"""
Returning a student's money (Task 9.6, decision D-6: refunds go back through the payment gateway).

Two steps, both on the ledger, so "refund decided" and "refund paid" can never be confused:

    decision   DR 2010 student escrow     CR 2050 refunds payable      (also settles the booking: the tutor is not paid)
    paid       DR 2050 refunds payable    CR 1010/1020 gateway cash    (when the gateway has really returned the money)

While a refund is still pending the student may turn it into wallet credit instead (DR 2050, CR 2040). A booking with no
captured payment (legacy or credit-funded rows) has nothing to send back to a gateway, so it gets a wallet lot straight away.

The gateway itself is a plug-in (`settings.REFUND_GATEWAY_BACKEND`): until Task 10.7 the default leaves requests pending
for a person to process in the sandbox.
"""
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.module_loading import import_string

from apps.payments.models import CreditBundle, LedgerAccount, LedgerEntry, PaymentTransaction, RefundRequest
from apps.payments.services.credits import grant_credit
from apps.payments.services.ledger_service import record_journal_entries
from apps.payments.services.settlement import is_settled, successful_transaction

logger = logging.getLogger(__name__)
EV = LedgerEntry.EventType
DR, CR = LedgerEntry.EntryType.DEBIT, LedgerEntry.EntryType.CREDIT


class RefundStateError(Exception):
    """The refund is not in a state that allows that change (already paid, converted, ...)."""


class AlreadySettled(Exception):
    """The booking's escrow was already settled by another path; refunding it as well would pay out twice."""


@dataclass
class RefundOutcome:
    refund: Optional[RefundRequest] = None          # a gateway refund was queued
    credit_lot: Optional[CreditBundle] = None       # or the student was given wallet credit straight away


class ManualSandboxRefundGateway:
    """Default backend: does nothing, so requests wait for a human (sandbox) until Task 10.7 plugs in PayPal / PayFast."""
    def refund(self, request: RefundRequest) -> Optional[str]:
        return None


def _gateway_cash_account(tx: PaymentTransaction) -> str:
    if tx.gateway == PaymentTransaction.Gateway.PAYFAST or tx.currency.upper() == 'ZAR':
        return LedgerAccount.ASSET_GATEWAY_PAYFAST
    return LedgerAccount.ASSET_GATEWAY_PAYPAL


def request_refund(booking, reason: str, *, event_type: str = EV.REFUND_ISSUED, dispute_case=None,
                   description: str = '') -> RefundOutcome:
    """
    Settle `booking`'s escrow back to the student. Idempotent per (booking, reason). Raises AlreadySettled when some other
    outcome already settled the escrow. Call inside the transaction that changed the booking's status.
    """
    existing = RefundRequest.objects.filter(booking=booking, reason=reason).first()
    if existing:
        return RefundOutcome(refund=existing)
    if is_settled(booking):
        raise AlreadySettled(f"Booking {booking.id} is already settled.")

    note = description or dict(RefundRequest.Reason.choices).get(reason, reason)
    paid = successful_transaction(booking)
    with transaction.atomic():
        if paid is None:
            price = Decimal(str(booking.teacher.price_per_25min_usd)).quantize(Decimal('0.01'))
            lot = grant_credit(booking.student, source=CreditBundle.Source.REFUND, pack_name=f'Refund: {note}'[:64],
                               unit_value=price, currency='USD')
            record_journal_entries(
                entries=[
                    {'account': LedgerAccount.LIABILITY_STUDENT_ESCROW, 'entry_type': DR, 'amount': price,
                     'description': f"Escrow released, nothing captured to return: {note}"},
                    {'account': LedgerAccount.LIABILITY_STUDENT_WALLET, 'entry_type': CR, 'amount': price,
                     'description': f"Wallet credit for {note}"},
                ],
                event_type=event_type, description=f"{note} (wallet credit) for booking {booking.id}",
                booking=booking, dispute_case=dispute_case, user=booking.student, currency='USD')
            return RefundOutcome(credit_lot=lot)

        amount = Decimal(str(paid.amount)).quantize(Decimal('0.01'))
        refund = RefundRequest.objects.create(
            booking=booking, payment_transaction=paid, user=booking.student, amount=amount,
            currency=paid.currency.upper(), reason=reason)
        record_journal_entries(
            entries=[
                {'account': LedgerAccount.LIABILITY_STUDENT_ESCROW, 'entry_type': DR, 'amount': amount, 'currency': refund.currency,
                 'description': f"Escrow released to the student: {note}"},
                {'account': LedgerAccount.LIABILITY_REFUNDS_PAYABLE, 'entry_type': CR, 'amount': amount, 'currency': refund.currency,
                 'description': f"Gateway refund owed to the student: {note}"},
            ],
            event_type=event_type, description=f"{note}: gateway refund queued for booking {booking.id}",
            booking=booking, payment_transaction=paid, dispute_case=dispute_case, user=booking.student,
            currency=refund.currency)
        return RefundOutcome(refund=refund)


def mark_processed(refund_id, gateway_reference: str) -> RefundRequest:
    """The gateway returned the money: post the cash movement. Safe to repeat."""
    with transaction.atomic():
        refund = RefundRequest.objects.select_for_update().select_related('payment_transaction', 'booking').get(pk=refund_id)
        if refund.status == RefundRequest.Status.PROCESSED:
            return refund
        if refund.status not in (RefundRequest.Status.PENDING_GATEWAY, RefundRequest.Status.FAILED):
            raise RefundStateError(f"Refund {refund.pk} is {refund.status}; it cannot be paid out.")
        tx = refund.payment_transaction
        record_journal_entries(
            entries=[
                {'account': LedgerAccount.LIABILITY_REFUNDS_PAYABLE, 'entry_type': DR, 'amount': refund.amount, 'currency': refund.currency,
                 'description': f"Gateway refund paid, ref {gateway_reference}"},
                {'account': _gateway_cash_account(tx), 'entry_type': CR, 'amount': refund.amount, 'currency': refund.currency,
                 'description': f"Refund returned to the original payment method via {tx.gateway.upper()}"},
            ],
            event_type=EV.GATEWAY_REFUND_PAID, description=f"Gateway refund {gateway_reference} for booking {refund.booking_id}",
            booking=refund.booking, payment_transaction=tx, user=refund.user, currency=refund.currency)
        refund.status = RefundRequest.Status.PROCESSED
        refund.gateway_reference = gateway_reference[:255]
        refund.failure_detail = ''
        refund.processed_at = timezone.now()
        refund.save(update_fields=['status', 'gateway_reference', 'failure_detail', 'processed_at', 'updated_at'])
        tx.status = PaymentTransaction.Status.REFUNDED
        tx.save(update_fields=['status', 'updated_at'])
        return refund


def mark_failed(refund_id, detail: str) -> RefundRequest:
    with transaction.atomic():
        refund = RefundRequest.objects.select_for_update().get(pk=refund_id)
        if refund.status != RefundRequest.Status.PENDING_GATEWAY:
            raise RefundStateError(f"Refund {refund.pk} is {refund.status}; it cannot be marked failed.")
        refund.status = RefundRequest.Status.FAILED
        refund.failure_detail = detail[:2000]
        refund.save(update_fields=['status', 'failure_detail', 'updated_at'])
        return refund


def convert_to_wallet(refund_id) -> CreditBundle:
    """The student prefers lesson credit to waiting for the gateway. Only while the refund is still pending."""
    with transaction.atomic():
        refund = RefundRequest.objects.select_for_update().select_related('booking', 'user').get(pk=refund_id)
        if refund.status != RefundRequest.Status.PENDING_GATEWAY:
            raise RefundStateError(f"Refund {refund.pk} is {refund.status}; only a pending refund can become wallet credit.")
        lot = grant_credit(refund.user, source=CreditBundle.Source.REFUND, pack_name='Refund converted to credit',
                           unit_value=refund.amount, currency=refund.currency)
        record_journal_entries(
            entries=[
                {'account': LedgerAccount.LIABILITY_REFUNDS_PAYABLE, 'entry_type': DR, 'amount': refund.amount, 'currency': refund.currency,
                 'description': "Refund converted to wallet credit at the student's request"},
                {'account': LedgerAccount.LIABILITY_STUDENT_WALLET, 'entry_type': CR, 'amount': refund.amount, 'currency': refund.currency,
                 'description': "Wallet credit from converted refund"},
            ],
            event_type=EV.REFUND_ISSUED, description=f"Refund {refund.pk} converted to wallet credit",
            booking=refund.booking, payment_transaction=refund.payment_transaction, user=refund.user, currency=refund.currency)
        refund.status = RefundRequest.Status.CONVERTED
        refund.processed_at = timezone.now()
        refund.save(update_fields=['status', 'processed_at', 'updated_at'])
        return lot


def process_pending_refunds() -> dict:
    """Hand every pending refund to the configured gateway. A gateway error is recorded on the refund (and logged), never hidden."""
    gateway = import_string(settings.REFUND_GATEWAY_BACKEND)()
    done = {'processed': 0, 'failed': 0, 'pending': 0}
    for pk in list(RefundRequest.objects.filter(status=RefundRequest.Status.PENDING_GATEWAY).values_list('pk', flat=True)):
        refund = RefundRequest.objects.get(pk=pk)
        try:
            reference = gateway.refund(refund)
        except Exception as exc:                                    # recorded on the refund, not swallowed
            logger.error("[REFUND] Gateway failed for refund %s: %s", pk, exc)
            mark_failed(pk, f"{type(exc).__name__}: {exc}")
            done['failed'] += 1
            continue
        if reference:
            mark_processed(pk, reference)
            done['processed'] += 1
        else:
            done['pending'] += 1
    return done
