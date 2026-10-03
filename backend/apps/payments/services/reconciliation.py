from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction as db_transaction
from django.utils import timezone

from apps.bookings.services.holds import hold_is_live
from apps.payments.gateways import paypal
from apps.payments.models import GatewayAnomaly, PaymentTransaction
from apps.payments.services.anomalies import record_anomaly
from apps.payments.services.paypal_capture import (CaptureRejected, record_pending_capture, settle_completed_capture,
                                                   verify_capture_amount)

# An unpaid, unapproved credit-pack order has no booking hold to lapse; PayPal itself stops honouring an unapproved order
# after hours, so a day is far past any real checkout.
UNPAID_CREDIT_ORDER_MAX_AGE = timedelta(hours=24)
# PayPal order statuses that mean "created but not paid"; every other status without a capture is not trusted either way.
UNPAID_ORDER_STATUSES = frozenset({'CREATED', 'SAVED', 'APPROVED', 'PAYER_ACTION_REQUIRED'})


@dataclass(frozen=True)
class ReconciliationResult:
    state: str
    detail: str = ''
    payload: dict | None = None
    track: bool = True      # False: a normal in-flight checkout, no operator anomaly needed


def query_gateway(transaction: PaymentTransaction) -> ReconciliationResult:
    """Read provider state without guessing that an old checkout failed."""
    if transaction.gateway == PaymentTransaction.Gateway.PAYPAL:
        # An unpaid checkout is looked up by its order; a PENDING_CAPTURE one already has a capture id, which is exact.
        if transaction.gateway_order_id and transaction.status == PaymentTransaction.Status.INITIALIZED:
            return _query_paypal_order(transaction)
        if transaction.gateway_reference.startswith('INIT-'):
            return ReconciliationResult(
                'unresolved',
                'PayPal capture id is not yet known; await a verified webhook or operator lookup.',
            )
        try:
            capture = paypal.get_capture(transaction.gateway_reference)
        except paypal.PayPalError as exc:
            return ReconciliationResult('unresolved', str(exc))
        status = str(capture.get('status', '')).upper()
        if status == 'COMPLETED':
            return ReconciliationResult('completed', payload=capture)
        if status in {'DECLINED', 'FAILED', 'REFUNDED', 'REVERSED'}:
            return ReconciliationResult('failed', f'PayPal reports {status}.', capture)
        return ReconciliationResult('pending', f'PayPal reports {status or "unknown"}.', capture)

    # PayFast has no merchant-status lookup in the current integration. Its authenticated ITN remains authoritative.
    return ReconciliationResult(
        'unresolved',
        'PayFast status lookup is unavailable; await a verified ITN or operator reconciliation.',
    )


def _order_abandoned(transaction: PaymentTransaction) -> bool:
    """Past the point where we would still accept a capture for this checkout (the capture endpoint enforces the same hold)."""
    if transaction.booking_id:
        return not hold_is_live(transaction.booking)
    return timezone.now() - transaction.created_at > UNPAID_CREDIT_ORDER_MAX_AGE


def _query_paypal_order(transaction: PaymentTransaction) -> ReconciliationResult:
    """Orders v2: ask PayPal for the order. Authoritative failure only: a declined capture, a voided order, or an unpaid order past the hold."""
    try:
        order = paypal.get_order(transaction.gateway_order_id)
    except paypal.PayPalError as exc:
        return ReconciliationResult('unresolved', str(exc))
    capture = paypal.extract_capture(order)
    status = str(order.get('status', '')).upper()
    if capture is not None:
        outcome = paypal.classify_capture(capture)
        if outcome.state == 'completed':
            return ReconciliationResult('completed', payload=order)
        if outcome.state in ('declined', 'failed'):
            return ReconciliationResult('failed', f"PayPal reports capture {capture.get('status')}.", order)
        return ReconciliationResult('pending', f"PayPal reports capture {capture.get('status')} ({outcome.reason}).", order)
    if status == 'VOIDED':
        return ReconciliationResult('failed', 'PayPal reports the order VOIDED.', order)
    if status in UNPAID_ORDER_STATUSES:
        if _order_abandoned(transaction):
            return ReconciliationResult('failed', f'PayPal order still {status}, unpaid past the hold.', order)
        return ReconciliationResult('pending', f'PayPal order {status}; checkout still inside its hold.', order, track=False)
    return ReconciliationResult('unresolved', f'PayPal order is {status or "unknown"} but has no capture.', order)


def _apply_order_result(transaction: PaymentTransaction, result: ReconciliationResult) -> ReconciliationResult:
    """Apply what the order lookup found. Anything that cannot be verified is left INITIALIZED for a human (never guessed)."""
    order = result.payload or {}
    if result.state not in ('completed', 'pending'):
        return result
    capture = paypal.extract_capture(order)
    if capture is None:
        return result
    if capture.get('custom_id') != transaction.merchant_reference:
        record_anomaly('paypal', capture.get('id'), 'capture_reference_mismatch',
                       f"order {transaction.gateway_order_id}: custom_id {capture.get('custom_id')} != {transaction.merchant_reference}",
                       tx=transaction, payload=order)
        return ReconciliationResult('unresolved', 'capture does not belong to this checkout', order)
    try:
        verify_capture_amount(transaction, capture, payload=order)
        if result.state == 'completed':
            settle_completed_capture(transaction.pk, capture, payload=order)
        else:
            record_pending_capture(transaction.pk, capture, paypal.classify_capture(capture), order)
    except CaptureRejected as exc:
        return ReconciliationResult('unresolved', f'capture rejected: {exc.reason}', order)
    return result


def reconcile_pending_capture(transaction: PaymentTransaction, *, lookup=None) -> ReconciliationResult:
    """
    Resolve a PENDING_CAPTURE transaction from PayPal's own record of its capture: COMPLETED goes through the same verified
    settle path as the webhook (grace bookings upgrade, normal ones confirm), DECLINED/FAILED/REVERSED run the failure
    runbook, anything else stays pending. Provider errors change nothing.
    """
    from apps.payments.services import grace
    lookup = lookup or query_gateway
    result = lookup(transaction)
    if result.state == 'completed':
        payload = result.payload or {}
        # The lookup may return the whole order (Orders v2) or a bare capture (legacy rows): normalise to the capture.
        capture = paypal.extract_capture(payload) or dict(payload)
        capture = {**capture, 'id': capture.get('id') or transaction.gateway_reference}
        try:
            verify_capture_amount(transaction, capture, payload=payload)
            settle_completed_capture(transaction.pk, capture, payload=payload)
        except CaptureRejected as exc:
            return ReconciliationResult('unresolved', f'PayPal capture could not be applied: {exc.reason}', result.payload)
    elif result.state == 'failed':
        grace.on_failed(transaction)
    PaymentTransaction.objects.filter(pk=transaction.pk).update(
        reconciliation_attempts=transaction.reconciliation_attempts + 1, last_reconciled_at=timezone.now())
    return result


def reconcile_initialized_transaction(transaction: PaymentTransaction, *, lookup=None) -> ReconciliationResult:
    lookup = lookup or query_gateway
    result = lookup(transaction)
    if transaction.gateway == PaymentTransaction.Gateway.PAYPAL and transaction.gateway_order_id:
        result = _apply_order_result(transaction, result)
    elif result.state == 'completed':
        payload = result.payload or {}
        amount_info = payload.get('amount') or {}
        fee_info = (payload.get('seller_receivable_breakdown') or {}).get('paypal_fee') or {}
        from apps.payments.services.webhook_handler import process_payment_webhook
        process_payment_webhook(
            booking_id=str(transaction.booking_id) if transaction.booking_id else None,
            credit_purchase_id=str(transaction.credit_purchase_id) if transaction.credit_purchase_id else None,
            gateway=transaction.gateway,
            transaction_id=transaction.gateway_reference,
            amount=amount_info.get('value', transaction.amount),
            currency=amount_info.get('currency_code', transaction.currency),
            status=PaymentTransaction.Status.SUCCESS,
            raw_payload=payload,
            provider_fee_amount=fee_info.get('value'),
            provider_fee_currency=fee_info.get('currency_code', ''),
        )
    transaction.reconciliation_attempts += 1
    transaction.last_reconciled_at = timezone.now()
    update_fields = ['reconciliation_attempts', 'last_reconciled_at', 'updated_at']
    if result.state == 'failed':
        # The object was loaded earlier in a batch: re-read it under a lock and only fail a row that is STILL unpaid, so a
        # capture/webhook that settled or parked it in between is never overwritten.
        with db_transaction.atomic():
            fresh = PaymentTransaction.objects.select_for_update().get(pk=transaction.pk)
            if fresh.status == PaymentTransaction.Status.INITIALIZED:
                transaction.status = PaymentTransaction.Status.FAILED
                update_fields.append('status')
                if transaction.credit_purchase_id:
                    transaction.credit_purchase.status = transaction.credit_purchase.Status.FAILED
                    transaction.credit_purchase.save(update_fields=['status', 'updated_at'])
            else:
                result = ReconciliationResult('pending', f'row is {fresh.status}; not failing it', result.payload, track=False)
            transaction.save(update_fields=update_fields)
    else:
        transaction.save(update_fields=update_fields)

    if result.state in {'unresolved', 'pending'} and result.track:
        GatewayAnomaly.objects.get_or_create(
            gateway=transaction.gateway,
            reference=transaction.gateway_reference,
            reason='reconciliation_unresolved',
            resolved=False,
            defaults={
                'detail': result.detail,
                'booking': transaction.booking,
                'payment_transaction': transaction,
                'payload': result.payload or {},
            },
        )
    elif result.state in {'completed', 'failed'}:
        GatewayAnomaly.objects.filter(
            payment_transaction=transaction,
            reason='reconciliation_unresolved',
            resolved=False,
        ).update(resolved=True)
    return result
