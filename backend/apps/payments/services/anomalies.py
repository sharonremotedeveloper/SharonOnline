from apps.payments.models import GatewayAnomaly


def record_anomaly(gateway, reference, reason, detail='', tx=None, payload=None):
    """
    Persist an authenticated-but-unappliable notification (money may have moved). Only call AFTER signature/IP checks
    so unauthenticated callers cannot fill the table. De-duplicated so gateway retries do not multiply rows.
    """
    GatewayAnomaly.objects.get_or_create(
        gateway=gateway, reference=str(reference or '')[:255], reason=reason, resolved=False,
        defaults={'detail': detail, 'payload': payload or {}, 'payment_transaction': tx,
                  'booking': tx.booking if tx is not None and tx.booking_id else None})
