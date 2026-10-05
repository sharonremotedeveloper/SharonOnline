"""
Admin-initiated cancellation of a suspended (or removed) tutor's future lessons (slice T1b, plan §3.1).

The tutor-cancel path cannot be used: `party_of` refuses staff, and a late tutor cancel would strike the very tutor being
suspended. Outcomes (docs/CANCELLATION_AND_REFUNDS.md "Admin cancel"):

    booking          outcome           student's money                                tutor
    pending_payment  released          nothing was taken (a late payment is quarantined, webhook_handler DEF-501 guard)   -
    confirmed        admin_refund      full refund of the capture through refunds.request_refund (credit-funded:
                                       credit restored; grace: refund waits for clearance) + ADMIN_CANCEL_BONUS_CREDITS (0)   no strike

The paid booking goes to CANCELLED_BY_TEACHER (terminal, "refunded") with `cancelled_by` = the admin; the audit row names the
admin. One transaction per booking: row lock on the booking, then the tutor (booking -> tutor like every path) re-checked
under its lock. Idempotent: an already cancelled lesson reports `already_cancelled` and moves no money. A hold whose payment is
in flight (recent INITIALIZED attempt, or a PENDING capture) is NOT released: `payment_in_flight`, left to the capture /
webhook path (which refuses or quarantines it for an unbookable tutor). Per-lesson domain errors are reported per lesson; the
default list is capped at BATCH_LIMIT. The student gets the existing cancellation e-mail (N1a/N2 take it over).
"""
import logging
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Exists, Min, OuterRef, Q

from apps.bookings.models import Booking
from apps.bookings.services.holds import inflight_grace
from apps.bookings.services.lock_service import release_slot_lock
from apps.bookings.services.state_machine import InvalidTransition, transition_booking
from apps.common import clock
from apps.payments.models import CreditBundle, PaymentTransaction, RefundRequest
from apps.payments.services import refunds
from apps.payments.services.credits import grant_credit
from apps.payments.services.funding import funding_for_settlement
from apps.payments.services.ledger_service import record_compensation_entry
from apps.teachers.models import TeacherProfile

logger = logging.getLogger(__name__)

S = Booking.Status
CANCELLABLE_TUTOR_STATUSES = (TeacherProfile.Status.SUSPENDED, TeacherProfile.Status.REJECTED)
FUTURE_LESSON_STATUSES = (S.PENDING_PAYMENT, S.CONFIRMED)
ALREADY_CANCELLED = (S.CANCELLED, S.CANCELLED_BY_TEACHER, S.CANCELLED_BY_STUDENT, S.STUDENT_LATE_CANCELLED)
BATCH_LIMIT = 50            # lessons per request when no explicit ids are given


class AdminCancelError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code, self.code, self.message = status_code, code, message


@dataclass(frozen=True)
class AdminCancelOutcome:
    booking_id: object
    outcome: str        # admin_refund | released | payment_in_flight | already_cancelled | not_cancellable | funding_unavailable | not_found
    status: str = ''


def future_lessons_q(now) -> Q:
    return Q(bookings__status__in=FUTURE_LESSON_STATUSES, bookings__start_time_utc__gt=now)


def future_lesson_ids(teacher_id, now=None) -> list:
    return list(Booking.objects.filter(teacher_id=teacher_id, status__in=FUTURE_LESSON_STATUSES,
                                       start_time_utc__gt=now or clock.now())
                .order_by('start_time_utc').values_list('id', flat=True))


def tutors_needing_action(now=None):
    """Staff work queue: unbookable tutors (suspended / removed) who still have future lessons, soonest lesson first."""
    now = now or clock.now()
    return (TeacherProfile.objects.filter(status__in=CANCELLABLE_TUTOR_STATUSES)
            .annotate(future_lesson_count=Count('bookings', filter=future_lessons_q(now)),
                      next_lesson_start_utc=Min('bookings__start_time_utc', filter=future_lessons_q(now)))
            .filter(future_lesson_count__gt=0).select_related('user').order_by('next_lesson_start_utc', 'pk'))


@dataclass(frozen=True)
class AdminCancelBatch:
    results: list
    remaining: bool = False         # the default list was capped at BATCH_LIMIT: call again for the rest


def _in_flight_exists(now):
    """A payment the gateway may still complete: a recent INITIALIZED attempt (the hold's own in-flight window) or a PENDING capture."""
    return Exists(PaymentTransaction.objects.filter(booking=OuterRef('pk')).filter(
        Q(status=PaymentTransaction.Status.PENDING_CAPTURE)
        | Q(status=PaymentTransaction.Status.INITIALIZED, created_at__gte=now - inflight_grace())))


def payment_in_flight(booking, now) -> bool:
    return Booking.objects.filter(pk=booking.pk).filter(_in_flight_exists(now)).exists()


def cancel_future_lessons(teacher_id, actor, *, reason: str, booking_ids=None, now=None) -> AdminCancelBatch:
    """
    Cancel each lesson in its own transaction; one failure never undoes the others. Raises AdminCancelError (404/409).
    Without `booking_ids` at most BATCH_LIMIT lessons are handled per call (`remaining` says whether more are left); holds with
    a payment in flight are reported as `payment_in_flight` and never count against the cap.
    """
    now = now or clock.now()
    tutor = TeacherProfile.objects.filter(pk=teacher_id).only('id', 'status').first()
    if tutor is None:
        raise AdminCancelError(404, 'not_found', 'Tutor not found.')
    if tutor.status not in CANCELLABLE_TUTOR_STATUSES:
        raise AdminCancelError(409, 'tutor_not_suspended',
                               'Only a suspended or removed tutor\'s lessons are cancelled by staff; suspend the tutor first.')
    flagged: list = []
    if booking_ids:
        ids, remaining = list(booking_ids), False
    else:
        ids = future_lesson_ids(teacher_id, now)
        in_flight = set(Booking.objects.filter(pk__in=ids, status=S.PENDING_PAYMENT).filter(_in_flight_exists(now))
                        .values_list('id', flat=True))
        flagged = [AdminCancelOutcome(i, 'payment_in_flight', S.PENDING_PAYMENT) for i in ids if i in in_flight]
        ids = [i for i in ids if i not in in_flight]
        ids, remaining = ids[:BATCH_LIMIT], len(ids) > BATCH_LIMIT
    done = [admin_cancel_booking(bid, actor, teacher_id=teacher_id, reason=reason, now=now) for bid in ids]
    return AdminCancelBatch(done + flagged, remaining)


def admin_cancel_booking(booking_id, actor, *, teacher_id, reason: str, now=None) -> AdminCancelOutcome:
    now = now or clock.now()
    try:
        with transaction.atomic():
            outcome = _cancel_locked(booking_id, actor, teacher_id, reason, now)
    except refunds.AlreadySettled:
        outcome = AdminCancelOutcome(booking_id, 'not_cancellable', '')
    except refunds.MissingFunding:
        outcome = AdminCancelOutcome(booking_id, 'funding_unavailable', '')
    except (refunds.RefundStateError, InvalidTransition):           # per-lesson domain errors never abort the batch
        outcome = AdminCancelOutcome(booking_id, 'not_cancellable', '')
    logger.info('admin cancel: booking %s tutor %s outcome %s', booking_id, teacher_id, outcome.outcome)
    return outcome


def _cancel_locked(booking_id, actor, teacher_id, reason, now) -> AdminCancelOutcome:
    # Lock order booking -> tutor, like every other path; the tutor is re-read under its lock so a concurrent `reactivate`
    # (which holds the tutor lock) either finishes first (we then refuse) or waits for us.
    booking = (Booking.objects.select_for_update(of=('self',)).select_related('teacher__user', 'student')
               .filter(pk=booking_id, teacher_id=teacher_id).first())
    if booking is None:
        return AdminCancelOutcome(booking_id, 'not_found')
    tutor_status = (TeacherProfile.objects.select_for_update().only('id', 'status').get(pk=teacher_id)).status
    if booking.status in ALREADY_CANCELLED:
        return AdminCancelOutcome(booking.id, 'already_cancelled', booking.status)
    if tutor_status not in CANCELLABLE_TUTOR_STATUSES:
        return AdminCancelOutcome(booking.id, 'not_cancellable', booking.status)
    if booking.status == S.PENDING_PAYMENT:
        if payment_in_flight(booking, now):          # the gateway may still take the money: leave it to the payment path
            return AdminCancelOutcome(booking.id, 'payment_in_flight', booking.status)
        _transition(booking, S.CANCELLED, actor, reason, now)
        _after_commit(booking, unpaid=True)
        return AdminCancelOutcome(booking.id, 'released', booking.status)
    if booking.status != S.CONFIRMED or booking.start_time_utc <= now:
        return AdminCancelOutcome(booking.id, 'not_cancellable', booking.status)

    funding = funding_for_settlement(booking, context='admin_cancellation')
    if funding is None:                        # anomaly recorded by funding_for_settlement; nothing else changes
        return AdminCancelOutcome(booking.id, 'funding_unavailable', booking.status)
    _transition(booking, S.CANCELLED_BY_TEACHER, actor, reason, now)
    refunds.request_refund(booking, RefundRequest.Reason.TEACHER_CANCEL,
                           description='Lesson cancelled by staff: the tutor is no longer available')
    _bonus(booking, funding)
    _after_commit(booking, unpaid=False)
    return AdminCancelOutcome(booking.id, 'admin_refund', booking.status)


def _transition(booking, to_status, actor, reason, now):
    booking.cancelled_at, booking.cancelled_by, booking.cancel_reason = now, actor, reason[:255]
    transition_booking(booking, to_status, actor=actor, reason=f'admin cancel: {reason}'[:255],
                       update_fields=('cancelled_at', 'cancelled_by', 'cancel_reason'))


def _bonus(booking, funding):
    credits = settings.ADMIN_CANCEL_BONUS_CREDITS            # PROVISIONAL 0 (plan §9)
    if credits <= 0:
        return
    grant_credit(booking.student, credits=credits, source=CreditBundle.Source.BONUS, pack_name='Lesson cancelled by staff',
                 unit_amount=funding.captured_amount, currency=funding.currency, fx_rate_to_zar=funding.fx_rate_to_zar,
                 fx_source=funding.fx_source, booking=booking, idempotency_key=f'admin-cancel-bonus:{booking.id}')
    record_compensation_entry(user=booking.student, booking=booking, amount_usd=funding.captured_amount * credits,
                              currency=funding.currency, fx_rate_to_zar=funding.fx_rate_to_zar, fx_source=funding.fx_source,
                              reason='Lesson cancelled by staff (tutor suspended)')


def _after_commit(booking, *, unpaid: bool):
    """Outside the money transaction: free the hold / Zoom room / calendar event, tell the student."""
    from apps.integrations.tasks import cleanup_gcal_event, cleanup_zoom_meeting, send_cancellation_emails
    booking_id, meeting_id = str(booking.id), booking.zoom_meeting_id
    gcal = (str(booking.teacher.user_id), booking.teacher_gcal_event_id)
    lock = (str(booking.teacher_id), booking.start_time_utc.isoformat(), str(booking.student_id), booking.slot_lock_token or None)

    def run():
        if unpaid:
            release_slot_lock(*lock[:3], token=lock[3])
        if meeting_id:
            cleanup_zoom_meeting.delay(meeting_id)
        if gcal[1]:
            cleanup_gcal_event.delay(*gcal)
        send_cancellation_emails.delay(booking_id, 'admin_unpaid' if unpaid else 'admin')
    transaction.on_commit(run)
