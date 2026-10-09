from celery import shared_task
from datetime import timedelta
from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from apps.bookings.models import Booking
from apps.payments.models import FulfillmentDispatch
from .services.eskom import EskomProviderError, EskomQuotaError, eskom_client
import logging

logger = logging.getLogger(__name__)


@shared_task(name='apps.integrations.tasks.retry_fulfillment_dispatches_task')
def retry_fulfillment_dispatches_task():
    """Re-enqueue durable fulfillment failures whose retry time has arrived, RUNNING claims whose worker died (lease), and
    PENDING/QUEUED rows whose message was lost (no booking may stay without a room)."""
    from apps.common.locks import distributed_task_lock
    from apps.bookings.services.fulfillment import stale_queued_q, stale_running_q
    from apps.payments.services.webhook_handler import dispatch_fulfillment

    @distributed_task_lock('lock:beat:retry_fulfillment_dispatches', timeout_seconds=240)
    def _execute():
        now = timezone.now()
        due = (Q(status=FulfillmentDispatch.Status.RETRYABLE, next_retry_at__lte=now) | stale_running_q(now)
               | stale_queued_q(now))
        due_ids = list(FulfillmentDispatch.objects.filter(due).values_list('booking_id', flat=True)[:100])
        for booking_id in due_ids:
            dispatch_fulfillment(str(booking_id))
        return {'redispatched_count': len(due_ids)}

    return _execute()


@shared_task(name='apps.integrations.tasks.dispatch_booking_fulfillment')
def dispatch_booking_fulfillment(booking_id: str):
    """Daily room, tutor calendar event and confirmation e-mail for a confirmed lesson (claim protocol in
    bookings/services/fulfillment.py). Failures are retried by `retry_fulfillment_dispatches_task`, not by Celery."""
    from apps.bookings.services.fulfillment import run_fulfillment
    return run_fulfillment(str(booking_id)) == 'succeeded'


@shared_task(name='apps.integrations.tasks.sync_eskom_stages_task')
def sync_eskom_stages_task():
    """
    Periodic task running every 15 minutes:
    Synchronizes current Eskom load shedding stages for South African tutors.
    Caches active stages in Redis (eskom:stage:{area_id}) and scans upcoming
    confirmed lessons within the next 4 hours for tutors lacking battery backup,
    dispatching proactive advance reschedule warnings.
    """
    from apps.common.locks import distributed_task_lock

    @distributed_task_lock('lock:beat:sync_eskom_stages', timeout_seconds=800)
    def _execute():
        return sync_eskom_statuses(eskom_client)

    return _execute()


def sync_eskom_statuses(provider, now=None):
    """Provider-injected implementation used by the beat task and deterministic tests."""
    from django.core.cache import cache
    from django.db import transaction
    from django.utils.dateparse import parse_datetime
    from apps.integrations.models import EskomAreaStatus, EskomNotificationAttempt
    from apps.teachers.models import TeacherProfile

    now = now or timezone.now()
    # Approved tutors plus suspended ones who still have a lesson to teach; never applicants (slice T1b).
    areas = set(TeacherProfile.objects.operational(now).filter(
        accent=TeacherProfile.Accent.SOUTH_AFRICAN,
    ).exclude(eskom_area_id='').values_list('eskom_area_id', flat=True))
    result = {'synced_areas': 0, 'failed_areas': 0, 'vulnerable_bookings_flagged': 0,
              'notifications_created': 0}

    for area_id in areas:
        try:
            payload = provider.fetch_area_status(area_id)
            retrieved_at = payload.get('retrieved_at') or now
            status_row, _ = EskomAreaStatus.objects.update_or_create(
                area_id=area_id,
                defaults={
                    'area_name': payload['area_name'], 'stage': payload['stage'],
                    'outages': payload.get('outages') or [],
                    'provider_status': EskomAreaStatus.ProviderStatus.OK,
                    'provider_retrieved_at': retrieved_at,
                    'fresh_until': retrieved_at + timedelta(seconds=settings.ESKOMSEPUSH_FRESH_SECONDS),
                    'last_error_code': '',
                },
            )
            cache.set(f'eskom:stage:{area_id}', {
                'stage': status_row.stage, 'area_name': status_row.area_name,
                'outages': status_row.outages, 'retrieved_at': status_row.provider_retrieved_at.isoformat(),
                'provider_status': status_row.provider_status,
            }, timeout=settings.ESKOMSEPUSH_STALE_SECONDS)
            result['synced_areas'] += 1
        except (EskomQuotaError, EskomProviderError) as exc:
            state = EskomAreaStatus.ProviderStatus.QUOTA if isinstance(exc, EskomQuotaError) else EskomAreaStatus.ProviderStatus.ERROR
            EskomAreaStatus.objects.filter(area_id=area_id).update(provider_status=state, last_error_code=exc.code)
            result['failed_areas'] += 1
            continue

        upcoming = Booking.objects.filter(
            teacher__eskom_area_id=area_id,
            status=Booking.Status.CONFIRMED,
            start_time_utc__gte=now,
            start_time_utc__lte=now + timedelta(hours=4),
        ).select_related('teacher__user', 'student')
        for booking in upcoming:
            if booking.teacher.has_inverter_backup and booking.teacher.has_lte_failover:
                continue
            matching_window = None
            for outage in status_row.outages:
                start = parse_datetime(str(outage.get('start') or ''))
                end = parse_datetime(str(outage.get('end') or ''))
                if start and end and start < booking.end_time_utc and end > booking.start_time_utc:
                    matching_window = (start, end)
                    break
            if matching_window is None:
                continue
            result['vulnerable_bookings_flagged'] += 1
            window_key = matching_window[0].isoformat()
            for recipient in (booking.teacher.user, booking.student):
                attempt, created = EskomNotificationAttempt.objects.get_or_create(
                    idempotency_key=f'eskom-shield:{booking.id}:{recipient.id}:{window_key}',
                    defaults={'booking': booking, 'recipient': recipient, 'area_status': status_row},
                )
                if created:
                    result['notifications_created'] += 1
                    transaction.on_commit(lambda attempt_id=str(attempt.id): send_eskom_notification_task.delay(attempt_id))
    return result


@shared_task(bind=True, max_retries=8)
def send_eskom_notification_task(self, attempt_id):
    from django.db.models import F
    from django.utils.html import escape
    from apps.integrations.email import EmailDeliveryError, EmailPermanentError, log_permanent_failure, send_email
    from apps.integrations.models import EskomNotificationAttempt
    from apps.notifications.service import notify

    attempt = EskomNotificationAttempt.objects.select_related(
        'recipient', 'booking__teacher__user', 'area_status',
    ).filter(pk=attempt_id).first()
    if attempt is None or attempt.state == EskomNotificationAttempt.State.SENT:
        return
    EskomNotificationAttempt.objects.filter(pk=attempt.pk).update(attempts=F('attempts') + 1)
    booking = attempt.booking
    try:
        notify(
            attempt.recipient,
            'eskom_shield_alert',
            key=attempt.idempotency_key,
            payload={'booking_id': str(booking.id), 'area_name': attempt.area_status.area_name},
            booking=booking,
        )
    except Exception:
        logger.exception("notify failed for eskom_shield_alert on attempt %s", attempt.pk)

    subject = 'Power Guard warning for your upcoming lesson'
    time_text = booking.start_time_utc.strftime('%Y-%m-%d %H:%M UTC')
    area = escape(attempt.area_status.area_name)
    html = (f'<h2>Power Guard warning</h2><p>An outage window reported for {area} overlaps your '
            f'lesson at {escape(time_text)}.</p><p>Please prepare backup connectivity or contact support.</p>')
    text = f'An outage window reported for {attempt.area_status.area_name} overlaps your lesson at {time_text}.'
    try:
        send_email(attempt.recipient.email, subject, html, text)
    except EmailPermanentError as exc:                      # retrying cannot help: record it, do not retry
        EskomNotificationAttempt.objects.filter(pk=attempt.pk).update(last_error=f'permanent: {exc}'[:500])
        log_permanent_failure('send_eskom_notification_task', attempt.pk, exc)
        raise
    except EmailDeliveryError as exc:
        EskomNotificationAttempt.objects.filter(pk=attempt.pk).update(
            state=EskomNotificationAttempt.State.RETRYABLE, last_error=str(exc)[:500],
        )
        raise self.retry(exc=exc, countdown=min(30 * (2 ** self.request.retries), 1800))
    EskomNotificationAttempt.objects.filter(pk=attempt.pk).update(
        state=EskomNotificationAttempt.State.SENT,
        last_error='',
        sent_at=timezone.now(),
    )


@shared_task(name='apps.integrations.tasks.reconcile_teacher_gcal_task')
def reconcile_teacher_gcal_task():
    """
    Every 30 minutes: queue one `sync_tutor_busy_task` per tutor who can use the hint (operational, connected, "block my
    busy times" on). One job per tutor, so a slow or throttled Google account delays only itself.
    """
    from apps.common.locks import distributed_task_lock
    from apps.teachers.models import TeacherProfile

    @distributed_task_lock('lock:beat:reconcile_teacher_gcal', timeout_seconds=300)
    def _execute():
        tutor_ids = TeacherProfile.objects.operational().filter(
            user__calendar_credential__isnull=False, user__calendar_credential__revoked_at__isnull=True,
            user__calendar_credential__block_busy=True,
        ).values_list('id', flat=True)
        queued = 0
        for tutor_id in tutor_ids:
            sync_tutor_busy_task.delay(str(tutor_id))
            queued += 1
        return {"queued_tutors": queued}

    return _execute()


@shared_task(name='apps.integrations.tasks.sync_tutor_busy_task')
def sync_tutor_busy_task(tutor_id: str) -> str:
    """Slice G2: refresh one tutor's Google busy hint. A Google failure leaves the last hint and never fails the task."""
    from apps.teachers.models import TeacherProfile
    from .google_calendar import refresh_busy_hint

    tutor = TeacherProfile.objects.select_related('user').filter(pk=tutor_id).first()
    return refresh_busy_hint(tutor) if tutor else 'not_found'


@shared_task(bind=True, max_retries=3, default_retry_delay=120, name='apps.integrations.tasks.cleanup_daily_room')
def cleanup_daily_room(self, room_name: str):
    """Free a Daily lesson room after cancellation or rescheduling."""
    from .services.daily import DailyClient, is_daily_configured
    if not is_daily_configured():
        return True
    try:
        return DailyClient().delete_room(room_name)
    except Exception as exc:
        logger.error('Could not delete Daily room %s: %s', room_name, type(exc).__name__)
        raise self.retry(exc=exc) from exc


def _cancellation_recipients(booking, cancelled_by: str):
    outcome = 'full_refund' if cancelled_by in ('teacher', 'admin') else ('fee_forfeited' if cancelled_by == 'student_late' else 'cancelled')
    if cancelled_by == 'student':
        recipients = [booking.teacher.user]
    elif cancelled_by in ('teacher', 'admin', 'admin_unpaid'):
        recipients = [booking.student]
    else:
        recipients = [booking.student, booking.teacher.user]
    return recipients, outcome


def _cancellation_email_content(booking, cancelled_by: str):
    when = booking.start_time_utc.strftime('%A %d %B %Y, %H:%M UTC')
    if cancelled_by == 'payment_failed':
        return booking.teacher.user.email, 'A lesson was cancelled', (
            f"The lesson on {when} was cancelled because the student's payment did not go through."
        )
    if cancelled_by == 'admin':
        return booking.student.email, 'Your lesson was cancelled', (
            f"Your lesson on {when} was cancelled because your tutor is no longer available. You will be refunded to your "
            f"original payment method, or you can turn the refund into lesson credit in your wallet."
        )
    if cancelled_by == 'admin_unpaid':
        return booking.student.email, 'Your reservation was released', (
            f"Your reservation for the lesson on {when} was released because the tutor is no longer available. "
            f"Nothing was charged."
        )
    if cancelled_by == 'student':
        name = booking.student.first_name or booking.student.username
        return booking.teacher.user.email, 'A lesson was cancelled', f"{name} cancelled the lesson on {when}."
    return booking.student.email, 'Your lesson was cancelled by your tutor', (
        f"Your tutor had to cancel the lesson on {when}. You will be refunded to your original payment method, "
        f"or you can turn the refund into lesson credit in your wallet."
    )


@shared_task(bind=True, max_retries=3, default_retry_delay=120, name='apps.integrations.tasks.send_cancellation_emails')
def send_cancellation_emails(self, booking_id: str, cancelled_by: str):
    """Tell affected parties a lesson was cancelled (slice N2b)."""
    from .email import EmailDeliveryError, EmailPermanentError, log_permanent_failure, send_email
    from .services.email import render_html
    from apps.notifications.service import notify
    booking = Booking.objects.select_related('teacher__user', 'student').filter(id=booking_id).first()
    if booking is None:
        return False

    recipients, outcome = _cancellation_recipients(booking, cancelled_by)
    for recipient in recipients:
        key = f'booking-cancelled:{booking.id}:{recipient.id}'
        try:
            notify(recipient, 'booking_cancelled', key=key,
                   payload={'booking_id': str(booking.id), 'cancelled_by': cancelled_by, 'refund_outcome': outcome},
                   booking=booking)
        except Exception:
            logger.exception("notify failed for booking_cancelled on %s", key)

    to, subject, line = _cancellation_email_content(booking, cancelled_by)
    try:
        send_email(to, subject, render_html('<p>{line}</p>', line=line), line)
    except EmailPermanentError as exc:                      # retrying cannot help
        log_permanent_failure('send_cancellation_emails', booking_id, exc)
        raise
    except EmailDeliveryError as exc:
        raise self.retry(exc=exc) from exc

    return True


@shared_task(bind=True, max_retries=3, default_retry_delay=300, name='apps.integrations.tasks.cleanup_gcal_event')
def cleanup_gcal_event(self, teacher_user_id: str, event_id: str):
    """Take a cancelled / moved lesson off the tutor's Google Calendar."""
    from django.contrib.auth import get_user_model
    from .google_calendar import delete_teacher_gcal_event
    user = get_user_model().objects.filter(pk=teacher_user_id).first()
    if user is None:
        return False
    try:
        return delete_teacher_gcal_event(user, event_id)
    except Exception as exc:
        logger.error(f"Could not delete Google Calendar event {event_id}: {exc}")
        raise self.retry(exc=exc)
