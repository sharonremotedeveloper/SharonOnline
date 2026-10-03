from dataclasses import dataclass

from django.utils import timezone

from apps.payments.gateways import paypal
from apps.payments.models import GatewayAnomaly, PaymentTransaction


@dataclass(frozen=True)
class ReconciliationResult:
    state: str
    detail: str = ''
    payload: dict | None = None


def query_gateway(transaction: PaymentTransaction) -> ReconciliationResult:
    """Read provider state without guessing that an old checkout failed."""
    if transaction.gateway == PaymentTransaction.Gateway.PAYPAL:
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


def reconcile_initialized_transaction(transaction: PaymentTransaction, *, lookup=None) -> ReconciliationResult:
    lookup = lookup or query_gateway
    result = lookup(transaction)
    if result.state == 'completed':
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
        transaction.status = PaymentTransaction.Status.FAILED
        update_fields.append('status')
        if transaction.credit_purchase_id:
            transaction.credit_purchase.status = transaction.credit_purchase.Status.FAILED
            transaction.credit_purchase.save(update_fields=['status', 'updated_at'])
    transaction.save(update_fields=update_fields)

    if result.state in {'unresolved', 'pending'}:
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
