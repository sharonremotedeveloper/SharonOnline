"""
The only writer of `TeacherProfile.status` (plan §3.1, docs/TUTOR_STATUS_MACHINE.md; guard (a) in
tests/guards/test_guard_teacher_status_writes.py fails the build on any other write).

    transition_teacher(teacher, to_status, *, actor, reason='', rubric=None, reviewed_assets=None) -> TeacherTransitionResult
    create_teacher_profile(user, *, status='applied', actor, reason='', **fields) -> TeacherProfile

* `actor` is a User (STAFF when a platform admin, SELF when it is the tutor's own account) or a 'system:<source>' string
  (SYSTEM). STAFF may take every edge; SELF and SYSTEM only the edges listed for them in ALLOWED_TRANSITIONS.
* The decision is made on the row re-read with SELECT ... FOR UPDATE (the tutor row only: this module NEVER locks a booking,
  so it cannot join a booking/tutor lock cycle; every booking path, reviews included since T1b, locks booking -> tutor).
* An illegal edge raises InvalidTeacherTransition (409); a legal edge the actor may not take raises TransitionNotPermitted
  (403); an unknown status or a missing / malformed actor is a ValueError (a programming error).
* Re-requesting the current status is a no-op (`changed=False`, no audit row): retries and duplicate jobs are idempotent.
* Every real change writes one immutable TeacherStatusChange row in the same transaction, then (after commit) calls the
  notification hook, a no-op until N1a.
* A move to SUSPENDED returns the tutor's future pending/confirmed bookings (read only); cancelling them is a separate,
  per-booking admin action (bookings/services/admin_cancellation.py), never done here.
"""
import logging
from dataclasses import dataclass

from django.db import transaction

from apps.common import clock
from apps.teachers.models import TeacherProfile, TeacherStatusChange

logger = logging.getLogger(__name__)

St = TeacherProfile.Status
SELF, STAFF, SYSTEM = 'self', 'staff', 'system'

# edge -> actor kinds that may take it. STAFF is listed explicitly on every edge (it may take them all).
ALLOWED_TRANSITIONS: dict[str, dict[str, frozenset[str]]] = {
    St.APPLIED: {St.SUBMITTED: frozenset({SELF, STAFF})},                 # the applicant sends the application
    St.SUBMITTED: {St.IN_REVIEW: frozenset({STAFF})},                      # a reviewer picks it up
    St.IN_REVIEW: {
        St.APPROVED: frozenset({STAFF}),
        St.CHANGES_REQUESTED: frozenset({STAFF}),                          # e.g. re-record the intro video
        St.REJECTED: frozenset({STAFF}),
    },
    St.CHANGES_REQUESTED: {St.SUBMITTED: frozenset({SELF, STAFF})},       # re-submitted after the changes
    St.APPROVED: {
        St.SUSPENDED: frozenset({STAFF, SYSTEM}),                          # admin decision or the strike limit
        St.IN_REVIEW: frozenset({STAFF, SELF, SYSTEM}),                    # re-vet after a vetted asset changed (TEA-11)
    },
    St.SUSPENDED: {
        St.APPROVED: frozenset({STAFF}),                                   # only a human reinstates
        St.REJECTED: frozenset({STAFF}),                                   # permanent removal (Anesu 2026-10-05, T1b)
    },
    St.REJECTED: {St.APPLIED: frozenset({STAFF})},                         # re-application
}


class VettingError(Exception):
    http_status = 400


class InvalidTeacherTransition(VettingError):
    http_status = 409

    def __init__(self, teacher_id, from_status, to_status):
        self.teacher_id, self.from_status, self.to_status = teacher_id, from_status, to_status
        super().__init__(f"Tutor {teacher_id}: illegal status change '{from_status}' -> '{to_status}'.")


class TransitionNotPermitted(VettingError):
    http_status = 403

    def __init__(self, teacher_id, from_status, to_status, actor_kind):
        self.teacher_id, self.from_status, self.to_status, self.actor_kind = teacher_id, from_status, to_status, actor_kind
        super().__init__(f"Tutor {teacher_id}: '{from_status}' -> '{to_status}' is not permitted for {actor_kind}.")


@dataclass(frozen=True)
class TeacherTransitionResult:
    changed: bool
    from_status: str
    to_status: str
    change_id: object = None
    affected_booking_ids: tuple = ()


def notify_status_change(change_id) -> None:
    """Notification hook (plan §6 `vetting:{change_id}` / `suspended:{change_id}`). No-op shim until N1a lands."""
    logger.info('tutor status change %s committed', change_id)


def _is_staff(user) -> bool:
    return getattr(user, 'role', None) == 'admin' or bool(user.is_staff) or bool(user.is_superuser)


def is_staff_user(actor) -> bool:
    """STAFF by the same rule as IsPlatformAdmin; False for system strings, None and anonymous users."""
    return hasattr(actor, 'get_username') and bool(getattr(actor, 'is_authenticated', False)) and _is_staff(actor)


def _actor(actor, teacher_user_id):
    """(kind, label, user) for an actor; kind is None for a user who is neither staff nor the tutor."""
    if isinstance(actor, str):
        if not actor.startswith('system:') or len(actor) <= len('system:'):
            raise ValueError("A system actor must be a 'system:<source>' string.")
        return SYSTEM, actor[:80], None
    if actor is None or not hasattr(actor, 'get_username'):
        raise ValueError("The tutor status service needs an actor: a User or a 'system:<source>' string.")
    label = f'user:{actor.get_username()}'[:80]
    if _is_staff(actor):
        return STAFF, label, actor
    return (SELF if actor.pk == teacher_user_id else None), label, actor


def _check_status(status):
    if status not in St.values:
        raise ValueError(f"'{status}' is not a tutor status.")


def _future_bookings(teacher_id) -> tuple:
    """Plain read (no lock) of the lessons a suspension leaves without a tutor."""
    from apps.bookings.models import Booking
    return tuple(Booking.objects.filter(
        teacher_id=teacher_id, status__in=[Booking.Status.PENDING_PAYMENT, Booking.Status.CONFIRMED],
        start_time_utc__gt=clock.now()).order_by('start_time_utc').values_list('id', flat=True))


def _record(teacher_id, from_status, to_status, label, user, reason, rubric, reviewed_assets):
    return TeacherStatusChange.objects.create(
        teacher_id=teacher_id, from_status=from_status, to_status=to_status, actor=label, actor_user=user,
        reason=(reason or '')[:500], rubric=rubric, reviewed_assets=reviewed_assets or {})


def transition_teacher(teacher, to_status, *, actor, reason='', rubric=None, reviewed_assets=None) -> TeacherTransitionResult:
    """Move `teacher` to `to_status`; `teacher` is refreshed in place (status and the generated flags)."""
    _check_status(to_status)
    with transaction.atomic():
        locked = TeacherProfile.objects.select_for_update().only('id', 'status', 'user_id', 'updated_at').get(pk=teacher.pk)
        kind, label, user = _actor(actor, locked.user_id)
        current = locked.status
        if kind is None:
            raise TransitionNotPermitted(locked.pk, current, to_status, 'another user')
        if current == to_status:
            teacher.refresh_from_db(fields=_FRESH_FIELDS)
            return TeacherTransitionResult(False, current, to_status)
        allowed = ALLOWED_TRANSITIONS.get(current, {})
        if to_status not in allowed:
            raise InvalidTeacherTransition(locked.pk, current, to_status)
        if kind not in allowed[to_status]:
            raise TransitionNotPermitted(locked.pk, current, to_status, kind)

        locked.status = to_status
        locked.save(update_fields=['status', 'updated_at'])
        change = _record(locked.pk, current, to_status, label, user, reason, rubric, reviewed_assets)
        affected = _future_bookings(locked.pk) if to_status == St.SUSPENDED else ()
        transaction.on_commit(lambda: notify_status_change(change.id))
        teacher.refresh_from_db(fields=_FRESH_FIELDS)
    logger.info('tutor %s status %s -> %s (change %s)', locked.pk, current, to_status, change.id)
    return TeacherTransitionResult(True, current, to_status, change.id, affected)


def create_teacher_profile(user, *, status=St.APPLIED, actor, reason='', **fields) -> TeacherProfile:
    """
    Create a tutor profile in `status` with its baseline audit row (from_status ''). STAFF and SYSTEM may create any
    status; the tutor (SELF) only `applied`; anyone else nothing.
    """
    _check_status(status)
    kind, label, actor_user = _actor(actor, user.pk)
    if kind is None or (kind == SELF and status != St.APPLIED):
        raise TransitionNotPermitted(None, '', status, kind or 'another user')
    with transaction.atomic():
        profile = TeacherProfile.objects.create(user=user, status=status, **fields)
        _record(profile.pk, '', status, label, actor_user, reason, None, None)
    return profile


def record_baseline(profile, *, actor, reason='') -> None:
    """Baseline audit row for a profile created outside create_teacher_profile (the Django admin "add" form)."""
    _kind, label, actor_user = _actor(actor, profile.user_id)
    _record(profile.pk, '', profile.status, label, actor_user, reason, None, None)


_FRESH_FIELDS = ['status', 'is_verified', 'is_active', 'updated_at']
