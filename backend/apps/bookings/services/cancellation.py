"""
Cancelling a lesson (Task 9.6, decision D-6). docs/CANCELLATION_AND_REFUNDS.md has the policy table; every number is a setting.

    who      when                                  outcome                      student's money                       tutor
    student  unpaid hold                           released                     -                                     -
    student  > STUDENT_FREE_CANCEL_HOURS before    full_refund                  gateway refund of the exact capture   nothing
    student  <= that, before the start             fee_forfeited                kept (escrow released at +24h)        80 % at +24h, like a student no-show
    tutor    >= TUTOR_CANCEL_NO_PENALTY_HOURS      tutor_refund                 gateway refund                        none (4th in 30 days: 1 strike)
    tutor    less than that, before the start      tutor_refund_with_penalty    gateway refund + bonus credit         1 strike

After the start time nobody can cancel (a lesson that did not happen is settled by the attendance job or a dispute).
The booking is locked while it is decided, so two cancels (or a cancel racing the attendance job) settle it once.
"""
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.bookings.models import Booking
from apps.bookings.services.state_machine import transition_booking
from apps.payments.models import CreditBundle, RefundRequest
from apps.payments.services import refunds
from apps.payments.services.credits import grant_credit
from apps.payments.services.ledger_service import record_compensation_entry
from apps.payments.models import BookingFunding
from apps.payments.services.funding import funding_for_settlement
from apps.payments.services.settlement import successful_transaction
from apps.teachers.models import TeacherStrike
from apps.teachers.strikes import add_strike

S = Booking.Status
STUDENT, TEACHER = 'student', 'teacher'


class CancelError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code, self.code, self.message = status_code, code, message


@dataclass
class Plan:
    outcome: str                        # released | full_refund | fee_forfeited | tutor_refund | tutor_refund_with_penalty | not_cancellable
    to_status: Optional[str] = None
    refund: bool = False
    bonus: bool = False
    strike: Optional[str] = None
    message: str = ''
    error: Optional[CancelError] = None


def party_of(booking, user) -> Optional[str]:
    if booking.student_id == user.id:
        return STUDENT
    if booking.teacher.user_id == user.id:
        return TEACHER
    return None


def recent_early_cancels(teacher, now) -> int:
    """Times this tutor already cancelled with proper notice in the last 30 days (they get TUTOR_EARLY_CANCELS_PER_30D free ones)."""
    notice = timedelta(hours=settings.TUTOR_CANCEL_NO_PENALTY_HOURS)
    rows = Booking.objects.filter(teacher=teacher, status=S.CANCELLED_BY_TEACHER, cancelled_at__gte=now - timedelta(days=30))
    return sum(1 for b in rows.only('start_time_utc', 'cancelled_at') if b.start_time_utc - b.cancelled_at >= notice)


def plan_cancellation(booking, party: str, now) -> Plan:
    """What cancelling would do right now. Pure decision: no writes."""
    def refuse(code, message, status=409):
        return Plan('not_cancellable', error=CancelError(status, code, message), message=message)

    if booking.status == S.PENDING_PAYMENT:
        if party == STUDENT:
            return Plan('released', S.CANCELLED, message='Your unpaid reservation will be released. Nothing was charged.')
        return refuse('not_cancellable', 'This booking has not been paid for yet.')
    if booking.status != S.CONFIRMED:
        return refuse('not_cancellable', f"A lesson that is '{booking.status}' cannot be cancelled.")
    if now >= booking.start_time_utc:
        return refuse('cancel_window_closed', 'This lesson has already started, so it can no longer be cancelled.')

    left = booking.start_time_utc - now
    if party == STUDENT:
        if left > timedelta(hours=settings.STUDENT_FREE_CANCEL_HOURS):
            return Plan('full_refund', S.CANCELLED_BY_STUDENT, refund=True,
                        message='Free cancellation: you will be refunded in full to your original payment method.')
        return Plan('fee_forfeited', S.STUDENT_LATE_CANCELLED,
                    message=f'This is less than {settings.STUDENT_FREE_CANCEL_HOURS} hours before the lesson, so the lesson fee is not refunded.')
    if left >= timedelta(hours=settings.TUTOR_CANCEL_NO_PENALTY_HOURS):
        strike = (TeacherStrike.Kind.SERIAL_CANCEL
                  if recent_early_cancels(booking.teacher, now) >= settings.TUTOR_EARLY_CANCELS_PER_30D else None)
        return Plan('tutor_refund', S.CANCELLED_BY_TEACHER, refund=True, strike=strike,
                    message='The student will be refunded in full.' + (' This counts as a strike: you have cancelled several lessons recently.' if strike else ''))
    return Plan('tutor_refund_with_penalty', S.CANCELLED_BY_TEACHER, refund=True, bonus=True, strike=TeacherStrike.Kind.LATE_CANCEL,
                message=f'The student will be refunded and given a bonus credit, and you receive a strike '
                        f'(cancelling less than {settings.TUTOR_CANCEL_NO_PENALTY_HOURS} hours before a lesson).')


def _known_funding(booking):
    """(amount, currency) the lesson was paid with, read-only (a preview must never write)."""
    funding = BookingFunding.objects.filter(booking=booking).first()
    if funding:
        return funding.captured_amount, funding.currency
    paid = successful_transaction(booking)
    return (paid.amount, paid.currency) if paid else None


def preview(booking, user, now=None) -> dict:
    now = now or timezone.now()
    party = party_of(booking, user)
    plan = plan_cancellation(booking, party, now)
    known = _known_funding(booking)
    body = {
        'can_cancel': plan.error is None,
        'outcome': plan.outcome,
        'message': plan.message,
        'seconds_until_start': max(int((booking.start_time_utc - now).total_seconds()), 0),
        'refund_amount': str(known[0]) if plan.refund and known else None,
        'refund_currency': known[1] if plan.refund and known else None,
        'bonus_credits': settings.TUTOR_CANCEL_BONUS_CREDITS if plan.bonus else 0,
        'strike': bool(plan.strike),
    }
    funding = BookingFunding.objects.filter(booking=booking).first()
    if plan.refund and funding and funding.source_type == BookingFunding.SourceType.GATEWAY_PENDING:
        # A grace booking: PayPal has not cleared the money yet, so nothing can be refunded yet. If the payment clears it is
        # refunded automatically; if it fails there is nothing to refund.
        body['refund_amount'] = None
        body['refund_currency'] = None
        body['message'] = ('PayPal is still verifying your payment, so nothing has been collected yet. If it clears you will be '
                           'refunded in full to your original payment method; if it does not, you owe nothing.')
    if party == STUDENT and booking.status == S.CONFIRMED:
        body['free_cancel_until'] = (booking.start_time_utc - timedelta(hours=settings.STUDENT_FREE_CANCEL_HOURS)).isoformat()
    return body


def cancel_booking(booking_id, user, *, reason: str = '', acknowledge_forfeit: bool = False, now=None) -> dict:
    """Cancel on behalf of one of the two parties. Raises CancelError with the HTTP status to answer with."""
    now = now or timezone.now()
    reason = (reason if isinstance(reason, str) else '').strip()[:255]
    missing_funding = False
    with transaction.atomic():
        booking = (Booking.objects.select_for_update(of=('self',)).select_related('teacher__user', 'student').get(pk=booking_id))
        party = party_of(booking, user)
        if party is None:
            raise CancelError(403, 'not_a_party', 'Only the student or the tutor of a lesson can cancel it.')
        plan = plan_cancellation(booking, party, now)
        if plan.error:
            raise plan.error
        if plan.outcome == 'fee_forfeited' and not acknowledge_forfeit:
            raise CancelError(400, 'acknowledgement_required',
                              f'{plan.message} Send acknowledge_forfeit=true to cancel anyway.')

        # Money is only ever returned against the booking's recorded funding, never a guess from the list price. Without it we
        # change nothing (the anomaly is recorded for finance) and say so after this block, so the record is not rolled back.
        funding = funding_for_settlement(booking, context='cancellation') if (plan.refund or plan.bonus) else None
        missing_funding = (plan.refund or plan.bonus) and funding is None
        if not missing_funding:
            booking.cancelled_at, booking.cancelled_by, booking.cancel_reason = now, user, reason
            result = transition_booking(booking, plan.to_status, actor=user, reason=reason or f'cancelled by {party}',
                                        update_fields=('cancelled_at', 'cancelled_by', 'cancel_reason'))
            if not result.changed:
                raise CancelError(409, 'not_cancellable', 'This lesson was already cancelled.')

            if plan.refund:
                refunds.request_refund(booking, RefundRequest.Reason.STUDENT_CANCEL if party == STUDENT else RefundRequest.Reason.TEACHER_CANCEL)
            if plan.bonus:
                credits = settings.TUTOR_CANCEL_BONUS_CREDITS
                grant_credit(booking.student, credits=credits, source=CreditBundle.Source.BONUS, pack_name='Tutor cancellation bonus',
                             unit_amount=funding.captured_amount, currency=funding.currency,
                             fx_rate_to_zar=funding.fx_rate_to_zar, fx_source=funding.fx_source, booking=booking,
                             idempotency_key=f'tutor-cancel-bonus:{booking.id}')
                record_compensation_entry(user=booking.student, booking=booking, amount_usd=funding.captured_amount * credits,
                                          currency=funding.currency, fx_rate_to_zar=funding.fx_rate_to_zar,
                                          fx_source=funding.fx_source, reason='Tutor cancelled less than 24h before the lesson')
            if plan.strike:
                add_strike(booking.teacher, plan.strike, booking=booking)

            meeting_id, booking_pk = booking.zoom_meeting_id, str(booking.id)
            gcal = (str(booking.teacher.user_id), booking.teacher_gcal_event_id)
            transaction.on_commit(lambda: _after_cancel(booking_pk, meeting_id, party, gcal))

    if missing_funding:
        raise CancelError(409, 'funding_unavailable', 'We could not find the payment for this lesson, so it cannot be cancelled '
                          'automatically. Our team has been notified and will sort it out.')
    return {'outcome': plan.outcome, 'status': booking.status, 'message': plan.message}


def _after_cancel(booking_id: str, meeting_id: str, cancelled_by: str, gcal: tuple):
    """Best-effort tidy-up outside the money transaction: free the Zoom room and calendar slot, tell the other person."""
    from apps.integrations.tasks import cleanup_gcal_event, cleanup_zoom_meeting, send_cancellation_emails
    if meeting_id:
        cleanup_zoom_meeting.delay(meeting_id)
    if gcal[1]:
        cleanup_gcal_event.delay(*gcal)
    send_cancellation_emails.delay(booking_id, cancelled_by)
