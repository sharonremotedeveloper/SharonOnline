"""E-mail delivery state machine for notifications (slice N1a; protocol in docs/adr/ADR-0002-notification-delivery.md).

    pending | retryable (due) --claim--> sending --sent--------------> sent
                                           |      --retryable/in_flight--> retryable (jittered backoff, retry_after floor)
                                           |      --failed / cap / no address--> failed (+ staff alert)
                                           |      --first attempt >= 20 h ago--> failed 'stale_needs_review' (+ alert)
                                           +-- lease (15 min) expired: claimable again

* `claim` is ONE conditional UPDATE (compare-and-swap); the claim time is the claim token. Every result write is
  conditional on (sending, my claim time), so a worker whose lease was taken over cannot overwrite the new owner.
* The persisted subject/html/text are sent under `Idempotency-Key = idempotency_key`: a retry is byte-identical, and
  Resend (24 h key retention) returns the first result instead of sending twice. After 20 h we refuse to resend without a
  person (the key may have expired at Resend, so a resend could duplicate).
* Retries are not scheduled with countdowns: the 2-minute sweep (`sweep_due`) picks due rows, lost messages and expired
  leases.
"""
import logging
import random
from datetime import timedelta

from django.conf import settings
from django.db.models import DateTimeField, F, Q, Value
from django.db.models.functions import Coalesce

from apps.common import clock
from apps.integrations.services import email as email_service
from apps.integrations.services.email import IN_FLIGHT, RETRYABLE, SENT, InvalidEmailError
from apps.notifications import registry
from apps.notifications.models import Notification

logger = logging.getLogger(__name__)

ES = Notification.EmailState
RESEND_CUTOFF = timedelta(hours=20)        # Resend keeps idempotency keys 24 h; stay well inside it
ERROR_CODE_MAX = 64
_rng = random.SystemRandom()


def lease() -> timedelta:
    return timedelta(seconds=settings.NOTIFICATION_LEASE_SECONDS)


def _claimable_q(now):
    due = Q(email_state__in=[ES.PENDING, ES.RETRYABLE]) & (
        Q(email_next_attempt_at__isnull=True) | Q(email_next_attempt_at__lte=now))
    expired = Q(email_state=ES.SENDING) & (Q(email_claimed_at__isnull=True) | Q(email_claimed_at__lte=now - lease()))
    return due | expired


def claim(notification_id, now):
    """CAS pending|retryable(due)|expired sending -> sending. Returns the claim time (token) or None."""
    updated = Notification.objects.filter(pk=notification_id).filter(_claimable_q(now)).update(
        email_state=ES.SENDING, email_claimed_at=now, email_attempts=F('email_attempts') + 1,
        email_first_attempt_at=Coalesce('email_first_attempt_at', Value(now, output_field=DateTimeField())))
    return now if updated else None


def deliver(notification_id) -> str:
    """Claim and send one notification e-mail. Returns sent | retryable | failed | skipped | not_claimed | revoked.

    Clock: claim times and lease comparisons all use the application clock (`clock.now()`), not the database clock; workers
    are assumed NTP-synchronised (skew of seconds against a 15-minute lease is harmless). See ADR-0002.
    """
    now = clock.now()
    token = claim(notification_id, now)
    if token is None:
        return 'not_claimed'
    n = Notification.objects.select_related('user').get(pk=notification_id)
    if _expired(n, now):
        if not _owned(n, token).update(email_state=ES.SKIPPED, email_last_error='expired', email_next_attempt_at=None):
            return _revoked(n)
        logger.info('notification.expired id=%s kind=%s (no longer worth sending)', n.pk, n.kind)
        return 'skipped'
    if now - n.email_first_attempt_at >= RESEND_CUTOFF:
        return _fail(n, token, 'stale_needs_review', now)
    to = (n.user.email or '').strip()
    if not to:
        return _fail(n, token, 'no_address', now)
    try:
        result = email_service.send_email(to, n.rendered_subject, n.rendered_html, n.rendered_text,
                                          idempotency_key=n.idempotency_key)
    except InvalidEmailError:
        return _fail(n, token, 'invalid_address', now)
    return _record(n, token, result, now)


def _expired(n, now) -> bool:
    """The kind's `not_after` hook (e.g. a reminder is worthless once the lesson started). A broken hook never blocks mail."""
    try:
        kind = registry.get(n.kind)
        limit = kind.not_after(n.payload, n.booking) if kind.not_after else None
    except Exception as exc:
        logger.error('notification.not_after_failed id=%s kind=%s error=%s', n.pk, n.kind, type(exc).__name__)
        return False
    return limit is not None and now >= limit


def _record(n, token, result, now) -> str:
    code = (result.error_code or result.status)[:ERROR_CODE_MAX]
    if result.status == SENT:
        if not _owned(n, token).update(email_state=ES.SENT, email_sent_at=now, email_last_error='',
                                       provider_message_id=result.provider_message_id[:128]):
            return _revoked(n)
        logger.info('notification.sent id=%s provider_id=%s attempt=%s', n.pk, result.provider_message_id,
                    n.email_attempts)
        return 'sent'
    if result.status in (RETRYABLE, IN_FLIGHT):
        if n.email_attempts >= settings.NOTIFICATION_MAX_ATTEMPTS:
            return _fail(n, token, f'attempts_exhausted:{code}'[:ERROR_CODE_MAX], now)
        delay = backoff_seconds(n.email_attempts, result.retry_after_seconds)
        if not _owned(n, token).update(email_state=ES.RETRYABLE, email_last_error=code,
                                       email_next_attempt_at=now + timedelta(seconds=delay)):
            return _revoked(n)
        logger.warning('notification.retryable id=%s code=%s attempt=%s in=%ss', n.pk, code, n.email_attempts, delay)
        return 'retryable'
    return _fail(n, token, code, now)


def _fail(n, token, code, now) -> str:
    if not _owned(n, token).update(email_state=ES.FAILED, email_last_error=code[:ERROR_CODE_MAX],
                                   email_next_attempt_at=None):
        return _revoked(n)
    logger.error('notification.failed id=%s kind=%s code=%s attempt=%s', n.pk, n.kind, code, n.email_attempts)
    alert_failure(n, code)
    return 'failed'


def alert_failure(n, code) -> None:
    from apps.notifications.alerts import alert_staff
    from apps.notifications.builtin_kinds import ADMIN_ALERT
    if n.kind == ADMIN_ALERT:           # recursion guard: a failed alert e-mail never raises another alert
        logger.error('[ADMIN ALERT] staff alert e-mail failed id=%s code=%s (in-app item still shown)', n.pk, code)
        return
    alert_staff('notification_failed', key=f'admin:notification-failed:{n.pk}',
                payload={'notification_id': str(n.pk), 'kind': n.kind, 'code': code[:ERROR_CODE_MAX]})


def _owned(n, token):
    return Notification.objects.filter(pk=n.pk, email_state=ES.SENDING, email_claimed_at=token)


def _revoked(n) -> str:
    logger.warning('notification.claim_lost id=%s (lease taken over; the new owner decides)', n.pk)
    return 'revoked'


def backoff_seconds(attempts: int, retry_after=None) -> int:
    """Exponential from NOTIFICATION_RETRY_SECONDS, +-20 % jitter, capped; a provider's retry_after is a floor."""
    cap = settings.NOTIFICATION_RETRY_MAX_SECONDS
    base = settings.NOTIFICATION_RETRY_SECONDS * 2 ** min(max(attempts - 1, 0), 20)
    delay = min(min(base, cap) * _rng.uniform(0.8, 1.2), cap)
    if retry_after:
        delay = max(delay, int(retry_after))
    return int(delay)


def sweep_due(now) -> int:
    """Enqueue rows that are due: pending older than the sweep age (lost message / broker outage), retryable whose time
    has come, sending whose lease expired. Bounded by NOTIFICATION_SWEEP_LIMIT; stops at the first broker refusal."""
    from apps.notifications.tasks import deliver_notification_task
    pending_age = now - timedelta(seconds=settings.NOTIFICATION_SWEEP_AGE_SECONDS)
    due = (Q(email_state=ES.PENDING, created_at__lte=pending_age)
           | Q(email_state=ES.RETRYABLE) & (Q(email_next_attempt_at__isnull=True) | Q(email_next_attempt_at__lte=now))
           | Q(email_state=ES.SENDING) & (Q(email_claimed_at__isnull=True) | Q(email_claimed_at__lte=now - lease())))
    ids = list(Notification.objects.filter(due).order_by('created_at')
               .values_list('pk', flat=True)[:settings.NOTIFICATION_SWEEP_LIMIT])
    enqueued = 0
    for notification_id in ids:
        try:
            deliver_notification_task.delay(str(notification_id))
        except Exception as exc:    # broker down: the next sweep tries again
            logger.error('notification.sweep_enqueue_failed id=%s error=%s', notification_id, type(exc).__name__)
            break
        enqueued += 1
    return enqueued


def requeue_failed(queryset, *, actor) -> list:
    """A person reviewed failed rows (runbook) and wants them sent: fresh attempts, fresh 20 h window."""
    from apps.notifications.service import enqueue_delivery
    requeued = []
    for notification_id in list(queryset.filter(email_state=ES.FAILED).values_list('pk', flat=True)):
        if Notification.objects.filter(pk=notification_id, email_state=ES.FAILED).update(
                email_state=ES.PENDING, email_attempts=0, email_first_attempt_at=None, email_next_attempt_at=None,
                email_claimed_at=None, email_last_error=''):
            logger.warning('notification.requeued id=%s actor=%s', notification_id, getattr(actor, 'pk', actor))
            requeued.append(notification_id)
            enqueue_delivery(notification_id)
    return requeued
