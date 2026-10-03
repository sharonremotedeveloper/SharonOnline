"""
Returning a student's money (Task 9.6, decision D-6: refunds go back through the payment gateway).

What is refunded, and in which currency, comes from the booking's immutable `BookingFunding` record - never from the current list
price. A booking with no funding record cannot be refunded (`MissingFunding`; an anomaly is recorded for finance).

Gateway-funded lessons - two steps, both on the ledger, so "refund decided" and "refund paid" cannot be confused:

    decision   DR 2010 student escrow     CR 2050 refunds payable      (also settles the booking: the tutor is not paid)
    paid       DR 2050 refunds payable    CR 1010/1020 gateway cash    (when the gateway has really returned the money)

While a refund is pending the student may turn it into wallet credit instead (DR 2050, CR 2040).
Credit-funded lessons have no gateway money to return: the credit is restored as a new lot (DR 2010, CR 2040).

The gateway itself is a plug-in (`settings.REFUND_GATEWAY_BACKEND`): until Task 10.7 the default leaves requests pending
for a person to process in the sandbox.
"""
import logging
from dataclasses import dataclass
from typing import Optional

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.module_loading import import_string

from apps.payments.models import (BookingFunding, CreditBundle, CreditWalletEntry, LedgerAccount, LedgerEntry,
                                  PaymentTransaction, RefundRequest)
from apps.payments.services.credits import grant_credit
from apps.payments.services.funding import funding_for_settlement
from apps.payments.services.ledger_service import record_journal_entries
from apps.payments.services.settlement import is_settled

logger = logging.getLogger(__name__)
EV = LedgerEntry.EventType
DR, CR = LedgerEntry.EntryType.DEBIT, LedgerEntry.EntryType.CREDIT


class RefundStateError(Exception):
    """The refund is not in a state that allows that change (already paid, converted, ...)."""


class AlreadySettled(Exception):
    """The booking's escrow was already settled by another path; refunding it as well would pay out twice."""


class MissingFunding(Exception):
    """The booking has no payment or credit provenance, so there is nothing safe to refund (an anomaly was recorded)."""


@dataclass
class RefundOutcome:
    refund: Optional[RefundRequest] = None          # a gateway refund was queued
    credit_lot: Optional[CreditBundle] = None       # or the student's credit was restored (credit-funded lesson)


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
    outcome already settled the escrow, MissingFunding when there is no funding record. Call inside the transaction that
    changed the booking's status.
    """
    existing = RefundRequest.objects.filter(booking=booking, reason=reason).first()
    if existing:
        return RefundOutcome(refund=existing)
    if is_settled(booking):
        raise AlreadySettled(f"Booking {booking.id} is already settled.")
    funding = funding_for_settlement(booking, context=f'refund:{reason}')
    if funding is None:
        raise MissingFunding(f"Booking {booking.id} has no funding provenance.")

    note = description or dict(RefundRequest.Reason.choices).get(reason, reason)
    amount, currency = funding.captured_amount, funding.currency.upper()
    fx = dict(fx_rate_to_zar=funding.fx_rate_to_zar, fx_source=funding.fx_source)
    if funding.source_type == BookingFunding.SourceType.PLATFORM_ABSORBED:
        # The pending payment failed: the student never paid, so there is nothing to give back.
        logger.info("[REFUND] Booking %s: payment never cleared, no refund owed (%s).", booking.id, reason)
        return RefundOutcome()
    if (funding.source_type == BookingFunding.SourceType.GATEWAY_PENDING
            and funding.payment_transaction.status == PaymentTransaction.Status.FAILED):
        logger.info("[REFUND] Booking %s: its pending payment already failed, no refund owed (%s).", booking.id, reason)
        return RefundOutcome()
    if funding.source_type == BookingFunding.SourceType.GATEWAY_PENDING:
        # Grace booking cancelled/refundable before PayPal cleared the payment: no money has arrived, so NO ledger entry
        # and no gateway refund yet. The obligation is recorded and becomes a real refund only if the payment clears
        # (`activate_deferred_refunds`); it is voided if the payment fails (`void_deferred_refunds`).
        refund, _ = RefundRequest.objects.get_or_create(
            booking=booking, reason=reason,
            defaults={'payment_transaction': funding.payment_transaction, 'user': booking.student, 'amount': amount,
                      'currency': currency, 'status': RefundRequest.Status.AWAITING_CLEARANCE})
        return RefundOutcome(refund=refund)
    with transaction.atomic():
        if funding.source_type == BookingFunding.SourceType.CREDIT:
            lot = grant_credit(booking.student, source=CreditBundle.Source.REFUND, pack_name=f'Refund: {note}'[:64],
                               unit_amount=amount, currency=currency, entry_type=CreditWalletEntry.EntryType.REFUND,
                               booking=booking, idempotency_key=f'refund:{booking.id}:{reason}', **fx)
            record_journal_entries(
                entries=[
                    {'account': LedgerAccount.LIABILITY_STUDENT_ESCROW, 'entry_type': DR, 'amount': amount, 'currency': currency,
                     'description': f"Escrow released, credit restored: {note}"},
                    {'account': LedgerAccount.LIABILITY_STUDENT_WALLET, 'entry_type': CR, 'amount': amount, 'currency': currency,
                     'description': f"Credit restored to the wallet: {note}"},
                ],
                event_type=event_type, description=f"{note} (credit restored) for booking {booking.id}",
                booking=booking, dispute_case=dispute_case, user=booking.student, currency=currency, **fx)
            return RefundOutcome(credit_lot=lot)

        paid = funding.payment_transaction
        refund = RefundRequest.objects.create(
            booking=booking, payment_transaction=paid, user=booking.student, amount=amount,
            currency=currency, reason=reason)
        record_journal_entries(
            entries=[
                {'account': LedgerAccount.LIABILITY_STUDENT_ESCROW, 'entry_type': DR, 'amount': amount, 'currency': currency,
                 'description': f"Escrow released to the student: {note}"},
                {'account': LedgerAccount.LIABILITY_REFUNDS_PAYABLE, 'entry_type': CR, 'amount': amount, 'currency': currency,
                 'description': f"Gateway refund owed to the student: {note}"},
            ],
            event_type=event_type, description=f"{note}: gateway refund queued for booking {booking.id}",
            booking=booking, payment_transaction=paid, dispute_case=dispute_case, user=booking.student,
            currency=currency, **fx)
        return RefundOutcome(refund=refund)


_EVENT_FOR_REASON = {
    RefundRequest.Reason.OUTAGE: EV.OUTAGE_REFUND,
    RefundRequest.Reason.DISPUTE: EV.DISPUTE_RESOLVED,
}


def activate_deferred_refunds(booking) -> int:
    """
    The pending payment cleared (its capture journal is already posted, so escrow holds the money): turn every refund that
    was waiting on it into a real one (DR 2010, CR 2050), exactly as `request_refund` would have. Idempotent.
    """
    funding = BookingFunding.objects.get(booking=booking)
    fx = dict(fx_rate_to_zar=funding.fx_rate_to_zar, fx_source=funding.fx_source)
    done = 0
    with transaction.atomic():
        waiting = (RefundRequest.objects.select_for_update()
                   .filter(booking=booking, status=RefundRequest.Status.AWAITING_CLEARANCE))
        for refund in waiting:
            record_journal_entries(
                entries=[
                    {'account': LedgerAccount.LIABILITY_STUDENT_ESCROW, 'entry_type': DR, 'amount': refund.amount,
                     'currency': refund.currency, 'description': "Escrow released to the student: payment cleared after cancellation"},
                    {'account': LedgerAccount.LIABILITY_REFUNDS_PAYABLE, 'entry_type': CR, 'amount': refund.amount,
                     'currency': refund.currency, 'description': "Gateway refund owed to the student: payment cleared after cancellation"},
                ],
                event_type=_EVENT_FOR_REASON.get(refund.reason, EV.REFUND_ISSUED),
                description=f"Deferred refund ({refund.reason}) activated: gateway refund queued for booking {booking.id}",
                booking=booking, payment_transaction=refund.payment_transaction, user=booking.student,
                currency=refund.currency, **fx)
            refund.status = RefundRequest.Status.PENDING_GATEWAY
            refund.save(update_fields=['status', 'updated_at'])
            done += 1
    return done


def void_deferred_refunds(booking) -> int:
    """The pending payment failed: no money ever arrived, so the refunds that were waiting on it are not owed."""
    return RefundRequest.objects.filter(
        booking=booking, status=RefundRequest.Status.AWAITING_CLEARANCE
    ).update(status=RefundRequest.Status.VOID, failure_detail='The payment never cleared; nothing was collected.',
             updated_at=timezone.now())


def _fx_of(refund) -> dict:
    funding = BookingFunding.objects.filter(booking_id=refund.booking_id).first()
    return dict(fx_rate_to_zar=funding.fx_rate_to_zar, fx_source=funding.fx_source) if funding else {}


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
            booking=refund.booking, payment_transaction=tx, user=refund.user, currency=refund.currency, **_fx_of(refund))
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
        fx = _fx_of(refund)
        lot = grant_credit(refund.user, source=CreditBundle.Source.REFUND, pack_name='Refund converted to credit',
                           unit_amount=refund.amount, currency=refund.currency, entry_type=CreditWalletEntry.EntryType.REFUND,
                           booking=refund.booking, idempotency_key=f'convert-refund:{refund.pk}', **fx)
        record_journal_entries(
            entries=[
                {'account': LedgerAccount.LIABILITY_REFUNDS_PAYABLE, 'entry_type': DR, 'amount': refund.amount, 'currency': refund.currency,
                 'description': "Refund converted to wallet credit at the student's request"},
                {'account': LedgerAccount.LIABILITY_STUDENT_WALLET, 'entry_type': CR, 'amount': refund.amount, 'currency': refund.currency,
                 'description': "Wallet credit from converted refund"},
            ],
            event_type=EV.REFUND_ISSUED, description=f"Refund {refund.pk} converted to wallet credit",
            booking=refund.booking, payment_transaction=refund.payment_transaction, user=refund.user,
            currency=refund.currency, **fx)
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
