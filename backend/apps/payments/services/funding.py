from decimal import Decimal

from django.conf import settings

from apps.payments.models import BookingFunding, PaymentTransaction, SettlementAnomaly


class MissingBookingFunding(RuntimeError):
    pass


def gateway_fx_snapshot(currency: str) -> tuple[Decimal, str]:
    currency = currency.upper()
    if currency == 'ZAR':
        return Decimal('1.000000'), 'transaction_currency'
    if currency == 'USD':
        return Decimal(str(settings.ZAR_PER_USD)), 'configured_checkout_rate'
    raise MissingBookingFunding(f'No approved ZAR valuation source is configured for {currency}.')


def ensure_gateway_funding(payment_transaction: PaymentTransaction, booking) -> BookingFunding:
    """Persist the immutable amount/currency/FX used for a paid lesson."""
    fx_rate = payment_transaction.fx_rate_to_zar
    fx_source = payment_transaction.fx_source
    if fx_rate is None or not fx_source:
        fx_rate, fx_source = gateway_fx_snapshot(payment_transaction.currency)
        payment_transaction.fx_rate_to_zar = fx_rate
        payment_transaction.fx_source = fx_source
        payment_transaction.save(update_fields=['fx_rate_to_zar', 'fx_source', 'updated_at'])
    funding, _ = BookingFunding.objects.get_or_create(
        booking=booking,
        defaults={
            'source_type': BookingFunding.SourceType.GATEWAY,
            'captured_amount': payment_transaction.amount,
            'currency': payment_transaction.currency.upper(),
            'fx_rate_to_zar': fx_rate,
            'fx_source': fx_source,
            'payment_transaction': payment_transaction,
        },
    )
    return funding


def persist_capture_snapshot(payment_transaction: PaymentTransaction) -> tuple[Decimal, str]:
    """Persist exactly one provider/currency valuation snapshot when capture is accepted."""
    if payment_transaction.fx_rate_to_zar is not None and payment_transaction.fx_source:
        return payment_transaction.fx_rate_to_zar, payment_transaction.fx_source
    if payment_transaction.credit_purchase_id:
        purchase = payment_transaction.credit_purchase
        fx_rate, fx_source = purchase.fx_rate_to_zar, purchase.fx_source
    else:
        fx_rate, fx_source = gateway_fx_snapshot(payment_transaction.currency)
    payment_transaction.fx_rate_to_zar = fx_rate
    payment_transaction.fx_source = fx_source
    payment_transaction.save(update_fields=['fx_rate_to_zar', 'fx_source', 'updated_at'])
    return fx_rate, fx_source


def funding_for_settlement(booking, *, context: str) -> BookingFunding | None:
    """Return proven funding or persist an anomaly and stop the settlement path."""
    try:
        return BookingFunding.objects.select_related('payment_transaction', 'credit_wallet_entry').get(booking=booking)
    except BookingFunding.DoesNotExist:
        # Legacy/test rows can still be recovered from an actual captured transaction. Never use list price.
        tx = (PaymentTransaction.objects.filter(booking=booking, status=PaymentTransaction.Status.SUCCESS)
              .order_by('-created_at').first())
        if tx:
            return ensure_gateway_funding(tx, booking)
        SettlementAnomaly.objects.get_or_create(
            booking=booking,
            code='missing_booking_funding',
            resolved=False,
            defaults={'detail': f'{context}: settlement stopped because no payment or credit provenance exists.'},
        )
        return None
