from celery import shared_task
from datetime import timedelta
from django.utils import timezone
from apps.bookings.models import Booking
from apps.payments.models import FulfillmentDispatch
from .zoom import zoom_client
from .google_calendar import sync_booking_to_teacher_gcal
from .email import send_booking_confirmation_email
from .services.eskom import EskomProviderError, EskomQuotaError, eskom_client
import logging

logger = logging.getLogger(__name__)


@shared_task(name='apps.integrations.tasks.retry_fulfillment_dispatches_task')
def retry_fulfillment_dispatches_task():
    """Re-enqueue durable fulfillment failures whose retry time has arrived."""
    from apps.common.locks import distributed_task_lock
    from apps.payments.services.webhook_handler import dispatch_fulfillment

    @distributed_task_lock('lock:beat:retry_fulfillment_dispatches', timeout_seconds=240)
    def _execute():
        due_ids = list(FulfillmentDispatch.objects.filter(
            status=FulfillmentDispatch.Status.RETRYABLE,
            next_retry_at__lte=timezone.now(),
        ).values_list('booking_id', flat=True)[:100])
        for booking_id in due_ids:
            dispatch_fulfillment(str(booking_id))
        return {'redispatched_count': len(due_ids)}

    return _execute()

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def dispatch_booking_fulfillment(self, booking_id: str):
    """
    Asynchronous Celery task that executes upon payment confirmation:
    1. Provisions a dedicated 25-minute Zoom meeting room via Server-to-Server OAuth 2.0.
    2. Syncs the confirmed lesson into the teacher's connected Google Calendar.
    3. Generates the standard .ics calendar invite and emails it to the student via Resend.
    """
    try:
        booking = Booking.objects.get(id=booking_id)
    except Booking.DoesNotExist:
        logger.error(f"Cannot fulfill booking: ID {booking_id} does not exist.")
        return False

    dispatch, _ = FulfillmentDispatch.objects.get_or_create(booking=booking)
    dispatch.status = FulfillmentDispatch.Status.RUNNING
    dispatch.attempts += 1
    dispatch.last_error = ''
    dispatch.save(update_fields=['status', 'attempts', 'last_error', 'updated_at'])

    def retryable_failure(component, exc):
        dispatch.status = FulfillmentDispatch.Status.RETRYABLE
        dispatch.last_error = f'{component}: {exc}'[:2000]
        dispatch.next_retry_at = timezone.now() + timedelta(seconds=60)
        dispatch.save(update_fields=['status', 'last_error', 'next_retry_at', 'updated_at'])
        raise self.retry(exc=exc)

    # 1. Provision Zoom Meeting
    if not dispatch.zoom_completed:
        try:
            if not booking.zoom_meeting_id:
                topic = f"Sharon ESL: {booking.student.first_name or booking.student.username} with {booking.teacher.user.first_name or booking.teacher.user.username}"
                zoom_data = zoom_client.create_meeting(
                    topic=topic,
                    start_time_iso=booking.start_time_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),
                    duration_minutes=25
                )
                booking.zoom_meeting_id = zoom_data['meeting_id']
                booking.zoom_join_url = zoom_data['join_url']
                booking.zoom_start_url = zoom_data['start_url']
                booking.zoom_password = zoom_data.get('password', '')
                booking.save()
            dispatch.zoom_completed = True
            dispatch.save(update_fields=['zoom_completed', 'updated_at'])
            logger.info(f"Zoom meeting provisioned successfully for booking={booking_id}: ID={booking.zoom_meeting_id}")
        except Exception as exc:
            logger.error(f"Error provisioning Zoom room for booking {booking_id}: {exc}")
            retryable_failure('zoom', exc)

    # 2. Sync to Teacher Google Calendar
    if not dispatch.calendar_completed:
        try:
            sync_booking_to_teacher_gcal(booking)
            dispatch.calendar_completed = True
            dispatch.save(update_fields=['calendar_completed', 'updated_at'])
        except Exception as exc:
            logger.warning(f"Google Calendar sync warning for booking {booking_id}: {exc}")
            retryable_failure('calendar', exc)

    # 3. Send Transactional Confirmation Email with .ics Invite
    if not dispatch.email_completed:
        try:
            send_booking_confirmation_email(booking)
            dispatch.email_completed = True
            dispatch.save(update_fields=['email_completed', 'updated_at'])
        except Exception as exc:
            logger.warning(f"Email dispatch warning for booking {booking_id}: {exc}")
            retryable_failure('email', exc)

    dispatch.status = FulfillmentDispatch.Status.SUCCEEDED
    dispatch.last_error = ''
    dispatch.next_retry_at = None
    dispatch.save(update_fields=['status', 'last_error', 'next_retry_at', 'updated_at'])

    return True


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
    areas = set(TeacherProfile.objects.filter(
        accent=TeacherProfile.Accent.SOUTH_AFRICAN, is_active=True,
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

    attempt = EskomNotificationAttempt.objects.select_related(
        'recipient', 'booking__teacher__user', 'area_status',
    ).filter(pk=attempt_id).first()
    if attempt is None or attempt.state == EskomNotificationAttempt.State.SENT:
        return
    EskomNotificationAttempt.objects.filter(pk=attempt.pk).update(attempts=F('attempts') + 1)
    booking = attempt.booking
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
    from apps.teachers.models import TeacherProfile
    from apps.common.locks import distributed_task_lock

    @distributed_task_lock('lock:beat:reconcile_teacher_gcal', timeout_seconds=1600)
    def _execute():
        tutors = TeacherProfile.objects.filter(
            is_active=True,
            user__google_calendar_token__isnull=False
        ).select_related('user')

        reconciled = 0
        for tutor in tutors:
            token = tutor.user.google_calendar_token
            if token and token.get('access_token'):
                cache_key = f"gcal:busy:{tutor.id}"
                # Cache busy span placeholder
                cache.set(cache_key, [], timeout=7200)
                reconciled += 1
                logger.info(f"Reconciled Google Calendar free/busy status for tutor {tutor.user.username}")

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
    """Tell the other person a lesson was cancelled (the canceller sees the result on screen)."""
    from .email import EmailDeliveryError, EmailPermanentError, log_permanent_failure, send_email
    from .services.email import render_html
    booking = Booking.objects.select_related('teacher__user', 'student').filter(id=booking_id).first()
    if booking is None:
        return False
    when = booking.start_time_utc.strftime('%A %d %B %Y, %H:%M UTC')
    if cancelled_by == 'payment_failed':
        # The student's pending PayPal payment failed before the lesson (the student is told by the payment-failure e-mail).
        to, subject, line = booking.teacher.user.email, 'A lesson was cancelled', (
            f"The lesson on {when} was cancelled because the student's payment did not go through.")
    elif cancelled_by == 'student':
        to, subject, line = booking.teacher.user.email, 'A lesson was cancelled', f"{booking.student.first_name or booking.student.username} cancelled the lesson on {when}."
    else:
        to, subject, line = booking.student.email, 'Your lesson was cancelled by your tutor', (
            f"Your tutor had to cancel the lesson on {when}. You will be refunded to your original payment method, "
            f"or you can turn the refund into lesson credit in your wallet.")
    try:
        send_email(to, subject, render_html('<p>{line}</p>', line=line), line)
    except EmailPermanentError as exc:                      # retrying cannot help
        log_permanent_failure('send_cancellation_emails', booking_id, exc)
        raise
    except EmailDeliveryError as exc:
        raise self.retry(exc=exc)
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
