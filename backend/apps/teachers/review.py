"""
Explicit staff review actions on a tutor (slice T1b, docs/TUTOR_STATUS_MACHINE.md §9). Every move goes through
teachers/vetting.py::transition_teacher; this module only decides WHICH edges an action takes. There is no path search:
each action names its target, the statuses it may start from, and (for `start-review` only) a fixed lead-in.

    apply_review_action(teacher_id, action, *, actor, reason='') -> ReviewResult
    legacy_verify(teacher_id, *, approve, actor, reason='') -> ReviewResult      # PATCH /admin/teachers/<id>/verify/

`start-review` may lead in through `submitted` from `applied` / `changes_requested`: until slice T5a there is no tutor
"submit" step, so staff receive the application on the tutor's behalf. TODO(T5a): drop the `applied` and
`changes_requested` lead-ins once tutors submit themselves.

All steps of one call run in one transaction under the tutor's row lock: a failure on any step rolls back every step.
A request for the status the tutor already has is a no-op (`changed=False`, no audit row).
"""
from dataclasses import dataclass, field

from django.db import transaction

from apps.teachers import rubric as rubric_rules, vetting
from apps.teachers.models import TeacherProfile

St = TeacherProfile.Status


class TeacherNotFound(vetting.VettingError):
    http_status = 404


class ReasonRequired(vetting.VettingError):
    http_status = 400


@dataclass(frozen=True)
class ReviewAction:
    name: str
    target: str
    sources: frozenset                         # statuses the single edge to `target` starts from
    lead_in: dict = field(default_factory=dict)   # status -> fixed steps taken before `target`
    needs_reason: bool = False                 # decisions the tutor is told about carry a reason


ACTIONS = {a.name: a for a in (
    ReviewAction('start-review', St.IN_REVIEW, frozenset({St.SUBMITTED}),
                 {St.APPLIED: (St.SUBMITTED,), St.CHANGES_REQUESTED: (St.SUBMITTED,)}),
    ReviewAction('approve', St.APPROVED, frozenset({St.IN_REVIEW})),
    ReviewAction('request-changes', St.CHANGES_REQUESTED, frozenset({St.IN_REVIEW}), needs_reason=True),
    ReviewAction('reject', St.REJECTED, frozenset({St.IN_REVIEW, St.SUSPENDED}), needs_reason=True),
    ReviewAction('suspend', St.SUSPENDED, frozenset({St.APPROVED}), needs_reason=True),
    ReviewAction('reactivate', St.APPROVED, frozenset({St.SUSPENDED})),
    ReviewAction('revet', St.IN_REVIEW, frozenset({St.APPROVED})),
    ReviewAction('reopen', St.APPLIED, frozenset({St.REJECTED})),
)}


@dataclass(frozen=True)
class ReviewResult:
    teacher_id: object
    action: str
    previous_status: str
    status: str
    change_ids: tuple = ()
    affected_booking_ids: tuple = ()

    @property
    def changed(self) -> bool:
        return bool(self.change_ids)


def steps_for(action: ReviewAction, current: str, teacher_id=None) -> tuple:
    """The statuses `action` moves through from `current` (empty when already there); 409 when it may not start here."""
    if current == action.target:
        return ()
    if current in action.lead_in:
        return (*action.lead_in[current], action.target)
    if current in action.sources:
        return (action.target,)
    raise vetting.InvalidTeacherTransition(teacher_id, current, action.target)


def _lock(teacher_id):
    locked = (TeacherProfile.objects.select_for_update().only('id', 'status', 'user_id', 'updated_at')
              .filter(pk=teacher_id).first())
    if locked is None:
        raise TeacherNotFound(f'Tutor {teacher_id} not found.')
    return locked


def _check(actor, reason, needs_reason):
    if not vetting.is_staff_user(actor):
        raise vetting.TransitionNotPermitted(None, '', '', 'non-staff')
    if needs_reason and not (reason or '').strip():
        raise ReasonRequired('A reason is required for this decision.')


def _run(locked, action_name, steps, actor, reason, evidence=None) -> ReviewResult:
    """`evidence` (rubric / reviewed assets, slice T4a) is recorded on the decision step only, never on a lead-in step."""
    previous = locked.status
    change_ids, affected = [], ()
    for index, step in enumerate(steps):      # steps_for never yields the current status, so every step is a real change
        extra = evidence if index == len(steps) - 1 and evidence else {}
        result = vetting.transition_teacher(locked, step, actor=actor, reason=(reason or '').strip(), **extra)
        change_ids.append(result.change_id)
        affected = result.affected_booking_ids or affected
    return ReviewResult(locked.pk, action_name, previous, locked.status, tuple(change_ids), affected)


def _evidence(action_name, locked, rubric, reviewed_assets, requested_changes) -> dict:
    """Checks the rubric rules for the action (T4a) and returns the extra audit data for the decision step."""
    if action_name == 'approve':
        stored, live = rubric_rules.check_approval(locked, rubric, reviewed_assets)
        return {'rubric': stored, 'reviewed_assets': live}
    if action_name == 'request-changes':
        return {'rubric': {'version': 1, 'requested_changes': rubric_rules.check_requested_changes(requested_changes)}}
    return {}


def apply_review_action(teacher_id, action_name: str, *, actor, reason: str = '', rubric=None, reviewed_assets=None,
                        requested_changes=None) -> ReviewResult:
    action = ACTIONS[action_name]
    _check(actor, reason, action.needs_reason)
    with transaction.atomic():
        locked = _lock(teacher_id)
        steps = steps_for(action, locked.status, locked.pk)
        evidence = _evidence(action_name, locked, rubric, reviewed_assets, requested_changes) if steps else {}
        return _run(locked, action.name, steps, actor, reason, evidence)


def legacy_verify(teacher_id, *, approve: bool, actor, reason: str = '', rubric=None,
                  reviewed_assets=None) -> ReviewResult:
    """
    The Slice 8 contract (approve / reject in one call) built from the explicit actions: `start-review` when the
    application has not reached a reviewer yet, then `approve` / `reject`. Never passes through `approved` on the way to
    `rejected`; a live tutor (approve -> reject) or a lifecycle move (reactivate, reopen) is 409 here.
    """
    final = ACTIONS['approve' if approve else 'reject']
    start = ACTIONS['start-review']
    _check(actor, reason or 'legacy-verify', False)
    with transaction.atomic():
        locked = _lock(teacher_id)
        current = locked.status
        steps = ()
        if current in start.sources or current in start.lead_in:      # never approved / rejected: no lead-in for them
            steps = steps_for(start, current, locked.pk)
            current = start.target
        decision = steps_for(final, current, locked.pk)
        evidence = _evidence(final.name, locked, rubric, reviewed_assets, None) if decision else {}
        return _run(locked, f'legacy-{final.name}', (*steps, *decision), actor, reason or 'legacy-verify', evidence)
