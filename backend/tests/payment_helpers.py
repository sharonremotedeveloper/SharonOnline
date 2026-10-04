"""Shared builders for payment / refund tests: a lesson, a lesson that was really paid through the webhook handler, a ledger net.

A plain module (not a test file) so no test module has to import another test module.
"""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from apps.bookings.models import Booking
from apps.payments.models import LedgerEntry, PaymentTransaction
from apps.payments.services.funding import ensure_gateway_funding
from apps.payments.services.webhook_handler import process_payment_webhook

S = Booking.Status
MIN = timedelta(minutes=1)


def lesson(teacher, student, start_in_min, status=S.PENDING_PAYMENT):
    start = timezone.now() + start_in_min * MIN
    booking = Booking.objects.create(teacher=teacher, student=student, start_time_utc=start,
                                     end_time_utc=start + 25 * MIN, status=status)
    if status != S.PENDING_PAYMENT:
        tx = PaymentTransaction.objects.create(
            booking=booking, gateway='paypal', gateway_reference=f'TEST-{booking.id}',
            amount=Decimal('9.00'), currency='USD', status='success')
        ensure_gateway_funding(tx, booking)
    return booking


def captured(teacher, student, start_in_min, *, gateway='payfast', amount='168.75', currency='ZAR', ref='CAP-1'):
    """A booking that was really paid through the webhook handler (ledger capture entry included)."""
    booking = lesson(teacher, student, start_in_min)
    PaymentTransaction.objects.create(booking=booking, gateway=gateway, gateway_reference=f"INIT-{ref}",
                                      merchant_reference=ref, amount=amount, currency=currency)
    process_payment_webhook(booking_id=str(booking.id), gateway=gateway, transaction_id=f"GW-{ref}",
                            amount=Decimal(amount), currency=currency, status='success', raw_payload={})
    booking.refresh_from_db()
    assert booking.status == S.CONFIRMED
    return booking


def net(booking, account):
    """credit - debit on one ledger account for one booking, in the entries' own currency."""
    rows = LedgerEntry.objects.filter(booking=booking, account=account)
    cr = rows.filter(entry_type=LedgerEntry.EntryType.CREDIT).aggregate(t=Sum('amount'))['t'] or Decimal('0')
    dr = rows.filter(entry_type=LedgerEntry.EntryType.DEBIT).aggregate(t=Sum('amount'))['t'] or Decimal('0')
    return cr - dr
