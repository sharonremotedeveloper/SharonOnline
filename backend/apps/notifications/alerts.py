"""Staff alerts through notify() (slice N1a): operational problems a person must see (fulfilment, attendance, delivery).

Money alerts stay in `payments/services/alerts.py::alert_admin` (GatewayAnomaly-backed, payment-bound; plan §3.2).

Recipients: `ADMIN_ALERT_RECIPIENTS` (e-mail addresses of staff accounts, case-insensitive). An address that is not an
active staff account (`is_staff` or role admin) is ignored, so a typo can never send operational detail to an outsider.
Empty = every active admin-role user. Each recipient gets an in-app item and an e-mail (the `staff_alert` category is
mandatory), keyed `{key}:{user_id}`, so a repeat of the same alert is a no-op.

`alert_staff` never raises into the caller (an alert must not break fulfilment or adjudication): any error is logged
with its type only and the caller's own `[ADMIN ALERT]` log line remains the fallback.
"""
import logging

from django.conf import settings
from django.db.models import Q

from apps.notifications.builtin_kinds import ADMIN_ALERT, ALERT_TITLES
from apps.notifications.service import notify
from apps.users.models import User

logger = logging.getLogger(__name__)


def staff_recipients() -> list:
    staff = User.objects.filter(is_active=True).filter(Q(is_staff=True) | Q(role=User.Role.ADMIN))
    wanted = [a.strip().lower() for a in settings.ADMIN_ALERT_RECIPIENTS if a and a.strip()]
    if not wanted:
        return list(User.objects.filter(is_active=True, role=User.Role.ADMIN).order_by('date_joined', 'pk'))
    matched = [u for u in staff.order_by('date_joined', 'pk') if (u.email or '').strip().lower() in wanted]
    if len(matched) < len(wanted):
        logger.warning('ADMIN_ALERT_RECIPIENTS: %s of %s addresses are not active staff accounts (ignored)',
                       len(wanted) - len(matched), len(wanted))
    return matched


def alert_staff(alert: str, *, key: str, payload=None) -> int:
    """Notify every staff recipient once per `key`. Returns how many recipients were notified (0 on any problem)."""
    if alert not in ALERT_TITLES:
        raise ValueError(f'unknown staff alert {alert!r}; add it to builtin_kinds.ALERT_TITLES')
    data = {'alert': alert, **(payload or {})}
    try:
        recipients = staff_recipients()
        if not recipients:
            logger.error('[ADMIN ALERT] %s key=%s: no recipient (set ADMIN_ALERT_RECIPIENTS or create an admin)',
                         alert, key)
            return 0
        for user in recipients:
            notify(user, ADMIN_ALERT, key=f'{key}:{user.pk}', payload=data)
    except Exception as exc:
        logger.error('[ADMIN ALERT] %s key=%s could not be raised: error=%s', alert, key, type(exc).__name__)
        return 0
    return len(recipients)
