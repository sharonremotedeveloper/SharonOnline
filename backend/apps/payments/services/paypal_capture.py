"""
Verified application of a PayPal capture. Used by BOTH the webhook and the capture endpoint (Task 10.2), so a booking
is only ever confirmed through one locked, idempotent path, and only after the amount was re-read from PayPal itself.
"""
import logging
from decimal import Decimal

from django.db import transaction

from apps.payments.models import PaymentTransaction
from apps.payments.services.anomalies import record_anomaly
from apps.payments.services.pricing import quantize_money
from apps.payments.services.webhook_handler import process_payment_webhook, record_unallocated_payment

logger = logging.getLogger(__name__)

SETTLED_STATES = (PaymentTransaction.Status.SUCCESS, PaymentTransaction.Status.UNALLOCATED)


class CaptureRejected(Exception):
    """The capture cannot be applied to this transaction (the caller decides the HTTP response)."""

    def __init__(self, reason: str, **context):
        super().__init__(reason)
        self.reason = reason
        self.context = context


def verify_capture_amount(tx: PaymentTransaction, capture: dict, *, payload: dict) -> None:
    """The amount and currency PayPal reports must equal what we asked for; otherwise an anomaly is recorded."""
    amount_info = capture.get('amount') or {}
    try:
        paid = Decimal(str(amount_info.get('value', '')))
    except Exception:
        raise CaptureRejected('unparseable_amount') from None
    if amount_info.get('currency_code') != tx.currency or quantize_money(paid, tx.currency) != quantize_money(tx.amount, tx.currency):
        record_anomaly('paypal', capture.get('id'), 'amount_mismatch',
                       f"expected {tx.amount} {tx.currency}, PayPal says {paid} {amount_info.get('currency_code')}",
                       tx=tx, payload=payload)
        raise CaptureRejected('amount_mismatch', expected=f'{tx.amount} {tx.currency}',
                              got=f"{paid} {amount_info.get('currency_code')}")


def _bind_gateway_reference(tx: PaymentTransaction, gateway_reference: str, raw_payload: dict) -> bool:
    if tx.gateway_reference != gateway_reference:
        if PaymentTransaction.objects.filter(gateway_reference=gateway_reference).exclude(pk=tx.pk).exists():
            return False
        tx.gateway_reference = gateway_reference
    tx.raw_webhook_payload = raw_payload
    tx.save(update_fields=['gateway_reference', 'raw_webhook_payload', 'updated_at'])
    return True


def settle_completed_capture(tx_pk, capture: dict, *, payload: dict) -> str:
    """
    Apply a COMPLETED, amount-verified capture under a row lock. Returns 'settled' or 'duplicate'; raises
    CaptureRejected('gateway_reference_reused') when the capture id already belongs to another transaction.
    """
    capture_id = capture.get('id')
    reference = capture.get('custom_id')
    fee = (capture.get('seller_receivable_breakdown') or {}).get('paypal_fee') or {}
    with transaction.atomic():
        tx = PaymentTransaction.objects.select_for_update(of=('self',)).select_related('booking').get(pk=tx_pk)
        if tx.status in SETTLED_STATES:
            if tx.gateway_reference == capture_id:
                return 'duplicate'
            if tx.credit_purchase_id:
                record_anomaly('paypal', capture_id, 'duplicate_credit_purchase_capture',
                               f'purchase {tx.credit_purchase_id} already settled by {tx.gateway_reference}',
                               tx=tx, payload=payload)
                return 'duplicate'
            # A DIFFERENT capture against an already-settled order reference: hold for refund, never drop silently.
            record_unallocated_payment(
                booking=tx.booking, gateway=PaymentTransaction.Gateway.PAYPAL, transaction_id=capture_id,
                amount=tx.amount, currency=tx.currency, raw_payload=payload, reason='duplicate_payment',
                detail=f"custom_id {reference} already settled by {tx.gateway_reference}")
            return 'duplicate'
        if not _bind_gateway_reference(tx, capture_id, payload):
            record_anomaly('paypal', capture_id, 'gateway_reference_reused', f'custom_id={reference}',
                           tx=tx, payload=payload)
            raise CaptureRejected('gateway_reference_reused', capture_id=capture_id)
        process_payment_webhook(
            booking_id=str(tx.booking_id) if tx.booking_id else None,
            credit_purchase_id=str(tx.credit_purchase_id) if tx.credit_purchase_id else None,
            gateway=PaymentTransaction.Gateway.PAYPAL,
            transaction_id=capture_id, amount=tx.amount, currency=tx.currency,
            status=PaymentTransaction.Status.SUCCESS, raw_payload=payload,
            provider_fee_amount=fee.get('value'), provider_fee_currency=fee.get('currency_code', ''))
    return 'settled'


def record_pending_capture(tx_pk, capture: dict, outcome, order: dict) -> PaymentTransaction:
    """PayPal accepted the capture but has not guaranteed the money: remember why, and who the payer is."""
    payer = (order or {}).get('payer') or {}
    with transaction.atomic():
        tx = PaymentTransaction.objects.select_for_update().get(pk=tx_pk)
        if tx.status in SETTLED_STATES or tx.status in (PaymentTransaction.Status.FAILED, PaymentTransaction.Status.REFUNDED):
            return tx
        tx.status = PaymentTransaction.Status.PENDING_CAPTURE
        tx.pending_reason = (outcome.reason or '')[:64]
        # Only ever fill or update the payer identity (the per-payer grace cap depends on it); a report without payer data
        # (for example a webhook that cannot re-read the order) must not blank it.
        tx.payer_id = str(payer.get('payer_id') or '')[:64] or tx.payer_id
        tx.payer_email = str(payer.get('email_address') or '')[:254] or tx.payer_email
        capture_id = capture.get('id')
        if capture_id and tx.gateway_reference != capture_id and not PaymentTransaction.objects.filter(
                gateway_reference=capture_id).exclude(pk=tx.pk).exists():
            tx.gateway_reference = capture_id
        tx.raw_webhook_payload = order or capture
        tx.save()
    return tx


def record_failed_capture(tx_pk) -> PaymentTransaction:
    with transaction.atomic():
        tx = PaymentTransaction.objects.select_for_update().get(pk=tx_pk)
        if tx.status in (PaymentTransaction.Status.INITIALIZED, PaymentTransaction.Status.PENDING_CAPTURE):
            tx.status = PaymentTransaction.Status.FAILED
            tx.save(update_fields=['status', 'updated_at'])
    return tx
