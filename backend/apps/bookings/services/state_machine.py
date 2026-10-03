"""
The only place allowed to change `Booking.status` (enforced by tests/test_booking_state_machine.py::TestNoDirectStatusWrites).

    transition_booking(booking, to_status, *, actor, reason='') -> TransitionResult

* Re-reads the row with SELECT ... FOR UPDATE, so the decision is made on the database's truth, not on a stale in-memory copy.
* Illegal moves raise `InvalidTransition` (callers map it to 409 / skip-and-continue).
* Re-requesting the status the booking already has is a no-op (`changed=False`): callers run their side effects only
  `if result.changed`, which makes retries, duplicate webhooks and overlapping Celery runs idempotent.
* Every real change writes a `BookingStatusChange` row in the same transaction.

The map below documents the lifecycle; see docs/BOOKING_STATE_MACHINE.md for the diagram and the rule for adding edges.
"""
from dataclasses import dataclass
from typing import Iterable

from django.db import transaction

from apps.bookings.models import Booking, BookingStatusChange

S = Booking.Status

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    # Slot held, awaiting payment. CONFIRMED on a verified payment; CANCELLED when the hold expires;
    # DISPUTED when the payment lands on a slot that is no longer available (DEF-501).
    S.PENDING_PAYMENT: frozenset({S.CONFIRMED, S.CANCELLED, S.DISPUTED}),
    # Paid and scheduled.
    S.CONFIRMED: frozenset({
        S.IN_PROGRESS,              # someone joined (Zoom webhook / active probe)
        S.TEACHER_NO_SHOW, S.STUDENT_NO_SHOW,   # T+10m adjudication
        S.INTERRUPTED_POWER,        # outage reported
        S.CANCELLED_BY_STUDENT,     # student cancelled more than STUDENT_FREE_CANCEL_HOURS out: refunded
        S.STUDENT_LATE_CANCELLED,   # student cancelled inside that window: fee kept, tutor paid at +24h
        S.CANCELLED_BY_TEACHER,     # tutor cancelled: refunded (+ bonus credit and a strike when late)
        S.COMPLETED_PENDING_MEMO,   # lesson ended with >=20 teacher minutes
        S.DISPUTED,                 # lesson ended with <20 teacher minutes
        S.CANCELLED,                # grace booking whose PENDING PayPal payment failed before the lesson (payments/services/grace.py)
    }),
    S.IN_PROGRESS: frozenset({
        S.COMPLETED_PENDING_MEMO, S.DISPUTED, S.INTERRUPTED_POWER,
        S.STUDENT_NO_SHOW,          # active Zoom probe revived a "teacher absent" case, but the student never joined
    }),
    # Adjudicated absences can be overturned by late attendance telemetry -> admin arbitration.
    S.TEACHER_NO_SHOW: frozenset({S.DISPUTED}),
    S.STUDENT_NO_SHOW: frozenset({S.DISPUTED}),
    # Lesson happened, memo outstanding.
    S.COMPLETED_PENDING_MEMO: frozenset({S.COMPLETED, S.COMPLETED_MEMO_FORFEITED}),
    S.COMPLETED: frozenset({S.COMPLETED_MEMO_FORFEITED}),  # e.g. dispute-released lesson that never got a memo
    S.COMPLETED_MEMO_FORFEITED: frozenset({S.COMPLETED}),  # a late memo is still accepted
    # Awaiting an admin decision (ResolveDisputeView).
    S.DISPUTED: frozenset({S.CANCELLED, S.COMPLETED}),
    # A payment arriving after the hold was purged may re-confirm the slot if it is still free, or be quarantined.
    S.CANCELLED: frozenset({S.CONFIRMED, S.DISPUTED}),
    S.INTERRUPTED_POWER: frozenset(),  # terminal
    # Cancellations are terminal, and deliberately NOT S.CANCELLED: that status may be re-confirmed by a late payment
    # (cancelled -> confirmed), which must never resurrect a booking whose money has already been refunded or settled.
    S.CANCELLED_BY_STUDENT: frozenset(),
    S.STUDENT_LATE_CANCELLED: frozenset(),
    S.CANCELLED_BY_TEACHER: frozenset(),
}

TERMINAL_STATUSES = frozenset(s for s, targets in ALLOWED_TRANSITIONS.items() if not targets)


class InvalidTransition(Exception):
    def __init__(self, booking_id, from_status, to_status):
        self.booking_id, self.from_status, self.to_status = booking_id, from_status, to_status
        super().__init__(f"Booking {booking_id}: illegal status change '{from_status}' -> '{to_status}'.")


@dataclass(frozen=True)
class TransitionResult:
    changed: bool
    from_status: str
    to_status: str


def can_transition(from_status: str, to_status: str) -> bool:
    return from_status == to_status or to_status in ALLOWED_TRANSITIONS.get(from_status, frozenset())


def _actor_fields(actor):
    """A User instance (human action) or a string naming the automated source ('system:purge_expired')."""
    if isinstance(actor, str):
        return actor[:80], None
    if actor is None:
        raise ValueError("transition_booking needs an actor: a User or a 'system:<source>' string.")
    return f"user:{actor.get_username()}"[:80], actor


def transition_booking(booking: Booking, to_status: str, *, actor, reason: str = '',
                       update_fields: Iterable[str] = ()) -> TransitionResult:
    """
    Move `booking` to `to_status`. `booking` is refreshed in place (status, updated_at) on success.
    `update_fields` lets the caller persist other columns it set on the instance in the same locked write.
    """
    if to_status not in Booking.Status.values:
        raise ValueError(f"'{to_status}' is not a Booking status.")
    actor_label, actor_user = _actor_fields(actor)

    with transaction.atomic():
        locked = Booking.objects.select_for_update().only('id', 'status').get(pk=booking.pk)
        current = locked.status
        if current == to_status:
            booking.status = current
            return TransitionResult(False, current, to_status)
        if not can_transition(current, to_status):
            raise InvalidTransition(booking.pk, current, to_status)

        booking.status = to_status
        try:
            booking.save(update_fields=['status', 'updated_at', *update_fields])
            BookingStatusChange.objects.create(
                booking=booking, from_status=current, to_status=to_status,
                actor=actor_label, actor_user=actor_user, reason=reason[:255])
        except BaseException:
            booking.status = current  # e.g. IntegrityError on the active-slot constraint: leave the instance truthful
            raise
    return TransitionResult(True, current, to_status)
