"""`notify()`: the one way to create a notification (slice N1a; docs/NOTIFICATIONS.md §2).

    notify(user, 'kind', key='event:{id}', payload={'booking_id': ...}, booking=booking)

* Idempotent on `key`: a second call returns the existing row (or None if nothing was created) and enqueues nothing.
  The insert runs in its own savepoint, so a duplicate (a concurrent worker won the insert) never poisons the caller's
  transaction.
* Renders subject/html/text once and persists them; delivery re-sends exactly those bytes.
* Preferences: mandatory kinds always e-mail; an optional kind follows `email_by_kind` / `in_app_by_kind`.
* Delivery is enqueued with `transaction.on_commit`; a broker failure is logged and left to the 2-minute sweep.
* Producer contract: `notify()` raises only for programming errors (`UnknownKind`, `InvalidNotification`). A renderer
  error (own savepoint) becomes a minimal in-app row with `email_state=failed` / `render_error` plus a staff alert; a user
  without an address gets `skipped` / `no_address` at creation. An existing key returns the existing row unchanged, even if
  the payload differs.
"""
import logging
import re
import uuid

from django.db import IntegrityError, transaction

from apps.notifications import registry
from apps.notifications.builtin_kinds import ADMIN_ALERT
from apps.notifications.models import Notification, NotificationPreference
from apps.notifications.registry import EMAIL, IN_APP
from apps.notifications.rendering import one_line

logger = logging.getLogger(__name__)

ES = Notification.EmailState
_KEY = re.compile(r'[A-Za-z0-9:_.\-]{1,200}')
_PAYLOAD_KEY = re.compile(r'[a-z][a-z0-9_]{0,63}')
# Free text must never ride in a payload (plan §3.2: student_review, CRM dossier, tokens); ids and short codes only.
_FORBIDDEN_FRAGMENTS = ('review', 'note', 'dossier', 'token', 'password', 'secret', 'email', 'text', 'body',
                        'message', 'comment', 'statement')
MAX_PAYLOAD_ITEMS = 20
MAX_PAYLOAD_STRING = 128


class InvalidNotification(ValueError):
    """A programming error: bad key or a payload that is not ids-only."""


def booking_generation(booking) -> str:
    """Generation token for booking-bound keys (plan §6 `g`): a reschedule re-arms confirmations and reminders."""
    return f'{booking.pk}:{booking.reschedule_count}'


def booking_key(event: str, booking, role: str = '') -> str:
    key = f'{event}:{booking_generation(booking)}'
    return f'{key}:{role}' if role else key


def notify(user, kind: str, *, key: str, payload: dict, booking=None):
    """Create (or return the existing) notification for `key`; None when the user wants neither channel."""
    kind_def = registry.get(kind)
    _check_key(key)
    clean = _clean_payload(payload)
    existing = Notification.objects.filter(idempotency_key=key).first()
    if existing is not None:
        return existing
    wants_email, wants_in_app = effective_channels(user, kind_def)
    if not (wants_email or wants_in_app):
        return None
    base = dict(user=user, kind=kind, idempotency_key=key, payload=clean, booking=booking, in_app=wants_in_app)
    try:
        with transaction.atomic():                      # savepoint: a renderer's DB error never aborts the caller
            rendered = kind_def.render(user, clean, booking)
    except Exception as exc:    # a template bug must never break the producer (a booking, a settlement, a cancel)
        return _render_failed(kind_def, base, exc)
    # No address: nothing to send and nothing to retry, so the row is born `skipped` (no failed row, no staff alert).
    has_address = bool((getattr(user, 'email', '') or '').strip())
    send = wants_email and has_address
    fields = dict(base, title=rendered.title, body=rendered.body, email_state=ES.PENDING if send else ES.SKIPPED,
                  email_last_error='no_address' if wants_email and not has_address else '')
    if send:
        fields.update(rendered_subject=rendered.subject, rendered_html=rendered.html, rendered_text=rendered.text)
    notification, created = _insert(fields)
    if send and created:
        transaction.on_commit(lambda: enqueue_delivery(notification.pk))
    return notification


def _insert(fields):
    """(row, created). A lost insert race returns the winner's row with created=False."""
    try:
        with transaction.atomic():                      # own savepoint: a duplicate never breaks the caller
            return Notification.objects.create(**fields), True
    except IntegrityError:
        return Notification.objects.get(idempotency_key=fields['idempotency_key']), False


def _render_failed(kind_def, base, exc):
    """The renderer raised: keep a minimal in-app row (title only) with a failed e-mail, alert staff, never raise."""
    logger.error('notification.render_failed kind=%s key=%s error=%s', kind_def.name, base['idempotency_key'],
                 type(exc).__name__)
    notification, created = _insert(dict(base, title=one_line(kind_def.name.replace('_', ' ')), body='',
                                         email_state=ES.FAILED, email_last_error='render_error'))
    if created and kind_def.name != ADMIN_ALERT:        # recursion guard: a broken alert template cannot alert about itself
        from apps.notifications.delivery import alert_failure
        alert_failure(notification, 'render_error')
    return notification


def effective_channels(user, kind_def) -> tuple:
    """(e-mail, in-app) after preferences. The mandatory set (registry) cannot be switched off."""
    email = EMAIL in kind_def.channels
    in_app = IN_APP in kind_def.channels
    if kind_def.mandatory:
        return email, in_app
    pref = NotificationPreference.objects.filter(user=user).first()
    if pref is not None:
        email = email and pref.email_by_kind.get(kind_def.name, True) is not False
        in_app = in_app and pref.in_app_by_kind.get(kind_def.name, True) is not False
    return email, in_app


def enqueue_delivery(notification_id) -> None:
    from apps.notifications.tasks import deliver_notification_task
    try:
        deliver_notification_task.delay(str(notification_id))
    except Exception as exc:        # broker down: the row is durable and the 2-minute sweep sends it
        logger.error('notification.enqueue_failed id=%s error=%s (left for the sweep)', notification_id,
                     type(exc).__name__)


def _check_key(key) -> None:
    if not isinstance(key, str) or not _KEY.fullmatch(key):
        raise InvalidNotification('key must be 1..200 characters of A-Z a-z 0-9 : _ . -')


def _clean_payload(payload) -> dict:
    if not isinstance(payload, dict) or len(payload) > MAX_PAYLOAD_ITEMS:
        raise InvalidNotification('payload must be a small dict of ids')
    clean = {}
    for name, value in payload.items():
        if not isinstance(name, str) or not _PAYLOAD_KEY.fullmatch(name):
            raise InvalidNotification('payload keys must be snake_case')
        if any(fragment in name for fragment in _FORBIDDEN_FRAGMENTS):
            raise InvalidNotification(f'payload key {name!r} looks like free text; payloads carry ids only')
        clean[name] = _clean_value(name, value)
    return clean


def _clean_value(name, value):
    if isinstance(value, uuid.UUID):
        return str(value)
    if value is None or isinstance(value, (bool, int)):        # bool is an int; float is neither (no money here)
        return value
    if isinstance(value, str) and len(value) <= MAX_PAYLOAD_STRING:
        return value
    raise InvalidNotification(f'payload value of {name!r} must be an id, a short code, an int, a bool or None')
