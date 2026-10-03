"""
Pending-payment grace bookings (Task 10.2 slice E + failure runbook G, plan section 2).

A grace booking is a lesson confirmed (Zoom link issued) while PayPal still reports the capture PENDING. Policy
(docs/PHASE_10_2_PAYPAL_ORDERS_PLAN.md P-1..P-8):
  * one open grace booking per student account AND per PayPal payer (payer id, falling back to payer e-mail);
  * only for merchant-side reasons and PENDING_REVIEW; never for ECHECK / VERIFICATION_REQUIRED / OTHER / unknown / DECLINED;
  * never for credit-pack purchases;
  * circuit breaker: settings.GRACE_MAX_OPEN open RISK-BASED (PENDING_REVIEW) grace bookings switch risk-based grace off;
    merchant-side reasons never count toward it, but each one alerts the admin immediately;
  * NOTHING is posted to the ledger while the capture is pending (no cash has arrived), and the funding is marked
    GATEWAY_PENDING so escrow release, arbitration release and tutor payout all refuse the booking until it clears.

Resolution:
  on_completed  the capture cleared: tx SUCCESS, funding GATEWAY, capture journal posted at the checkout-stamped FX,
                the booking is NOT touched, deferred refunds (a cancelled grace booking) become real refunds.
  on_failed     the capture failed. Before the lesson: cancel it, nothing was collected so nothing is refunded.
                After the lesson: the platform still pays the tutor (funding PLATFORM_ABSORBED -> ledger 5040 -> 2020 at the
                normal 24h release), the student is blocked from booking until staff clear it. Always: support ticket,
                e-mail to the student and an admin alert, each created once.
"""
import logging
from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.db.models import Q
from django.utils import timezone

from apps.bookings.models import Booking
from apps.bookings.services.state_machine import transition_booking
from apps.payments.gateways import paypal
from apps.payments.models import BookingFunding, PaymentTransaction, SettlementAnomaly
from apps.payments.services import refunds
from apps.payments.services.alerts import alert_admin, resolve_alert
from apps.payments.services.funding import ensure_gateway_funding
from apps.payments.services.ledger_service import record_payment_capture_entry
from apps.payments.services.webhook_handler import (
    _hold_unallocated, finish_confirmed_booking, slot_unavailable_reason)

logger = logging.getLogger(__name__)

S = Booking.Status
PENDING_STILL_OPEN_CODE = 'grace_payment_still_pending'
BREAKER_ALERT = 'grace_circuit_breaker_open'
GRACE_ADVISORY_LOCK = 7_102_002     # serialises grace decisions so the per-account / per-payer caps and the breaker cannot be raced

# A grace booking in one of these states carries no tutor-payment exposure any more (the lesson was cancelled or did not
# happen), so it no longer counts toward the caps and the platform owes the tutor nothing.
NO_EXPOSURE_STATUSES = (S.CANCELLED, S.CANCELLED_BY_STUDENT, S.CANCELLED_BY_TEACHER, S.TEACHER_NO_SHOW, S.INTERRUPTED_POWER)


@dataclass(frozen=True)
class GraceDecision:
    allowed: bool
    reason: str = ''          # why grace was refused, or the rule that allowed it (for logs/admin)


# ---------------------------------------------------------------------------------------------------------------------
# Eligibility (pure reads)
# ---------------------------------------------------------------------------------------------------------------------

def outcome_from_tx(tx) -> paypal.CaptureOutcome:
    """Rebuild the classification of a stored pending capture from the reason recorded on the transaction."""
    reason = tx.pending_reason or ''
    return paypal.CaptureOutcome('pending', reason, reason in paypal.MERCHANT_SIDE_PENDING_REASONS,
                                 reason in paypal.RISK_BASED_PENDING_REASONS)


def open_grace_funding():
    """Grace bookings still waiting for PayPal to clear the money and still carrying tutor-payment exposure."""
    return (BookingFunding.objects
            .filter(source_type=BookingFunding.SourceType.GATEWAY_PENDING,
                    payment_transaction__status=PaymentTransaction.Status.PENDING_CAPTURE)
            .exclude(booking__status__in=NO_EXPOSURE_STATUSES))


def open_risk_based_count(exclude_tx=None) -> int:
    qs = open_grace_funding().filter(payment_transaction__pending_reason__in=paypal.RISK_BASED_PENDING_REASONS)
    if exclude_tx is not None:
        qs = qs.exclude(payment_transaction=exclude_tx)
    return qs.count()


def evaluate_grace(tx, outcome) -> GraceDecision:
    """Decide whether a PENDING capture may confirm its booking now. Reads only; races are closed by confirm_grace_booking."""
    if tx.credit_purchase_id or not tx.booking_id:
        return GraceDecision(False, 'credit_pack')                                    # P-7
    if outcome.state != 'pending':
        return GraceDecision(False, 'not_pending')
    if not (outcome.merchant_side or outcome.risk_based):                             # P-5: an allow-list, never a deny-list
        return GraceDecision(False, f"reason_not_eligible:{outcome.reason or 'none'}")
    booking = tx.booking
    if booking.status != S.PENDING_PAYMENT:
        return GraceDecision(False, 'booking_not_awaiting_payment')
    student = booking.student
    if student.booking_blocked_reason:
        return GraceDecision(False, 'student_blocked')

    payer_id, payer_email = (tx.payer_id or '').strip(), (tx.payer_email or '').strip()
    if not payer_id and not payer_email:
        return GraceDecision(False, 'payer_unknown')                                  # cannot enforce the per-payer cap

    others = open_grace_funding().exclude(payment_transaction=tx)
    if others.filter(booking__student=student).exists():                              # P-2, per account
        return GraceDecision(False, 'account_cap')
    same_payer = Q()
    if payer_id:
        same_payer |= Q(payment_transaction__payer_id=payer_id)
    if payer_email:
        same_payer |= Q(payment_transaction__payer_email__iexact=payer_email)
    if others.filter(same_payer).exists():                                            # P-2, per PayPal payer
        return GraceDecision(False, 'payer_cap')

    if outcome.risk_based and open_risk_based_count(exclude_tx=tx) >= settings.GRACE_MAX_OPEN:   # P-6
        return GraceDecision(False, 'circuit_breaker')
    return GraceDecision(True, 'merchant_side' if outcome.merchant_side else 'risk_based')


# ---------------------------------------------------------------------------------------------------------------------
# Confirmation
# ---------------------------------------------------------------------------------------------------------------------

def _serialize_grace_decisions() -> None:
    if connection.vendor == 'postgresql':
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(%s)', [GRACE_ADVISORY_LOCK])


def _alert_breaker(tx=None) -> None:
    alert_admin(
        BREAKER_ALERT, 'Grace bookings switched off (circuit breaker)',
        f"{settings.GRACE_MAX_OPEN} risk-based (PENDING_REVIEW) grace bookings are open at once, so new pending PayPal "
        f"payments no longer confirm lessons until some resolve. Review the open pending payments in PayPal.",
        key='grace', tx=tx)


def alert_merchant_side_pending(tx) -> None:
    """A merchant-side pending reason means OUR PayPal account settings hold the payment: tell the admin to fix the account."""
    alert_admin(
        'paypal_merchant_side_pending',
        f"PayPal holds a payment because of our account settings ({tx.pending_reason})",
        f"Capture {tx.gateway_reference} ({tx.amount} {tx.currency}) is pending with reason {tx.pending_reason}. This is a "
        f"PayPal Business account setting (receiving preferences / currency handling), not the student. Fix the account.",
        key=tx.merchant_reference or str(tx.pk), tx=tx)


def handle_pending_capture(tx, outcome) -> GraceDecision:
    """Everything the capture endpoint does with a PENDING capture, in one call: alert on merchant-side reasons, then try grace."""
    if outcome.merchant_side:
        alert_merchant_side_pending(tx)
    if not settings.PAYPAL_CAPTURE_CONFIRMS:
        return GraceDecision(False, 'capture_endpoint_does_not_confirm')              # P-8: grace is a confirmation by the endpoint
    return confirm_grace_booking(tx)


def confirm_grace_booking(tx) -> GraceDecision:
    """
    Confirm the booking of a PENDING_CAPTURE transaction as a grace booking, if policy and the DEF-501 guards allow it.
    Eligibility is re-evaluated under a lock so concurrent captures cannot slip past the caps. Posts NO ledger entry.
    """
    decision = None
    with transaction.atomic():
        _serialize_grace_decisions()
        tx = PaymentTransaction.objects.select_for_update().select_related('booking').get(pk=tx.pk)
        if tx.status != PaymentTransaction.Status.PENDING_CAPTURE or not tx.booking_id:
            return GraceDecision(False, 'not_pending')
        booking = Booking.objects.select_for_update().select_related('teacher', 'student').get(pk=tx.booking_id)
        tx.booking = booking
        decision = evaluate_grace(tx, outcome_from_tx(tx))
        if decision.allowed:
            if BookingFunding.objects.filter(booking=booking).exists():
                decision = GraceDecision(False, 'booking_already_funded')
            else:
                guard = slot_unavailable_reason(booking)            # DEF-501: same guard as the normal confirmation
                if guard:
                    decision = GraceDecision(False, guard)
        if decision.allowed:
            try:
                with transaction.atomic():
                    transition_booking(booking, S.CONFIRMED, actor='system:paypal_capture', reason='grace_pending_capture')
            except IntegrityError:                                  # lost a microsecond race for the slot: no grace
                decision = GraceDecision(False, 'slot_race')
        if decision.allowed:
            ensure_gateway_funding(tx, booking, BookingFunding.SourceType.GATEWAY_PENDING)
            finish_confirmed_booking(booking)
            logger.warning("[GRACE BOOKING] booking %s confirmed while PayPal capture %s is PENDING (%s)",
                           booking.id, tx.gateway_reference, tx.pending_reason)
            if tx.pending_reason in paypal.RISK_BASED_PENDING_REASONS and open_risk_based_count() >= settings.GRACE_MAX_OPEN:
                _alert_breaker(tx)                                  # tripped by this grant: alert once
    if not decision.allowed:
        logger.info("Grace refused for transaction %s: %s", tx.pk, decision.reason)
        if decision.reason == 'circuit_breaker':
            _alert_breaker(tx)
    return decision


# ---------------------------------------------------------------------------------------------------------------------
# Resolution: cleared
# ---------------------------------------------------------------------------------------------------------------------

def _refresh_breaker() -> None:
    if open_risk_based_count() < settings.GRACE_MAX_OPEN:
        resolve_alert(BREAKER_ALERT, 'grace')


def on_completed(tx) -> bool:
    """
    A PENDING_CAPTURE transaction cleared (COMPLETED). Marks the transaction SUCCESS, upgrades the funding to GATEWAY, posts
    the capture journal (DR gateway cash, CR escrow) at the FX stamped at checkout, turns refunds that were waiting on it
    into real ones, and lifts the settlement gate. The booking itself is never transitioned. Idempotent; returns True if it acted.
    """
    with transaction.atomic():
        tx = PaymentTransaction.objects.select_for_update().get(pk=tx.pk)
        if tx.status == PaymentTransaction.Status.SUCCESS:
            return False
        funding = BookingFunding.objects.select_for_update().filter(payment_transaction=tx).first()
        if funding is None or funding.source_type != BookingFunding.SourceType.GATEWAY_PENDING:
            return False
        booking = Booking.objects.select_for_update().select_related('teacher__user', 'student').get(pk=tx.booking_id)
        if tx.status == PaymentTransaction.Status.FAILED:
            # PayPal says COMPLETED after we already wrote the payment off (booking cancelled / tutor covered). The money is
            # real: hold it for a refund instead of re-opening a settled outcome.
            _hold_unallocated(tx, booking, 'payment_completed_after_failure',
                              f"booking is '{booking.status}'; the payment had been written off as failed")
            return True
        tx.status = PaymentTransaction.Status.SUCCESS
        tx.save(update_fields=['status', 'updated_at'])
        funding.resolve_pending(BookingFunding.SourceType.GATEWAY)
        record_payment_capture_entry(
            payment_transaction=tx, booking=booking, user=booking.student,
            fx_rate_to_zar=funding.fx_rate_to_zar, fx_source=funding.fx_source)
        refunds.activate_deferred_refunds(booking)
        SettlementAnomaly.objects.filter(booking=booking, code=PENDING_STILL_OPEN_CODE, resolved=False).update(
            resolved=True, resolved_at=timezone.now())
        resolve_alert(PENDING_STILL_OPEN_CODE, str(booking.id))
        resolve_alert('grace_pending_over_7_days', tx.merchant_reference or str(tx.pk))
        _refresh_breaker()
    return True


# ---------------------------------------------------------------------------------------------------------------------
# Resolution: failed
# ---------------------------------------------------------------------------------------------------------------------

def _booking_blocked_reason(booking) -> str:
    return (f"The lesson on {booking.start_time_utc:%d %B %Y} took place but its PayPal payment did not go through. "
            f"Please contact support to settle it before booking again.")[:255]


def _apply_to_booking(tx, booking, now) -> str:
    """Move a failed pending payment's booking to its end state. Idempotent. Returns the notice kind."""
    funding = BookingFunding.objects.select_for_update().filter(payment_transaction=tx).first()
    if funding is None:
        return 'unconfirmed'                                  # a non-grace pending capture: the booking never left PENDING_PAYMENT
    if funding.source_type == BookingFunding.SourceType.PLATFORM_ABSORBED:
        return 'absorbed'
    if funding.source_type != BookingFunding.SourceType.GATEWAY_PENDING:
        return 'unconfirmed'
    if booking.status in NO_EXPOSURE_STATUSES:
        refunds.void_deferred_refunds(booking)                # the lesson was already cancelled: the refund that waited is moot
        return 'already_cancelled'
    if booking.status == S.CONFIRMED and booking.start_time_utc > now:
        booking.cancelled_at, booking.cancel_reason = now, 'Payment did not clear'
        transition_booking(booking, S.CANCELLED, actor='system:payment_failed', reason='grace_payment_failed',
                           update_fields=('cancelled_at', 'cancel_reason'))
        refunds.void_deferred_refunds(booking)
        meeting_id, booking_pk = booking.zoom_meeting_id, str(booking.id)
        gcal = (str(booking.teacher.user_id), booking.teacher_gcal_event_id)

        def tidy():
            from apps.integrations.tasks import cleanup_gcal_event, cleanup_zoom_meeting, send_cancellation_emails
            if meeting_id:
                cleanup_zoom_meeting.delay(meeting_id)
            if gcal[1]:
                cleanup_gcal_event.delay(*gcal)
            send_cancellation_emails.delay(booking_pk, 'payment_failed')
        transaction.on_commit(tidy)
        return 'cancelled'
    # The lesson started or was delivered while the money was pending: the platform still pays the tutor (P-3).
    funding.resolve_pending(BookingFunding.SourceType.PLATFORM_ABSORBED)
    get_user_model().objects.filter(pk=booking.student_id, booking_blocked_reason='').update(
        booking_blocked_reason=_booking_blocked_reason(booking))
    return 'absorbed'


def on_failed(tx) -> str:
    """
    A pending capture failed (DENIED / FAILED / REVERSED). Resolves the booking per the runbook (plan 2.5), then, once, opens a
    support ticket, e-mails the student and alerts the admin. Safe to call repeatedly (webhook retries, reconcile runs).
    Returns the notice kind ('cancelled', 'absorbed', 'unconfirmed', 'already_cancelled', 'pack') or 'noop'.
    """
    now = timezone.now()
    with transaction.atomic():
        tx = (PaymentTransaction.objects.select_for_update().select_related('booking', 'credit_purchase__user').get(pk=tx.pk))
        if tx.status in (PaymentTransaction.Status.SUCCESS, PaymentTransaction.Status.UNALLOCATED,
                         PaymentTransaction.Status.REFUNDED):
            return 'noop'
        if tx.status in (PaymentTransaction.Status.INITIALIZED, PaymentTransaction.Status.PENDING_CAPTURE):
            tx.status = PaymentTransaction.Status.FAILED
            tx.save(update_fields=['status', 'updated_at'])
        if tx.credit_purchase_id:
            purchase = tx.credit_purchase
            if purchase.status == purchase.Status.INITIALIZED:
                purchase.status = purchase.Status.FAILED
                purchase.save(update_fields=['status', 'updated_at'])
            kind, student = 'pack', purchase.user
        else:
            booking = Booking.objects.select_for_update().select_related('teacher__user', 'student').get(pk=tx.booking_id)
            kind, student = _apply_to_booking(tx, booking, now), booking.student
            SettlementAnomaly.objects.filter(booking=booking, code=PENDING_STILL_OPEN_CODE, resolved=False).update(
                resolved=True, resolved_at=now)
            resolve_alert(PENDING_STILL_OPEN_CODE, str(booking.id))
        _open_ticket_and_notify(tx, student, kind)
        alert_admin(
            'pending_payment_failed', f"A pending PayPal payment failed ({kind})",
            f"Capture {tx.gateway_reference} ({tx.amount} {tx.currency}) for {student.username} failed after it was pending "
            f"({tx.pending_reason or 'no reason'}). Outcome: {kind}. A support ticket was opened and the student was e-mailed.",
            key=tx.merchant_reference or str(tx.pk), tx=tx)
        resolve_alert('grace_pending_over_7_days', tx.merchant_reference or str(tx.pk))
        _refresh_breaker()
    return kind


def _open_ticket_and_notify(tx, student, kind: str) -> None:
    """One support ticket and one student e-mail per failed transaction, however many times the failure is reported."""
    from apps.payments.services.notices import ticket_subject_and_message
    from apps.users.models import SupportInquiry
    ref = (tx.merchant_reference or str(tx.pk))[:40]
    if SupportInquiry.objects.filter(category=SupportInquiry.Category.PAYMENT_FAILURE, related_transaction_ref=ref).exists():
        return
    subject, message = ticket_subject_and_message(tx, kind)
    ticket = SupportInquiry.objects.create(
        category=SupportInquiry.Category.PAYMENT_FAILURE, student=student,
        sender_name=(student.get_full_name() or student.username)[:150], sender_email=student.email,
        sender_type=SupportInquiry.SenderType.STUDENT, subject=subject, message=message,
        related_booking_id=tx.booking_id, related_transaction_ref=ref)
    from apps.payments.tasks import send_payment_failure_email_task
    from apps.users.tasks import send_support_inquiry_notification
    ticket_id, tx_id = str(ticket.id), str(tx.pk)
    transaction.on_commit(lambda: send_support_inquiry_notification.delay(ticket_id))
    transaction.on_commit(lambda: send_payment_failure_email_task.delay(tx_id, kind, ticket_id))
