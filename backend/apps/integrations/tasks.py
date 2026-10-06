from celery import shared_task
from datetime import timedelta
from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from apps.bookings.models import Booking
from apps.payments.models import FulfillmentDispatch
from .zoom import zoom_client
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
    """Zoom room, tutor calendar event and confirmation e-mail for a confirmed lesson (claim protocol in
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
    from django.conf import settings
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
    except Exception as exc:
        EskomNotificationAttempt.objects.filter(pk=attempt.pk).update(
            state=EskomNotificationAttempt.State.RETRYABLE, last_error=str(exc)[:500],
        )
        raise self.retry(exc=exc, countdown=min(30 * (2 ** self.request.retries), 1800))
    EskomNotificationAttempt.objects.filter(pk=attempt.pk).update(
        state=EskomNotificationAttempt.State.SENT, last_error='', sent_at=timezone.now(),
    )


@shared_task(name='apps.integrations.tasks.reconcile_teacher_gcal_task')
def reconcile_teacher_gcal_task():
    """
    Periodic task running every 30 minutes:
    Synchronizes connected teacher Google Calendars to detect external busy blocks
    and caches them in Redis for availability slot deduction.
    """
    from django.core.cache import cache
    from django.utils.dateparse import parse_datetime
    from .google_calendar import fetch_freebusy
    from apps.teachers.models import TeacherProfile
    from apps.common.locks import distributed_task_lock

    @distributed_task_lock('lock:beat:reconcile_teacher_gcal', timeout_seconds=1600)
    def _execute():
        # Same rule as the Eskom sync (slice T1b): approved tutors and suspended ones with lessons left; no applicants.
        tutors = TeacherProfile.objects.operational().filter(
            user__calendar_credential__revoked_at__isnull=True
        ).select_related('user', 'user__calendar_credential')

        reconciled = 0
        for tutor in tutors:
            credential = getattr(tutor.user, 'calendar_credential', None)
            local_mode = settings.DEBUG or getattr(settings, 'ZOOM_SIMULATE_WITHOUT_CREDENTIALS', False)
            if credential or (local_mode and isinstance(tutor.user.google_calendar_token, dict)
                              and tutor.user.google_calendar_token.get('access_token')):
                cache_key = f"gcal:busy:{tutor.id}"
                # No credential row = the local-simulation legacy token: nothing to fetch, cache an empty busy list.
                if credential is None or not credential.block_busy:
                    cache.set(cache_key, [], timeout=7200)
                    reconciled += 1
                    continue
                now = timezone.now()
                try:
                    busy = fetch_freebusy(tutor.user, now, now + timedelta(days=settings.BOOKING_HORIZON_DAYS + 1))
                    intervals = []
                    for item in busy:
                        start, end = parse_datetime(str(item.get('start') or '')), parse_datetime(str(item.get('end') or ''))
                        if start and end and start < end:
                            intervals.append((start.isoformat(), end.isoformat()))
                    cache.set(cache_key, intervals, timeout=7200)
                    reconciled += 1
                    logger.info('Reconciled Google Calendar free/busy for tutor %s', tutor.user.username)
                except Exception as exc:
                    logger.warning('Google Calendar free/busy unavailable for tutor %s: %s', tutor.user.username, exc)

        return {"reconciled_tutors": reconciled}

    return _execute()


@shared_task(bind=True, max_retries=3, default_retry_delay=120, name='apps.integrations.tasks.cleanup_zoom_meeting')
def cleanup_zoom_meeting(self, meeting_id: str):
    """Free a Zoom room whose lesson was cancelled or moved. Retried; a persistent failure is logged for a human."""
    try:
        return zoom_client.delete_meeting(meeting_id)
    except Exception as exc:
        logger.error(f"Could not delete Zoom meeting {meeting_id}: {exc}")
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=120, name='apps.integrations.tasks.send_cancellation_emails')
def send_cancellation_emails(self, booking_id: str, cancelled_by: str):
    """Tell affected parties a lesson was cancelled (slice N2b)."""
    from apps.notifications.service import notify
    booking = Booking.objects.select_related('teacher__user', 'student').filter(id=booking_id).first()
    if booking is None:
        return False

    outcome = 'full_refund' if cancelled_by in ('teacher', 'admin') else ('fee_forfeited' if cancelled_by == 'student_late' else 'cancelled')
    
    if cancelled_by == 'student':
        recipients = [booking.teacher.user]
    elif cancelled_by in ('teacher', 'admin', 'admin_unpaid'):
        recipients = [booking.student]
    elif cancelled_by == 'payment_failed':
        recipients = [booking.student, booking.teacher.user]
    else:
        recipients = [booking.student, booking.teacher.user]

    for recipient in recipients:
        key = f'booking-cancelled:{booking.id}:{recipient.id}'
        notify(recipient, 'booking_cancelled', key=key,
               payload={'booking_id': str(booking.id), 'cancelled_by': cancelled_by, 'refund_outcome': outcome},
               booking=booking)

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
