"""
Admin alerts for money events that need a person (Task 10.2 failure runbook).

There is no alert inbox in the product yet, so an alert is: (1) a durable, de-duplicated `GatewayAnomaly` row that the
admin console and reconciliation already surface, (2) an ERROR log line, and (3) one e-mail to settings.SUPPORT_TO_EMAIL
sent through the existing Resend wrapper by a retrying Celery task. The row is the de-duplication key: while an
unresolved row with the same (code, key) exists, repeating the alert does nothing, so webhook retries, reconcile runs and
repeated requests never spam the admin. `resolve_alert` closes the row so the next occurrence alerts again ("once per
trip" for the circuit breaker).
"""
import logging

from django.db import transaction

from apps.payments.models import GatewayAnomaly, PaymentTransaction

logger = logging.getLogger(__name__)


def alert_admin(code: str, subject: str, detail: str, *, key: str, tx: PaymentTransaction | None = None,
                booking=None, gateway: str = '') -> bool:
    """Raise an admin alert once per open (code, key). Returns True when this call created it."""
    gateway = gateway or (tx.gateway if tx is not None else PaymentTransaction.Gateway.PAYPAL)
    booking = booking or (tx.booking if tx is not None and tx.booking_id else None)
    anomaly, created = GatewayAnomaly.objects.get_or_create(
        gateway=gateway, reference=str(key)[:255], reason=code[:64], resolved=False,
        defaults={'detail': detail, 'payment_transaction': tx, 'booking': booking})
    if not created:
        return False
    logger.error("[ADMIN ALERT] %s (%s): %s", code, key, detail)
    from apps.payments.tasks import send_admin_alert_email_task
    transaction.on_commit(lambda: send_admin_alert_email_task.delay(subject, detail))
    return True


def resolve_alert(code: str, key: str) -> int:
    return GatewayAnomaly.objects.filter(reason=code[:64], reference=str(key)[:255], resolved=False).update(resolved=True)
