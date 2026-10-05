"""
Post-payment lesson provisioning: Zoom room, tutor Google Calendar event, confirmation e-mail (Slice F0).

One `payments.FulfillmentDispatch` row per booking. The protocol:

* `claim_dispatch`: ONE conditional UPDATE moves PENDING | QUEUED | RETRYABLE (or a RUNNING row whose lease expired) to RUNNING
  with a fresh `claim_token`. A concurrent second run updates 0 rows and exits, so two workers never build two rooms.
* Every later write to the dispatch is conditional on (RUNNING, my token). A reschedule resets the row
  (`reset_for_reprovision`), which silently revokes the claim; the stale worker then stops and keeps nothing.
* The booking is re-read under its row lock and must still be CONFIRMED (a cancelled lesson is never provisioned); booking
  writes use `update_fields` only, so a stale instance can never overwrite a cancellation or any other column.
* The Zoom HTTP call runs outside the row lock. A meeting created for a lesson that was cancelled or moved meanwhile, or whose
  save failed, is deleted again (`cleanup_zoom_meeting`): no orphaned rooms.
* Each step ends `done`, `skipped` (nothing to do, e.g. no Google Calendar connected) or `failed`. A failed step makes the
  dispatch RETRYABLE (`next_retry_at`, honouring a provider `retry_after_seconds`) until FULFILLMENT_MAX_ATTEMPTS, then
  terminal FAILED with an admin alert. A permanent e-mail failure (`classify_failure`) is terminal at once. Finished steps
  are never repeated on a retry (no second Zoom room).
"""
import logging
import random
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.bookings.models import Booking
from apps.integrations.email import send_booking_confirmation_email
from apps.integrations.google_calendar import sync_booking_to_teacher_gcal
from apps.bookings.services.video_provider import uses_video_sdk
from apps.integrations.zoom import zoom_client
from apps.integrations.zoom_hosts import host_picker
from apps.notifications.alerts import alert_staff
from apps.payments.models import FulfillmentDispatch

logger = logging.getLogger(__name__)

D = FulfillmentDispatch.Status
St = FulfillmentDispatch.StepState
CLAIMABLE = (D.PENDING, D.QUEUED)            # + RETRYABLE once due (_due_retry_q) + stale RUNNING
REQUEUEABLE = (D.PENDING, D.QUEUED, D.ABANDONED)
FINISHED_STEP = (St.DONE, St.SKIPPED)
STEP_FLAGS = {'zoom': 'zoom_completed', 'calendar': 'calendar_completed', 'email': 'email_completed'}
# No zoom_start_url (Slice Z1): the host link expires and is fetched fresh by the host-link endpoint, never stored.
ZOOM_FIELDS = ['zoom_meeting_id', 'zoom_join_url', 'zoom_password', 'zoom_host_user_id', 'updated_at']


class ClaimRevoked(Exception):
    """The dispatch was reset (reschedule) or reclaimed after the lease: this run must stop and keep nothing."""


class NotConfirmed(Exception):
    """The booking is no longer CONFIRMED (cancelled, moved on in its lifecycle): nothing more to provision."""


class CalendarNotSynced(Exception):
    """The tutor has a calendar connected but no event id came back."""


class EmailNotSent(Exception):
    """The confirmation e-mail provider did not accept the message."""


def stale_running_q(now):
    """RUNNING rows whose worker has not finished within the lease (it died or hangs): they may be claimed again."""
    cutoff = now - timedelta(seconds=settings.FULFILLMENT_LEASE_SECONDS)
    return Q(status=D.RUNNING) & (Q(claimed_at__lt=cutoff) | Q(claimed_at__isnull=True))


def stale_queued_q(now):
    """PENDING/QUEUED rows untouched for FULFILLMENT_QUEUED_STALE_SECONDS: the broker message was lost or acked early."""
    return Q(status__in=(D.PENDING, D.QUEUED),
             updated_at__lt=now - timedelta(seconds=settings.FULFILLMENT_QUEUED_STALE_SECONDS))


def _due_retry_q(now):
    """A RETRYABLE row may run again only once its retry time (incl. a provider's retry_after) has come."""
    return Q(status=D.RETRYABLE) & (Q(next_retry_at__lte=now) | Q(next_retry_at__isnull=True))


def _owned(booking_id, token):
    return FulfillmentDispatch.objects.filter(booking_id=booking_id, status=D.RUNNING, claim_token=token)


def claim_dispatch(booking_id, *, now=None):
    """Compare-and-swap claim. Returns the claim token, or None when another run holds (or finished) the dispatch, or a
    retry is not due yet (a replayed webhook cannot bypass the backoff / retry_after)."""
    now = now or timezone.now()
    FulfillmentDispatch.objects.get_or_create(booking_id=booking_id)
    token = uuid.uuid4().hex
    won = (FulfillmentDispatch.objects.filter(booking_id=booking_id)
           .filter(Q(status__in=CLAIMABLE) | _due_retry_q(now) | stale_running_q(now))
           .update(status=D.RUNNING, claim_token=token, claimed_at=now, attempts=F('attempts') + 1,
                   last_error='', next_retry_at=None, updated_at=now))
    return token if won == 1 else None


def requeue(booking_id, *, now=None) -> bool:
    """Mark the dispatch QUEUED unless it succeeded, failed for good, a live worker holds it, or its retry is not due
    (then the row, incl. next_retry_at, is left untouched). True when queued."""
    now = now or timezone.now()
    FulfillmentDispatch.objects.get_or_create(booking_id=booking_id)
    return (FulfillmentDispatch.objects.filter(booking_id=booking_id)
            .filter(Q(status__in=REQUEUEABLE) | _due_retry_q(now) | stale_running_q(now))
            .update(status=D.QUEUED, claim_token='', last_error='', next_retry_at=None, updated_at=now)) == 1


def admin_requeue(dispatches, *, actor) -> list:
    """Staff action (Django admin): give terminally FAILED dispatches a fresh run. Returns the booking ids re-queued."""
    from apps.integrations.tasks import dispatch_booking_fulfillment
    requeued = []
    for booking_id in list(dispatches.filter(status=D.FAILED).values_list('booking_id', flat=True)):
        now = timezone.now()
        if FulfillmentDispatch.objects.filter(booking_id=booking_id, status=D.FAILED).update(
                status=D.QUEUED, attempts=0, claim_token='', last_error='', next_retry_at=None, updated_at=now):
            logger.warning('[ADMIN] Fulfilment re-queued: booking=%s actor=%s', booking_id, actor.pk)
            dispatch_booking_fulfillment.delay(str(booking_id))
            requeued.append(booking_id)
    return requeued


def retry_delay_seconds(attempts: int, retry_after) -> int:
    """Jittered exponential backoff: FULFILLMENT_RETRY_SECONDS doubling per attempt, capped, never below retry_after."""
    base = min(settings.FULFILLMENT_RETRY_SECONDS * 2 ** min(max(attempts, 1) - 1, 20), settings.FULFILLMENT_RETRY_MAX_SECONDS)
    jitter = random.uniform(0.8, 1.2)  # noqa: S311 - spreads retry timing only, not a security value
    delay = min(int(base * jitter), settings.FULFILLMENT_RETRY_MAX_SECONDS)
    return max(delay, int(retry_after or 0))


def reset_for_reprovision(booking) -> None:
    """Inside the reschedule transaction: the lesson moved, so every step runs again (new room, new event, new e-mail).
    Clearing the claim token revokes any run still working on the old time."""
    FulfillmentDispatch.objects.update_or_create(booking=booking, defaults=dict(
        status=D.QUEUED, attempts=0, last_error='', next_retry_at=None, claim_token='', claimed_at=None,
        zoom_state=St.PENDING, calendar_state=St.PENDING, email_state=St.PENDING,
        zoom_completed=False, calendar_completed=False, email_completed=False))


def run_fulfillment(booking_id, *, now=None) -> str:
    """Claim and run the outstanding steps. Returns succeeded | not_claimed | revoked | abandoned | retryable | failed | missing."""
    now = now or timezone.now()
    if not Booking.objects.filter(pk=booking_id).exists():
        logger.error('Fulfilment skipped: booking=%s does not exist', booking_id)
        return 'missing'
    token = claim_dispatch(booking_id, now=now)
    if token is None:
        logger.info('Fulfilment not claimed (another run holds or finished it): booking=%s', booking_id)
        return 'not_claimed'
    dispatch = FulfillmentDispatch.objects.get(booking_id=booking_id)
    step = 'zoom'
    try:
        for step, run_step in (('zoom', _zoom_step), ('calendar', _calendar_step), ('email', _email_step)):
            if getattr(dispatch, f'{step}_state') not in FINISHED_STEP:
                run_step(booking_id, token, now)
    except ClaimRevoked:
        logger.info('Fulfilment claim revoked mid-run (rescheduled or reclaimed): booking=%s', booking_id)
        return 'revoked'
    except NotConfirmed:
        _finish(booking_id, token, D.ABANDONED, now)
        logger.info('Fulfilment abandoned, booking no longer confirmed: booking=%s', booking_id)
        return 'abandoned'
    except Exception as exc:    # a provider / database failure in one step: recorded, retried, alerted after N attempts
        return _fail(booking_id, token, step, exc, now)
    _finish(booking_id, token, D.SUCCEEDED, now)
    return 'succeeded'


def _finish(booking_id, token, status, now) -> None:
    _owned(booking_id, token).update(status=status, claim_token='', last_error='', next_retry_at=None, updated_at=now)


def classify_failure(exc) -> tuple[bool, int | None]:
    """(permanent, retry_after_seconds) for a step failure.

    Adapter for the e-mail contract of slice N1c, written so it works before and after that merge: N1c raises
    `EmailDeliveryError` carrying `.result` (an EmailResult: status sent|retryable|failed|in_flight, retry_after_seconds) and a
    subclass `EmailPermanentError` (status `failed`: 422/403/not configured). Permanence is read from `.result.status`, so no
    class that may not exist yet is imported. Every other exception (Zoom, Google, database, broker) is transient."""
    result = getattr(exc, 'result', None)
    if result is None:
        # Slice Z1: a Zoom 429 whose Retry-After exceeded the client's inline cap carries it on the ZoomError.
        retry_after = getattr(exc, 'retry_after_seconds', None)
        return False, (int(retry_after) if isinstance(retry_after, int) and retry_after > 0 else None)
    if getattr(result, 'status', None) == 'failed':
        return True, None
    retry_after = getattr(result, 'retry_after_seconds', None)
    return False, (int(retry_after) if retry_after else None)


def _fail(booking_id, token, step, exc, now) -> str:
    """Terminal policy: a permanent failure ends at once; otherwise retry with backoff while the lesson is still ahead (each
    retry may still save it) and give up only after FULFILLMENT_MAX_ATTEMPTS once it has started (a room is useless then,
    and the T+10 guard disputes a lesson without one). Staff are alerted when the cap is reached either way."""
    attempts = FulfillmentDispatch.objects.filter(booking_id=booking_id).values_list('attempts', flat=True).first() or 0
    lesson_started = Booking.objects.filter(pk=booking_id, start_time_utc__lte=now).exists()
    permanent, retry_after = classify_failure(exc)
    capped = attempts >= settings.FULFILLMENT_MAX_ATTEMPTS
    terminal = permanent or (capped and lesson_started)
    delay = retry_delay_seconds(attempts, retry_after)
    fields = {f'{step}_state': St.FAILED, STEP_FLAGS[step]: False, 'last_error': f'{step}: {type(exc).__name__}',
              'claim_token': '', 'updated_at': now,
              'status': D.FAILED if terminal else D.RETRYABLE,
              'next_retry_at': None if terminal else now + timedelta(seconds=delay)}
    if not _owned(booking_id, token).update(**fields):
        return 'revoked'
    error = type(exc).__name__
    # Staff alerts go through notify() (slice N1a); payments/services/alerts.py stays payment-bound. The claim token keys
    # the alert to this run, so an admin re-queue that fails again alerts again.
    alert = {'booking_id': str(booking_id), 'step': step, 'error': error, 'attempts': attempts}
    if terminal:
        logger.error('[ADMIN ALERT] FULFILMENT FAILED booking=%s step=%s error=%s attempts=%s permanent=%s',
                     booking_id, step, error, attempts, permanent)
        alert_staff('fulfilment_failed', key=f'admin:fulfilment-failed:{booking_id}:{token}', payload=alert)
        return 'failed'
    if attempts == settings.FULFILLMENT_MAX_ATTEMPTS:
        logger.error('[ADMIN ALERT] FULFILMENT NEEDS ATTENTION booking=%s step=%s error=%s attempts=%s (still retrying)',
                     booking_id, step, error, attempts)
        alert_staff('fulfilment_needs_attention', key=f'admin:fulfilment-attention:{booking_id}:{token}', payload=alert)
    logger.warning('Fulfilment step failed, will retry: booking=%s step=%s error=%s attempt=%s in=%ss',
                   booking_id, step, error, attempts, delay)
    _schedule_retry(booking_id, delay)
    return 'retryable'


def _schedule_retry(booking_id, delay) -> None:
    """Next attempt via countdown (the 5-minute sweep stays the safety net if the broker refuses)."""
    from apps.integrations.tasks import dispatch_booking_fulfillment
    try:
        dispatch_booking_fulfillment.apply_async(args=[str(booking_id)], countdown=delay + 1)
    except Exception as exc:
        logger.error('Could not schedule the fulfilment retry: booking=%s error=%s (the sweep will pick it up)',
                     booking_id, type(exc).__name__)


def _set_step(booking_id, token, step, state, now) -> None:
    updated = _owned(booking_id, token).update(**{f'{step}_state': state, STEP_FLAGS[step]: state in FINISHED_STEP,
                                                 'updated_at': now})
    if not updated:
        raise ClaimRevoked()


def _locked_confirmed(booking_id, token):
    """Row-lock the booking (call inside atomic) and prove the claim is still ours and the lesson still on."""
    booking = (Booking.objects.select_for_update(of=('self',))
               .select_related('teacher__user', 'student').get(pk=booking_id))
    return _require_live(booking, token)


def _require_live(booking, token):
    if not _owned(booking.pk, token).exists():
        raise ClaimRevoked()
    if booking.status != Booking.Status.CONFIRMED:
        raise NotConfirmed()
    return booking


def _delete_orphan(meeting_id, booking_id) -> None:
    from apps.integrations.tasks import cleanup_zoom_meeting
    logger.warning('Deleting Zoom meeting created for booking=%s that was not kept: meeting=%s', booking_id, meeting_id)
    try:
        cleanup_zoom_meeting.delay(meeting_id)
    except Exception as exc:    # broker down: a human must delete it; never hide that
        logger.error('[ADMIN ALERT] ORPHANED ZOOM MEETING meeting=%s booking=%s error=%s',
                     meeting_id, booking_id, type(exc).__name__)
        alert_staff('orphaned_zoom_meeting', key=f'admin:orphaned-zoom-meeting:{meeting_id}',
                    payload={'meeting_id': str(meeting_id), 'booking_id': str(booking_id)})


def _zoom_step(booking_id, token, now) -> None:
    with transaction.atomic():
        booking = _locked_confirmed(booking_id, token)
        if booking.zoom_meeting_id:
            _set_step(booking_id, token, 'zoom', St.DONE, now)       # a room exists: reuse it, never build a second one
            return
        if uses_video_sdk(booking):
            _set_step(booking_id, token, 'zoom', St.SKIPPED, now)    # Video SDK lesson: the classroom needs no Meetings room
            return
    student, tutor = booking.student, booking.teacher.user
    # Any earlier attempt (a failed step, OR a worker that died after Zoom built the room and was reclaimed: attempts > 1)
    # may have left a meeting behind: look for it before creating another (Z1, QA #2).
    retried = FulfillmentDispatch.objects.filter(booking_id=booking_id).filter(
        Q(attempts__gt=1) | Q(zoom_state=St.FAILED)).exists()
    data = zoom_client.create_meeting(        # outside the row lock
        topic=f"Sharon ESL: {student.first_name or student.username} with {tutor.first_name or tutor.username}",
        start_time_iso=booking.start_time_utc.strftime('%Y-%m-%dT%H:%M:%SZ'), duration_minutes=25,
        booking_id=str(booking_id), host_user_id=host_picker.pick_host(booking), search_first=retried)
    _store_meeting(booking_id, token, data, now)


def _store_meeting(booking_id, token, data, now) -> None:
    """Keep the new room only if the lesson is still ours, still confirmed and has no room yet; otherwise delete it."""
    meeting_id, stored, wrote = str(data['meeting_id']), False, False
    try:
        with transaction.atomic():
            booking = _locked_confirmed(booking_id, token)
            if not booking.zoom_meeting_id:
                booking.zoom_meeting_id, booking.zoom_join_url = meeting_id, data['join_url']
                booking.zoom_password = data.get('password', '')
                booking.zoom_host_user_id = data.get('host_user_id') or 'me'
                booking.save(update_fields=ZOOM_FIELDS)
                wrote = True
            _set_step(booking_id, token, 'zoom', St.DONE, now)
        stored = wrote
        if stored:
            logger.info('Zoom meeting provisioned: booking=%s meeting=%s', booking_id, meeting_id)
    finally:
        if not stored:
            _delete_orphan(meeting_id, booking_id)


def _live_booking(booking_id, token):
    return _require_live(Booking.objects.select_related('teacher__user', 'student').get(pk=booking_id), token)


def _calendar_step(booking_id, token, now) -> None:
    booking = _live_booking(booking_id, token)
    from apps.integrations.models import CalendarCredential
    connected = CalendarCredential.objects.filter(user=booking.teacher.user, revoked_at__isnull=True).exists()
    local_mode = settings.DEBUG or getattr(settings, 'ZOOM_SIMULATE_WITHOUT_CREDENTIALS', False)
    legacy_connected = local_mode and isinstance(booking.teacher.user.google_calendar_token, dict) \
        and bool(booking.teacher.user.google_calendar_token.get('access_token'))
    if not connected and not legacy_connected:
        _set_step(booking_id, token, 'calendar', St.SKIPPED, now)
        return
    event_id = sync_booking_to_teacher_gcal(booking)          # HTTP, outside the row lock; returns the id, saves nothing
    if not event_id:
        raise CalendarNotSynced()
    _store_event(booking_id, token, str(event_id), str(booking.teacher.user_id), now)


def _store_event(booking_id, token, event_id, tutor_user_id, now) -> None:
    """Same fence as `_store_meeting`: keep the event only for a still-confirmed lesson we still own that has none yet."""
    from apps.integrations.tasks import cleanup_gcal_event
    stored, wrote = False, False
    try:
        with transaction.atomic():
            booking = _locked_confirmed(booking_id, token)
            if not booking.teacher_gcal_event_id:
                booking.teacher_gcal_event_id = event_id
                booking.save(update_fields=['teacher_gcal_event_id', 'updated_at'])
                wrote = True
            _set_step(booking_id, token, 'calendar', St.DONE, now)
        stored = wrote
    finally:
        if not stored:
            logger.warning('Deleting calendar event created for booking=%s that was not kept', booking_id)
            try:
                cleanup_gcal_event.delay(tutor_user_id, event_id)
            except Exception as exc:
                logger.error('[ADMIN ALERT] ORPHANED CALENDAR EVENT booking=%s error=%s', booking_id, type(exc).__name__)
                alert_staff('orphaned_calendar_event', key=f'admin:orphaned-calendar-event:{booking_id}:{token}',
                            payload={'booking_id': str(booking_id), 'tutor_user_id': str(tutor_user_id)})


def email_was_sent(result) -> bool:
    """Explicit success: `True` (today's sender) or a result whose status is 'sent' (N1c's EmailResult). Anything else -
    False, None, a string, a retryable/in-flight result - is a failure."""
    return result is True or (not isinstance(result, (str, bytes)) and getattr(result, 'status', None) == 'sent')


def _email_step(booking_id, token, now) -> None:
    booking = _live_booking(booking_id, token)
    if not email_was_sent(send_booking_confirmation_email(booking)):
        raise EmailNotSent()
    _set_step(booking_id, token, 'email', St.DONE, now)
