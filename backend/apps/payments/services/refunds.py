"""
Returning a student's money (Task 9.6, decision D-6: refunds go back through the payment gateway).

What is refunded, and in which currency, comes from the booking's immutable `BookingFunding` record - never from the current list
price. A booking with no funding record cannot be refunded (`MissingFunding`; an anomaly is recorded for finance).

Gateway-funded lessons - two steps, both on the ledger, so "refund decided" and "refund paid" cannot be confused:

    decision   DR 2010 student escrow     CR 2050 refunds payable      (also settles the booking: the tutor is not paid)
    paid       DR 2050 refunds payable    CR 1010/1020 gateway cash    (when the gateway has really returned the money)

While a refund is pending the student may turn it into wallet credit instead (DR 2050, CR 2040).
Credit-funded lessons have no gateway money to return: the credit is restored as a new lot (DR 2010, CR 2040).

The gateway itself is a plug-in (`settings.REFUND_GATEWAY_BACKEND`, contract in `refund_gateways.py`). Sending is a
claim / call / apply protocol (Task 10.7, docs/TASK_10_7_REFUND_GATEWAYS_PLAN.md section 2b), built so that money moves AT
MOST once and a crash at any point is recovered by replaying the same request id:

    claim   a compare-and-swap UPDATE stamps a claim token + lease and counts the attempt (portable: SQLite and Postgres)
    call    the gateway is called with NO database lock held
    apply   `apply_result` re-locks (payment, then refund), checks the token (fences a stale worker), writes the outcome and
            exactly one RefundAttempt row

Lock order is always PaymentTransaction then RefundRequest, the same as the PayPal webhook handler.
"""
import logging
import re
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Callable, Iterator, Optional

from django.conf import settings
from django.db import transaction
from django.db.models import Case, DateTimeField, F, Max, Q, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.module_loading import import_string

from apps.payments.models import (BookingFunding, CreditBundle, CreditWalletEntry, GatewayAnomaly, LedgerAccount, LedgerEntry,
                                  PaymentTransaction, RefundAttempt, RefundRequest)
from apps.payments.services.alerts import alert_admin, resolve_alert
from apps.payments.services.credits import grant_credit
from apps.payments.services.funding import funding_for_settlement
from apps.payments.services.ledger_service import gateway_cash_account, record_journal_entries
from apps.payments.services.pricing import quantize_money
from apps.payments.services.refund_gateways import ManualSandboxRefundGateway, RefundOrder, RefundResult  # noqa: F401  (re-exported: the old import path keeps resolving)
from apps.payments.services.settlement import is_settled

logger = logging.getLogger(__name__)
EV = LedgerEntry.EventType
DR, CR = LedgerEntry.EntryType.DEBIT, LedgerEntry.EntryType.CREDIT


class RefundStateError(Exception):
    """The refund is not in a state that allows that change (already paid, converted, ...)."""


class RefundInProgress(RefundStateError):
    """The gateway already has (or may have) this refund: it can no longer be turned into wallet credit."""


class RefundConfirmationRequired(RefundStateError):
    """The failure is ambiguous (the provider may have refunded): retrying needs the admin's confirmation it did not."""


class RefundGuardFailed(RefundStateError):
    """A safety guard still refuses this refund, so a retry would only fail again."""


class AlreadySettled(Exception):
    """The booking's escrow was already settled by another path; refunding it as well would pay out twice."""


class MissingFunding(Exception):
    """The booking has no payment or credit provenance, so there is nothing safe to refund (an anomaly was recorded)."""


@dataclass
class RefundOutcome:
    refund: Optional[RefundRequest] = None          # a gateway refund was queued
    credit_lot: Optional[CreditBundle] = None       # or the student's credit was restored (credit-funded lesson)


def _gateway_cash_account(tx: PaymentTransaction) -> str:
    """The cash account the capture was booked to: the one shared rule in ledger_service (gateway, never currency)."""
    return gateway_cash_account(tx)


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
    was waiting on it into a real one (DR 2010, CR 2050), exactly as `request_refund` would have. Idempotent. The first gateway
    attempt is not due before `REFUND_FIRST_ATTEMPT_DELAY_MINUTES` from NOW (the refund was decided long ago, but the money only
    arrived now), so the student's window to take wallet credit instead restarts when the money is really there.
    """
    funding = BookingFunding.objects.get(booking=booking)
    fx = dict(fx_rate_to_zar=funding.fx_rate_to_zar, fx_source=funding.fx_source)
    done = 0
    with transaction.atomic():
        first_attempt_at = _now() + _first_attempt_delay()
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
            refund.next_attempt_at = first_attempt_at
            refund.save(update_fields=['status', 'next_attempt_at', 'updated_at'])
            done += 1
    return done


def void_deferred_refunds(booking) -> int:
    """The pending payment failed: no money ever arrived, so the refunds that were waiting on it are not owed."""
    return RefundRequest.objects.filter(
        booking=booking, status=RefundRequest.Status.AWAITING_CLEARANCE
    ).update(status=RefundRequest.Status.VOID, failure_detail='The payment never cleared; nothing was collected.',
             updated_at=timezone.now())




# ================================================================================================ protocol constants
RS = RefundRequest.Status
FK = RefundRequest.FailureKind

CAPTURE_REF_RE = re.compile(r'[A-Za-z0-9_-]{5,64}')          # matched with fullmatch(): no trailing-newline loophole
BACKOFF = (timedelta(minutes=15), timedelta(hours=1), timedelta(hours=4), timedelta(hours=12), timedelta(hours=24))
MANUAL_RECHECK = timedelta(hours=6)                           # a manual backend is looked at again this often, burning no attempt
BREAKER_THRESHOLD = 3                                         # consecutive transient / provider-level results that stop a gateway for a sweep
SUBMITTED_STALE_AFTER = timedelta(days=14)
CANDIDATE_CAP = 1000
AMBIGUOUS_KINDS = (FK.EXHAUSTED, FK.REPLAY_WINDOW, FK.ALREADY_REFUNDED, '')     # the provider may already have refunded: a human must confirm
SEND, POLL = 'send', 'poll'
_REFUND_ALERT_CODES = tuple(f'refund_failed_{kind}' for kind in FK.values) + ('refund_manual_waiting', 'refund_submitted_stale',
                                                                                'refund_capture_not_found')
NOT_FOUND_ALERT_AFTER = 3                                     # straight 404 answers from the provider before a person is told about THAT refund


def _now():
    """The clock of this module (tests replace it to walk through backoff and windows)."""
    return timezone.now()


def _monotonic() -> float:
    return time.monotonic()


@dataclass(frozen=True)
class RefundClaim:
    refund_id: str
    token: str
    kind: str                    # 'send' (call the gateway) or 'poll' (look a submitted refund up)
    order: RefundOrder


# ================================================================================================ locking helpers
def _lock_pair(refund_id, *, skip_locked: bool = False):
    """
    Lock the PaymentTransaction, THEN the RefundRequest (the webhook handler's order, so the two can never deadlock).
    With `skip_locked` a payment someone else holds is skipped: (None, None). Must run inside transaction.atomic().
    """
    tx_id = RefundRequest.objects.filter(pk=refund_id).values_list('payment_transaction_id', flat=True).first()
    if tx_id is None:
        raise RefundRequest.DoesNotExist(f"Refund {refund_id} does not exist.")
    locked = PaymentTransaction.objects.select_for_update(skip_locked=True) if skip_locked else PaymentTransaction.objects.select_for_update()
    tx = locked.filter(pk=tx_id).first()
    if tx is None:
        if skip_locked:
            return None, None
        raise PaymentTransaction.DoesNotExist(f"Payment {tx_id} does not exist.")
    return tx, RefundRequest.objects.select_for_update().get(pk=refund_id)


def _fx_of(refund) -> dict:
    funding = BookingFunding.objects.filter(booking_id=refund.booking_id).first()
    return dict(fx_rate_to_zar=funding.fx_rate_to_zar, fx_source=funding.fx_source) if funding else {}


def _clear_claim(refund) -> None:
    refund.claim_token = ''
    refund.claimed_until = None


def _resolve_refund_alerts(refund) -> None:
    for code in _REFUND_ALERT_CODES:
        resolve_alert(code, str(refund.pk))


def _derive_request_id(refund) -> str:
    return f'refund-{refund.pk}' if refund.request_epoch == 0 else f'refund-{refund.pk}-r{refund.request_epoch}'


def _write_attempt(refund, kind: str, result_state: str, *, actor=None, http_status=None, error_code: str = '', request_id: str = '') -> None:
    last = RefundAttempt.objects.filter(refund=refund).aggregate(m=Max('seq'))['m'] or 0
    RefundAttempt.objects.create(refund=refund, seq=last + 1, kind=kind, actor=actor, request_id=request_id or refund.gateway_request_id,
                                 result_state=result_state, http_status=http_status or None, error_code=(error_code or '')[:64])


def _log(refund, tx, *, state: str, outcome: str, http_status=None, error_code: str = '') -> None:
    """One log-safe line: ids and codes only. Never headers, bodies, URLs, tokens, signatures or exception text."""
    logger.info("[REFUND] refund=%s booking=%s tx=%s gateway=%s request_id=%s attempt=%s state=%s outcome=%s http_status=%s error_code=%s",
                refund.pk, refund.booking_id, tx.pk, tx.gateway, refund.gateway_request_id, refund.attempts, state, outcome,
                http_status or '', error_code or '')


# ================================================================================================ guards
def _guard_problem(tx: PaymentTransaction, refund: RefundRequest) -> str:
    """Why this refund must NOT be sent right now ('' = safe). Runs under the payment's row lock, before any gateway call."""
    if tx.status != PaymentTransaction.Status.SUCCESS:
        return f"the payment is {tx.status}, not success"
    capture_ref = tx.gateway_reference or ''
    if capture_ref.upper().startswith('INIT-') or not CAPTURE_REF_RE.fullmatch(capture_ref):
        return "the payment has no real capture reference"
    if refund.amount is None or refund.amount <= 0:
        return "the refund amount must be greater than zero"
    funding = BookingFunding.objects.filter(booking_id=refund.booking_id).first()
    if funding is None:
        return "the booking has no funding record"
    currencies = {refund.currency.upper(), tx.currency.upper(), funding.currency.upper()}
    if len(currencies) != 1:
        return f"currency mismatch (refund {refund.currency}, payment {tx.currency}, funding {funding.currency})"
    try:
        exact = quantize_money(refund.amount, refund.currency) == refund.amount
    except ValueError:
        return f"unsupported currency {refund.currency}"
    if not exact:
        return f"the amount {refund.amount} is not a whole number of the {refund.currency} minor unit"
    if GatewayAnomaly.objects.filter(payment_transaction=tx, reason='external_refund', resolved=False).exists():
        return "an unresolved external refund on this payment must be reviewed first"
    moved = (RefundRequest.objects.filter(payment_transaction=tx).exclude(pk=refund.pk)
             .filter(Q(status__in=(RS.PROCESSED, RS.SUBMITTED)) | Q(status__in=(RS.PENDING_GATEWAY, RS.FAILED), attempts__gt=0))
             .aggregate(total=Sum('amount'))['total'] or Decimal('0'))
    if moved + refund.amount > tx.amount:
        return f"refunds of {moved} already moving plus {refund.amount} would exceed the {tx.amount} captured"
    return ''


# ================================================================================================ outcomes (all run under both locks)
def _fail_locked(tx, refund, detail: str, kind: str, *, code: str = '', http_status=None) -> None:
    refund.status = RS.FAILED
    refund.failure_kind = kind
    refund.failure_detail = detail[:2000]
    refund.last_error_code = (code or '')[:64]
    refund.last_http_status = http_status or None
    refund.next_attempt_at = None
    _clear_claim(refund)
    refund.save(update_fields=['status', 'failure_kind', 'failure_detail', 'last_error_code', 'last_http_status',
                               'next_attempt_at', 'claim_token', 'claimed_until', 'updated_at'])
    alert_admin(f'refund_failed_{kind}', f"Refund {refund.pk} needs a person ({kind})",
                f"Refund {refund.pk} for booking {refund.booking_id} ({refund.amount} {refund.currency}) failed: {kind}. {detail}".strip(),
                key=str(refund.pk), tx=tx, booking=refund.booking)


def _complete_locked(tx, refund, reference: str) -> None:
    """The gateway returned the money: post the cash movement. The caller holds both locks and has checked the state."""
    record_journal_entries(
        entries=[
            {'account': LedgerAccount.LIABILITY_REFUNDS_PAYABLE, 'entry_type': DR, 'amount': refund.amount, 'currency': refund.currency,
             'description': f"Gateway refund paid, ref {reference}"},
            {'account': _gateway_cash_account(tx), 'entry_type': CR, 'amount': refund.amount, 'currency': refund.currency,
             'description': f"Refund returned to the original payment method via {tx.gateway.upper()}"},
        ],
        event_type=EV.GATEWAY_REFUND_PAID, description=f"Gateway refund {reference} for booking {refund.booking_id}",
        booking=refund.booking, payment_transaction=tx, user=refund.user, currency=refund.currency, **_fx_of(refund))
    refund.status = RS.PROCESSED
    refund.gateway_reference = reference[:255]
    refund.failure_kind = ''
    refund.failure_detail = ''
    refund.next_attempt_at = None
    refund.processed_at = _now()
    _clear_claim(refund)
    refund.save(update_fields=['status', 'gateway_reference', 'failure_kind', 'failure_detail', 'next_attempt_at', 'processed_at',
                               'last_http_status', 'last_error_code', 'claim_token', 'claimed_until', 'updated_at'])
    tx.status = PaymentTransaction.Status.REFUNDED
    tx.save(update_fields=['status', 'updated_at'])
    _resolve_refund_alerts(refund)
    if refund.reason != 'external_refund':
        refund_id = str(refund.pk)

        def notify():
            from apps.payments.tasks import send_refund_processed_email_task
            send_refund_processed_email_task.delay(refund_id)
        transaction.on_commit(notify)


def _submit_locked(refund, provider_ref: str, now) -> None:
    refund.status = RS.SUBMITTED
    refund.gateway_reference = provider_ref[:255]
    refund.submitted_at = refund.submitted_at or now
    refund.next_attempt_at = now + timedelta(minutes=settings.REFUND_POLL_INTERVAL_MINUTES)
    _clear_claim(refund)
    refund.save(update_fields=['status', 'gateway_reference', 'submitted_at', 'next_attempt_at', 'last_http_status', 'last_error_code',
                               'claim_token', 'claimed_until', 'updated_at'])


def mark_processed(refund_id, gateway_reference: str) -> RefundRequest:
    """The gateway returned the money: post the cash movement. Safe to repeat (webhook, poll, sweeper and admin all end here)."""
    with transaction.atomic():
        tx, refund = _lock_pair(refund_id)
        if refund.status == RS.PROCESSED:
            return refund
        if refund.status not in (RS.PENDING_GATEWAY, RS.SUBMITTED, RS.FAILED):
            raise RefundStateError(f"Refund {refund.pk} is {refund.status}; it cannot be paid out.")
        _complete_locked(tx, refund, gateway_reference)
        return refund


def mark_submitted(refund_id, provider_ref: str, *, token: str) -> RefundRequest:
    """The provider accepted the refund but has not finished it. Needs the claim token of the worker that asked."""
    with transaction.atomic():
        tx, refund = _lock_pair(refund_id)
        if not token or refund.claim_token != token or refund.status != RS.PENDING_GATEWAY:
            raise RefundStateError(f"Refund {refund.pk} is {refund.status} and not held by that claim; it cannot be marked submitted.")
        _submit_locked(refund, provider_ref, _now())
        return refund


def mark_failed(refund_id, detail: str, *, kind: str, token: Optional[str] = None) -> RefundRequest:
    """A person must look at this refund. Accepts a pending or submitted refund; with a token it also fences a stale worker."""
    with transaction.atomic():
        tx, refund = _lock_pair(refund_id)
        if refund.status not in (RS.PENDING_GATEWAY, RS.SUBMITTED):
            raise RefundStateError(f"Refund {refund.pk} is {refund.status}; it cannot be marked failed.")
        if token is not None and (not token or refund.claim_token != token):
            raise RefundStateError(f"Refund {refund.pk} is no longer held by that claim.")
        _fail_locked(tx, refund, detail, kind)
        return refund


def mark_paid_manually(refund_id, *, actor, reference: str) -> RefundRequest:
    """A person paid the refund in the gateway's own console: post the cash movement and leave an audit row. Safe to repeat."""
    reference = (reference or '').strip()
    if not reference:
        raise ValueError("A reference for the manual payment is required.")
    with transaction.atomic():
        tx, refund = _lock_pair(refund_id)
        if refund.status == RS.PROCESSED:
            return refund
        if refund.status not in (RS.PENDING_GATEWAY, RS.FAILED):
            raise RefundStateError(f"Refund {refund.pk} is {refund.status}; it cannot be marked as paid by hand.")
        _complete_locked(tx, refund, reference)
        _write_attempt(refund, 'admin_mark_paid', 'completed', actor=actor)
        return refund


def _may_have_refunded_unseen(refund) -> bool:
    """
    Could the provider have refunded this request id without us seeing it? True when more than one attempt was made, or an earlier
    attempt of the SAME request id ended in a non-definitive answer (transient, manual): a later 'rejected' then says nothing about
    whether an earlier call went through (a crash or timeout after PayPal accepted it). A single definitive answer is certain.
    """
    if refund.attempts > 1:
        return True
    return RefundAttempt.objects.filter(refund=refund, kind__in=(SEND, POLL), request_id=refund.gateway_request_id,
                                        result_state__in=('transient', 'manual')).exists()


def retry_failed(refund_id, *, actor, confirm_not_refunded: bool = False) -> RefundRequest:
    """
    An admin sends a failed refund back to the gateway. Failures the provider certainly refused (`rejected`,
    `provider_failed` after ONE definitive answer) get a NEW request id (epoch bump); `guard` keeps its id; ambiguous ones (the
    provider may have refunded: exhausted, replay window, already refunded, or a rejection that followed a transient/manual/repeated
    attempt) need `confirm_not_refunded` and `exhausted`/`replay_window` keep the old id, so a replay can never refund twice. The
    guards run again first.
    """
    with transaction.atomic():
        tx, refund = _lock_pair(refund_id)
        if refund.status != RS.FAILED:
            raise RefundStateError(f"Refund {refund.pk} is {refund.status}; only a failed refund can be retried.")
        kind = refund.failure_kind
        ambiguous = kind in AMBIGUOUS_KINDS or (kind in (FK.REJECTED, FK.PROVIDER_FAILED) and _may_have_refunded_unseen(refund))
        if ambiguous and not confirm_not_refunded:
            raise RefundConfirmationRequired(
                f"Refund {refund.pk} failed as '{kind or 'unknown'}': the provider may already have refunded it (an earlier attempt was "
                f"not answered clearly). Check the gateway, then retry with confirm_not_refunded=True.")
        problem = _guard_problem(tx, refund)
        if problem:
            raise RefundGuardFailed(f"Refund {refund.pk} still fails a safety check: {problem}")
        now = _now()
        if kind in (FK.REJECTED, FK.PROVIDER_FAILED):
            refund.request_epoch += 1                    # the old request id would only replay the refusal
            refund.gateway_request_id = ''
            refund.attempts = 0
            refund.first_attempt_at = None
            refund.submitted_at = None                   # a new provider refund is coming: its 14-day staleness clock starts afresh
            if kind == FK.PROVIDER_FAILED:
                refund.gateway_reference = ''
        elif kind in (FK.EXHAUSTED, FK.REPLAY_WINDOW):
            refund.first_attempt_at = now                # a person verified it: restart the retry and replay windows
        refund.status = RS.PENDING_GATEWAY
        refund.failure_kind = ''
        refund.failure_detail = ''
        refund.next_attempt_at = None
        _clear_claim(refund)
        refund.save(update_fields=['request_epoch', 'gateway_request_id', 'attempts', 'first_attempt_at', 'submitted_at', 'gateway_reference',
                                   'status', 'failure_kind', 'failure_detail', 'next_attempt_at', 'claim_token', 'claimed_until', 'updated_at'])
        _resolve_refund_alerts(refund)
        _write_attempt(refund, 'admin_retry', 'retry', actor=actor, request_id=refund.gateway_request_id or _derive_request_id(refund))
        return refund


def convert_to_wallet(refund_id) -> CreditBundle:
    """
    The student prefers lesson credit to waiting for the gateway. Allowed ONLY before the gateway has been (or may have been)
    asked: attempts == 0, no live claim, never attempted. Afterwards the money may already be on its way, and converting would
    pay the student twice (`RefundInProgress`).
    """
    with transaction.atomic():
        _lock_pair(refund_id)
        refund = RefundRequest.objects.select_related('booking', 'user').get(pk=refund_id)
        if refund.status == RS.SUBMITTED:
            raise RefundInProgress(f"Refund {refund.pk} is already on its way to the original payment method.")
        if refund.status != RS.PENDING_GATEWAY:
            raise RefundStateError(f"Refund {refund.pk} is {refund.status}; only a pending refund can become wallet credit.")
        live_claim = bool(refund.claim_token) or (refund.claimed_until is not None and refund.claimed_until > _now())
        if refund.attempts or refund.last_attempt_at is not None or live_claim:
            raise RefundInProgress(f"Refund {refund.pk} has already been handed to the gateway; it can no longer become wallet credit.")
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
        refund.status = RS.CONVERTED
        refund.processed_at = _now()
        refund.next_attempt_at = None
        _clear_claim(refund)
        refund.save(update_fields=['status', 'processed_at', 'next_attempt_at', 'claim_token', 'claimed_until', 'updated_at'])
        _resolve_refund_alerts(refund)
        return lot


# ================================================================================================ claim
def _build_order(tx: PaymentTransaction, refund: RefundRequest, request_id: str) -> RefundOrder:
    return RefundOrder(
        refund_id=str(refund.pk), request_id=request_id, gateway=tx.gateway, capture_ref=tx.gateway_reference,
        provider_refund_id=refund.gateway_reference, amount=refund.amount, currency=refund.currency.upper(),
        invoice_id=str(refund.pk), note=getattr(settings, 'PAYPAL_REFUND_NOTE', 'Refund from Sharon Online'))


def _first_attempt_delay() -> timedelta:
    return timedelta(minutes=settings.REFUND_FIRST_ATTEMPT_DELAY_MINUTES)


def _is_due(refund: RefundRequest, now) -> bool:
    """Is this row ready to be claimed now? (Checked under the lock; the claim UPDATE repeats it atomically.)"""
    if refund.status not in (RS.PENDING_GATEWAY, RS.SUBMITTED):
        return False
    if refund.next_attempt_at is not None and refund.next_attempt_at > now:
        return False
    if refund.claimed_until is not None and refund.claimed_until > now:
        return False
    if refund.status == RS.PENDING_GATEWAY and refund.attempts == 0 and refund.created_at > now - _first_attempt_delay():
        return False                                        # the student's window to choose wallet credit instead
    return True


def _due_candidates(now) -> list:
    """(refund id, status, gateway) of rows that look due, oldest first. A hint only: the claim re-checks everything."""
    due = (Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now)) & (Q(claimed_until__isnull=True) | Q(claimed_until__lte=now))
    started = Q(attempts__gt=0) | Q(created_at__lte=now - _first_attempt_delay())
    rows = (RefundRequest.objects.filter(Q(status=RS.SUBMITTED) | (Q(status=RS.PENDING_GATEWAY) & started)).filter(due)
            .order_by('created_at').values_list('pk', 'status', 'payment_transaction__gateway')[:CANDIDATE_CAP])
    return list(rows)


def _cas_claim(refund_id, *, now, lease: timedelta, token: str, request_id: str, epoch: int, kind: str, delay: timedelta) -> bool:
    """
    The claim: ONE compare-and-swap UPDATE, portable across SQLite and Postgres. It only matches a row that is still in the
    state the caller saw (status, request epoch), is due and is not leased by another worker; `rowcount == 1` means we own it.
    """
    wanted = RS.SUBMITTED if kind == POLL else RS.PENDING_GATEWAY
    cond = (Q(pk=refund_id, status=wanted, request_epoch=epoch)
            & (Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))
            & (Q(claimed_until__isnull=True) | Q(claimed_until__lte=now)))
    changes = dict(claim_token=token, claimed_until=now + lease, last_attempt_at=now)
    if kind == SEND:
        cond &= Q(attempts__gt=0) | Q(created_at__lte=now - delay)
        changes.update(
            attempts=F('attempts') + 1,
            first_attempt_at=Coalesce('first_attempt_at', Value(now, output_field=DateTimeField())),
            gateway_request_id=Case(When(gateway_request_id='', then=Value(request_id)), default=F('gateway_request_id')))
    return RefundRequest.objects.filter(cond).update(**changes) == 1


def _try_claim(refund_id, status, now_fn: Callable) -> Optional[RefundClaim]:
    """Guard, then claim, one refund. None when it is not claimable (not due, taken, or failed a guard)."""
    kind = POLL if status == RS.SUBMITTED else SEND
    with transaction.atomic():
        tx, refund = _lock_pair(refund_id, skip_locked=True)
        if tx is None or refund.status != status:
            return None
        now = now_fn()
        if not _is_due(refund, now):
            return None
        if kind == SEND:
            replay_window = timedelta(days=settings.REFUND_REPLAY_WINDOW_DAYS)
            if refund.attempts > 0 and not refund.gateway_reference and refund.first_attempt_at and now - refund.first_attempt_at > replay_window:
                _fail_locked(tx, refund, f"The first attempt was more than {settings.REFUND_REPLAY_WINDOW_DAYS} days ago and no refund id "
                                         f"was recorded: check the gateway before sending it again.", FK.REPLAY_WINDOW)
                return None
            problem = _guard_problem(tx, refund)
            if problem:
                _fail_locked(tx, refund, problem, FK.GUARD)
                return None
        token = uuid.uuid4().hex
        won = _cas_claim(refund.pk, now=now, lease=timedelta(minutes=settings.REFUND_ATTEMPT_LEASE_MINUTES), token=token,
                         request_id=_derive_request_id(refund), epoch=refund.request_epoch, kind=kind, delay=_first_attempt_delay())
        if not won:
            return None
        request_id = refund.gateway_request_id or _derive_request_id(refund)
        return RefundClaim(str(refund.pk), token, kind, _build_order(tx, refund, request_id))


def claim_due_refunds(*, limit: int, now=None, skip_gateways=None, on_skip: Optional[Callable] = None) -> Iterator[RefundClaim]:
    """
    Yield up to `limit` claimed refunds, one at a time: each is claimed just before it is handed out, so a slow gateway call
    never lets another row's lease run out. `skip_gateways` (a set the caller may grow while iterating) is the circuit
    breaker: rows of those gateways are left untouched, burn no attempt, and are reported to `on_skip`.
    """
    now_fn = (lambda: now) if now is not None else _now
    claimed = 0
    for refund_id, status, gateway in _due_candidates(now_fn()):
        if claimed >= limit:
            return
        if skip_gateways is not None and gateway in skip_gateways:
            if on_skip is not None:
                on_skip(refund_id, gateway)
            continue
        claim = _try_claim(refund_id, status, now_fn)
        if claim is not None:
            claimed += 1
            yield claim


# ================================================================================================ apply
def _next_backoff(attempts: int, result: RefundResult) -> timedelta:
    delay = BACKOFF[min(max(attempts, 1) - 1, len(BACKOFF) - 1)]
    if result.retry_after_s and result.retry_after_s > 0:
        delay = max(delay, min(timedelta(seconds=result.retry_after_s), BACKOFF[-1]))
    return delay


def _retry_later(refund, delay: timedelta, now) -> None:
    refund.next_attempt_at = now + delay
    _clear_claim(refund)


def _alert_if_capture_unknown(tx, refund) -> None:
    """
    This send was answered 404. When the last NOT_FOUND_ALERT_AFTER sends of this request id (this one included, its row is not
    written yet) all ended in 404, the capture is probably unknown to this PayPal environment: tell a person about THIS refund
    (the gateway breaker only sees several refunds failing together).
    """
    earlier = list(RefundAttempt.objects.filter(refund=refund, kind=SEND, request_id=refund.gateway_request_id)
                   .order_by('-seq').values_list('http_status', flat=True)[:NOT_FOUND_ALERT_AFTER - 1])
    if len(earlier) == NOT_FOUND_ALERT_AFTER - 1 and all(status == 404 for status in earlier):
        alert_admin('refund_capture_not_found', f"Refund {refund.pk}: PayPal does not know its capture",
                    f"PayPal answered 404 to the last {NOT_FOUND_ALERT_AFTER} attempts to refund {refund.amount} {refund.currency} "
                    f"(capture {tx.gateway_reference}). Check that the capture exists in this PayPal environment (sandbox versus "
                    f"live) and that the payment really was captured. The refund keeps retrying with backoff.",
                    key=str(refund.pk), tx=tx, booking=refund.booking)


def apply_result(refund_id, token: str, result: RefundResult, *, kind: str) -> str:
    """
    The single place a gateway answer is written. Re-locks (payment, then refund), checks the claim token (a worker whose lease
    ran out and whose row was claimed again is a stale worker: its answer is ignored) and writes the outcome plus exactly one
    RefundAttempt row. Returns 'processed' | 'submitted' | 'retry' | 'failed' | 'manual' | 'noop'.
    """
    if kind not in (SEND, POLL):
        raise ValueError(f"Unknown claim kind {kind!r}.")
    with transaction.atomic():
        tx, refund = _lock_pair(refund_id)
        wanted = RS.SUBMITTED if kind == POLL else RS.PENDING_GATEWAY
        if not token or refund.claim_token != token or refund.status != wanted:
            return 'noop'
        now = _now()
        refund.last_http_status = result.http_status or None
        refund.last_error_code = (result.code or '')[:64]
        state = result.state
        if state == 'submitted' and not (result.reference or (kind == POLL and refund.gateway_reference)):
            state = 'transient'                              # a refund we cannot name can be neither polled nor matched to a webhook
        if state not in ('completed', 'submitted', 'rejected', 'manual'):
            state = 'transient'
        if state == 'rejected' and result.provider_level:
            state = 'transient'                              # a config/outage problem is never the refund's fault: never fail the row for it

        if state == 'completed':
            _complete_locked(tx, refund, result.reference or refund.gateway_reference or refund.gateway_request_id)
            outcome = 'processed'
        elif state == 'submitted':
            _submit_locked(refund, result.reference or refund.gateway_reference, now)
            if kind == POLL and now - refund.submitted_at >= SUBMITTED_STALE_AFTER:
                alert_admin('refund_submitted_stale', f"Refund {refund.pk} has been on its way for over 14 days",
                            f"Refund {refund.pk} ({refund.amount} {refund.currency}) was accepted by {tx.gateway} on "
                            f"{refund.submitted_at:%Y-%m-%d} and is still not finished. Check it in the gateway.",
                            key=str(refund.pk), tx=tx, booking=refund.booking)
            outcome = 'submitted'
        elif state == 'rejected':
            if kind == POLL:
                failure = FK.PROVIDER_FAILED
            elif result.code == 'CAPTURE_FULLY_REFUNDED':
                failure = FK.ALREADY_REFUNDED
            else:
                failure = FK.REJECTED
            _fail_locked(tx, refund, result.detail or f"{tx.gateway} refused the refund", failure, code=result.code, http_status=result.http_status)
            outcome = 'failed'
        elif state == 'manual' and kind == SEND:
            refund.attempts = max(refund.attempts - 1, 0)    # nothing was asked of the provider: this does not count
            if refund.attempts == 0:
                refund.first_attempt_at = None
                refund.last_attempt_at = None                # never attempted, so the student may still choose wallet credit
            _retry_later(refund, MANUAL_RECHECK, now)
            refund.failure_detail = (result.detail or '')[:2000]
            refund.save(update_fields=['attempts', 'first_attempt_at', 'last_attempt_at', 'next_attempt_at', 'failure_detail',
                                       'claim_token', 'claimed_until', 'last_http_status', 'last_error_code', 'updated_at'])
            if now - refund.created_at >= timedelta(hours=settings.REFUND_MANUAL_ALERT_AFTER_HOURS):
                alert_admin('refund_manual_waiting', f"Refund {refund.pk} is waiting for a person",
                            f"Refund {refund.pk} ({refund.amount} {refund.currency}, {tx.gateway}) has been waiting since "
                            f"{refund.created_at:%Y-%m-%d %H:%M} UTC for a manual payment: this backend does not move money.",
                            key=str(refund.pk), tx=tx, booking=refund.booking)
            outcome = 'manual'
        elif kind == POLL:                                   # transient (or manual) poll: look again at the next interval
            _retry_later(refund, timedelta(minutes=settings.REFUND_POLL_INTERVAL_MINUTES), now)
            refund.save(update_fields=['next_attempt_at', 'claim_token', 'claimed_until', 'last_http_status', 'last_error_code', 'updated_at'])
            outcome = 'retry'
        else:                                                # transient send
            exhausted = (not result.provider_level and refund.attempts >= settings.REFUND_MAX_ATTEMPTS and refund.first_attempt_at is not None
                         and now - refund.first_attempt_at >= timedelta(hours=settings.REFUND_TRANSIENT_WINDOW_HOURS))
            if exhausted:
                _fail_locked(tx, refund, f"Gave up after {refund.attempts} attempts over {settings.REFUND_TRANSIENT_WINDOW_HOURS} hours "
                                         f"(last: {result.detail or 'no detail'}). Check the gateway before retrying.",
                             FK.EXHAUSTED, code=result.code, http_status=result.http_status)
                outcome = 'failed'
            else:
                _retry_later(refund, _next_backoff(refund.attempts, result), now)
                refund.failure_detail = (result.detail or '')[:2000]
                if result.http_status == 404:
                    _alert_if_capture_unknown(tx, refund)
                refund.save(update_fields=['next_attempt_at', 'failure_detail', 'claim_token', 'claimed_until', 'last_http_status',
                                           'last_error_code', 'updated_at'])
                outcome = 'retry'

        _write_attempt(refund, kind, result.state, http_status=result.http_status, error_code=result.code)
        _log(refund, tx, state=result.state, outcome=outcome, http_status=result.http_status, error_code=result.code)
        return outcome


# ================================================================================================ the sweep
_COUNTERS = ('sent', 'completed', 'submitted', 'rejected', 'transient', 'manual', 'polled', 'skipped_breaker')
_OUTCOME_COUNTER = {'processed': 'completed', 'submitted': 'submitted', 'failed': 'rejected', 'retry': 'transient', 'manual': 'manual'}


def _ask_gateway(gateway, claim: RefundClaim) -> RefundResult:
    """Call the gateway with no database lock held. Whatever goes wrong becomes `transient`: a refund is never failed by a guess."""
    started = time.perf_counter()
    try:
        result = gateway.lookup(claim.order) if claim.kind == POLL else gateway.refund(claim.order)
        if not isinstance(result, RefundResult):
            raise TypeError("the gateway did not return a RefundResult")
    except Exception as exc:                                  # the sweep must survive any adapter; only the type is logged
        logger.error("[REFUND] refund=%s gateway=%s request_id=%s %s call raised %s", claim.order.refund_id, claim.order.gateway,
                     claim.order.request_id, claim.kind, type(exc).__name__)
        return RefundResult('transient', detail=f"unexpected error ({type(exc).__name__})")
    logger.info("[REFUND] refund=%s gateway=%s request_id=%s %s answered %s in %sms", claim.order.refund_id, claim.order.gateway,
                claim.order.request_id, claim.kind, result.state, int((time.perf_counter() - started) * 1000))
    return result


def _watch_provider(gateway_name: str, result: RefundResult, streak, tripped: set) -> None:
    """The per-gateway circuit breaker: three transient/provider-level answers in a row stop that gateway for this sweep."""
    if result.state == 'transient' or result.provider_level:
        streak[gateway_name] += 1
        if streak[gateway_name] >= BREAKER_THRESHOLD and gateway_name not in tripped:
            tripped.add(gateway_name)
            alert_admin('refund_provider_outage', f"{gateway_name} refunds are failing",
                        f"{BREAKER_THRESHOLD} refund calls to {gateway_name} in a row could not be completed (last HTTP status "
                        f"{result.http_status or 'n/a'}). Refunds to it are paused for this run and retried with backoff; "
                        f"check the {gateway_name} status and credentials.", key=gateway_name, gateway=gateway_name)
    elif result.state in ('completed', 'submitted', 'rejected'):
        streak[gateway_name] = 0                              # the provider answered
        resolve_alert('refund_provider_outage', gateway_name)


def process_pending_refunds() -> dict:
    """
    One sweep (beat, every 15 minutes): claim due refunds one at a time, call the configured gateway outside any lock, apply
    the answer. Bounded by REFUND_SWEEP_LIMIT rows and REFUND_SWEEP_BUDGET_SECONDS. A gateway that fails three times in a row is
    left alone for the rest of the sweep (its other rows burn no attempt) and raises ONE admin alert per trip.
    """
    gateway = import_string(settings.REFUND_GATEWAY_BACKEND)()
    done = dict.fromkeys(_COUNTERS, 0)
    streak, tripped = defaultdict(int), set()
    started = _monotonic()

    def skipped(refund_id, gateway_name):
        done['skipped_breaker'] += 1

    claims = claim_due_refunds(limit=settings.REFUND_SWEEP_LIMIT, skip_gateways=tripped, on_skip=skipped)
    try:
        while _monotonic() - started < settings.REFUND_SWEEP_BUDGET_SECONDS:
            claim = next(claims, None)
            if claim is None:
                break
            done['polled' if claim.kind == POLL else 'sent'] += 1
            result = _ask_gateway(gateway, claim)
            try:
                outcome = apply_result(claim.refund_id, claim.token, result, kind=claim.kind)
            except Exception:                                 # one bad row never stops the sweep; its lease expires and it is replayed
                logger.exception("[REFUND] refund=%s could not apply a %s result; it will be replayed with the same request id",
                                 claim.refund_id, result.state)
                done['transient'] += 1
                continue
            if outcome in _OUTCOME_COUNTER and not (outcome == 'submitted' and claim.kind == POLL):    # a poll that is still pending is only 'polled'
                done[_OUTCOME_COUNTER[outcome]] += 1
            _watch_provider(claim.order.gateway, result, streak, tripped)
    finally:
        claims.close()
    return done
