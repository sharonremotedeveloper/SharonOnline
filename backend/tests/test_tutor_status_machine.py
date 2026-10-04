"""
T1a: the tutor status machine (plan §3.1, docs/TUTOR_STATUS_MACHINE.md).

`TeacherProfile.status` is the only stored column; `is_verified` / `is_active` are GeneratedFields of it, and the one writer
is `apps.teachers.vetting.transition_teacher` (allowed-transition table + actor policy + row lock + immutable audit row).
"""
from datetime import timedelta
from itertools import product

import pytest
from django.utils import timezone

import factories as f
from apps.bookings.models import Booking
from apps.teachers import vetting
from apps.teachers.models import TeacherProfile, TeacherStatusChange
from apps.teachers.vetting import (InvalidTeacherTransition, TeacherTransitionResult, TransitionNotPermitted,
                                   VettingError, create_teacher_profile, transition_teacher)

pytestmark = pytest.mark.django_db
St = TeacherProfile.Status

# Plan §3.1, the only truth table: status -> (is_verified, is_active).
TRUTH_TABLE = {
    'applied': (False, True), 'submitted': (False, True), 'in_review': (False, True), 'changes_requested': (False, True),
    'rejected': (False, False), 'approved': (True, True), 'suspended': (True, False),
}
# Plan §3.1 / architect brief: edge -> actor kinds allowed to take it (staff may take every edge).
PLAN_EDGES = {
    ('applied', 'submitted'): {'self', 'staff'},
    ('submitted', 'in_review'): {'staff'},
    ('in_review', 'approved'): {'staff'},
    ('in_review', 'changes_requested'): {'staff'},
    ('in_review', 'rejected'): {'staff'},
    ('changes_requested', 'submitted'): {'self', 'staff'},
    ('approved', 'suspended'): {'staff', 'system'},
    ('suspended', 'approved'): {'staff'},
    ('approved', 'in_review'): {'staff', 'self', 'system'},
    ('rejected', 'applied'): {'staff'},
}


def actor_of(kind, profile):
    if kind == 'staff':
        return f.make_admin()
    if kind == 'self':
        return profile.user
    return 'system:test'


# ------------------------------------------------------------------ the field and the truth table
def test_status_choices_are_the_seven_plan_states():
    from apps.teachers import models as m
    assert set(St.values) == set(TRUTH_TABLE) == set(m.STATUS_VALUES)
    assert set(m.VERIFIED_STATUSES) == {s for s, (v, _a) in TRUTH_TABLE.items() if v}
    assert set(m.ACTIVE_STATUSES) == {s for s, (_v, a) in TRUTH_TABLE.items() if a}


def test_a_new_profile_starts_applied_without_training():
    profile = TeacherProfile.objects.create(user=f.make_user(role='teacher'))
    assert profile.status == St.APPLIED and profile.training_completed_at is None


@pytest.mark.parametrize('status,flags', TRUTH_TABLE.items())
def test_generated_flags_follow_the_truth_table(status, flags):
    profile = f.make_teacher_profile(status=status)
    assert (profile.is_verified, profile.is_active) == flags            # returned by the INSERT
    profile.refresh_from_db()
    assert (profile.is_verified, profile.is_active) == flags
    assert TeacherProfile.objects.filter(pk=profile.pk, is_verified=flags[0], is_active=flags[1]).exists()


def test_flags_are_generated_fields():
    for name in ('is_verified', 'is_active'):
        assert TeacherProfile._meta.get_field(name).generated is True


# ------------------------------------------------------------------ tripwires against silent drops
def test_constructor_refuses_the_derived_flags():
    for kwargs in ({'is_verified': True}, {'is_active': False}):
        with pytest.raises(TypeError):
            TeacherProfile(user=f.make_user(role='teacher'), **kwargs)
    with pytest.raises(TypeError):
        TeacherProfile.objects.create(user=f.make_user(role='teacher'), is_verified=True)


def test_save_with_update_fields_on_a_flag_raises():
    profile = f.make_teacher_profile()
    for fields in (['is_active'], ['is_verified'], ['bio', 'is_active']):
        with pytest.raises(ValueError):
            profile.save(update_fields=fields)


def test_queryset_update_of_a_flag_raises():
    profile = f.make_teacher_profile()
    for kwargs in ({'is_active': False}, {'is_verified': False}):
        with pytest.raises(ValueError):
            TeacherProfile.objects.filter(pk=profile.pk).update(**kwargs)
    with pytest.raises(ValueError):
        TeacherProfile.objects.bulk_update([profile], ['is_active'])
    profile.refresh_from_db()
    assert (profile.is_verified, profile.is_active) == (True, True)


def test_other_updates_still_work():
    profile = f.make_teacher_profile()
    assert TeacherProfile.objects.filter(pk=profile.pk).update(bio='hello') == 1
    profile.bio = 'again'
    profile.save(update_fields=['bio'])
    profile.refresh_from_db()
    assert profile.bio == 'again'


def test_the_database_refuses_an_unknown_status():
    from django.db import IntegrityError, transaction
    profile = f.make_teacher_profile()
    with pytest.raises(IntegrityError), transaction.atomic():
        TeacherProfile.objects.filter(pk=profile.pk).update(status='verified')


# ------------------------------------------------------------------ the transition table
def test_allowed_table_matches_the_plan():
    table = {(src, dst): set(kinds) for src, targets in vetting.ALLOWED_TRANSITIONS.items() for dst, kinds in targets.items()}
    assert table == PLAN_EDGES


@pytest.mark.parametrize('edge', sorted(PLAN_EDGES))
def test_every_allowed_edge_works_for_staff_and_writes_one_audit_row(edge):
    src, dst = edge
    profile = f.make_teacher_profile(status=src)
    admin = f.make_admin()
    result = transition_teacher(profile, dst, actor=admin, reason='because')
    assert isinstance(result, TeacherTransitionResult)
    assert (result.changed, result.from_status, result.to_status) == (True, src, dst)
    assert profile.status == dst and (profile.is_verified, profile.is_active) == TRUTH_TABLE[dst]   # instance is fresh
    change = TeacherStatusChange.objects.get(teacher=profile)
    assert change.id == result.change_id
    assert (change.from_status, change.to_status, change.actor_user, change.reason) == (src, dst, admin, 'because')
    assert change.actor == f'user:{admin.get_username()}'


ILLEGAL = sorted((a, b) for a, b in product(TRUTH_TABLE, TRUTH_TABLE) if a != b and (a, b) not in PLAN_EDGES)


@pytest.mark.parametrize('edge', ILLEGAL)
def test_every_illegal_pair_raises_and_changes_nothing(edge):
    src, dst = edge
    profile = f.make_teacher_profile(status=src)
    with pytest.raises(InvalidTeacherTransition) as exc:
        transition_teacher(profile, dst, actor=f.make_admin())
    assert exc.value.http_status == 409 and isinstance(exc.value, VettingError)
    profile.refresh_from_db()
    assert profile.status == src and not TeacherStatusChange.objects.exists()


@pytest.mark.parametrize('status', sorted(TRUTH_TABLE))
def test_same_state_is_a_no_op(status):
    profile = f.make_teacher_profile(status=status)
    result = transition_teacher(profile, status, actor='system:test')
    assert (result.changed, result.from_status, result.to_status, result.change_id) == (False, status, status, None)
    assert result.affected_booking_ids == ()
    assert not TeacherStatusChange.objects.exists()


# ------------------------------------------------------------------ actor policy
@pytest.mark.parametrize('edge,kind', sorted((e, k) for e in PLAN_EDGES for k in ('self', 'system')))
def test_self_and_system_take_only_their_edges(edge, kind):
    src, dst = edge
    profile = f.make_teacher_profile(status=src)
    actor = actor_of(kind, profile)
    if kind in PLAN_EDGES[edge]:
        assert transition_teacher(profile, dst, actor=actor).changed
        change = TeacherStatusChange.objects.get(teacher=profile)
        assert change.actor == (actor if kind == 'system' else f'user:{actor.get_username()}')
    else:
        with pytest.raises(TransitionNotPermitted) as exc:
            transition_teacher(profile, dst, actor=actor)
        assert exc.value.http_status == 403
        profile.refresh_from_db()
        assert profile.status == src


@pytest.mark.parametrize('flag', ['is_staff', 'is_superuser', 'role_admin'])
def test_staff_is_any_platform_admin(flag):
    profile = f.make_teacher_profile(status='submitted')
    if flag == 'role_admin':
        actor = f.make_user(role='admin', is_staff=False, is_superuser=False)
    else:
        actor = f.make_user(role='student', **{flag: True})
    assert transition_teacher(profile, 'in_review', actor=actor).changed


def test_another_tutor_or_a_student_is_not_permitted_even_on_a_self_edge():
    profile = f.make_teacher_profile(status='applied')
    for stranger in (f.make_user(role='teacher'), f.make_student()):
        with pytest.raises(TransitionNotPermitted):
            transition_teacher(profile, 'submitted', actor=stranger)
    profile.refresh_from_db()
    assert profile.status == 'applied'


def test_missing_actor_unknown_status_and_bad_actor_string_are_value_errors():
    profile = f.make_teacher_profile(status='applied')
    with pytest.raises(ValueError):
        transition_teacher(profile, 'submitted', actor=None)
    with pytest.raises(ValueError):
        transition_teacher(profile, 'verified', actor='system:test')
    with pytest.raises(ValueError):
        transition_teacher(profile, 'submitted', actor='somebody')
    assert not TeacherStatusChange.objects.exists()


def test_rubric_and_reviewed_assets_are_recorded_and_reason_is_truncated():
    profile = f.make_teacher_profile(status='in_review')
    transition_teacher(profile, 'changes_requested', actor=f.make_admin(), reason='x' * 900,
                       rubric={'accent': 3}, reviewed_assets={'video': 'etag-1'})
    change = TeacherStatusChange.objects.get(teacher=profile)
    assert change.rubric == {'accent': 3} and change.reviewed_assets == {'video': 'etag-1'} and len(change.reason) == 500


# ------------------------------------------------------------------ the decision is made on the database's truth
def test_a_stale_instance_is_judged_by_the_locked_row():
    profile = f.make_teacher_profile(status='approved')
    stale = TeacherProfile.objects.get(pk=profile.pk)
    transition_teacher(profile, 'suspended', actor='system:test')
    assert stale.status == 'approved'
    result = transition_teacher(stale, 'suspended', actor='system:test')       # already suspended in the DB: no-op
    assert result.changed is False and stale.status == 'suspended' and stale.is_active is False
    assert TeacherStatusChange.objects.count() == 1


# ------------------------------------------------------------------ suspension and future lessons
def test_suspension_returns_future_pending_and_confirmed_bookings_without_touching_them():
    tutor = f.make_teacher_profile(status='approved')
    confirmed = f.make_booking(teacher=tutor, status=Booking.Status.CONFIRMED, offset_hours=48)
    pending = f.make_booking(teacher=tutor, status=Booking.Status.PENDING_PAYMENT, offset_hours=72)
    f.make_booking(teacher=tutor, status=Booking.Status.CONFIRMED, start=timezone.now() - timedelta(hours=2))  # past
    f.make_booking(teacher=tutor, status=Booking.Status.CANCELLED, offset_hours=96)
    f.make_booking(status=Booking.Status.CONFIRMED, offset_hours=48)                                          # other tutor
    result = transition_teacher(tutor, 'suspended', actor='system:test')
    assert result.affected_booking_ids == (confirmed.id, pending.id)
    confirmed.refresh_from_db()
    assert confirmed.status == Booking.Status.CONFIRMED


def test_other_transitions_report_no_bookings():
    tutor = f.make_teacher_profile(status='approved')
    f.make_booking(teacher=tutor, status=Booking.Status.CONFIRMED, offset_hours=48)
    assert transition_teacher(tutor, 'in_review', actor='system:test').affected_booking_ids == ()


def test_the_service_never_locks_a_booking():
    from django.db import connection
    from django.test.utils import CaptureQueriesContext
    tutor = f.make_teacher_profile(status='approved')
    f.make_booking(teacher=tutor, status=Booking.Status.CONFIRMED, offset_hours=48)
    with CaptureQueriesContext(connection) as ctx:
        transition_teacher(tutor, 'suspended', actor='system:test')
    booking_sql = [q['sql'] for q in ctx.captured_queries if 'bookings_booking' in q['sql']]
    assert booking_sql and not any('FOR UPDATE' in sql for sql in booking_sql)


def test_a_notification_hook_runs_after_commit(django_capture_on_commit_callbacks, monkeypatch):
    seen = []
    monkeypatch.setattr(vetting, 'notify_status_change', seen.append)
    profile = f.make_teacher_profile(status='in_review')
    with django_capture_on_commit_callbacks(execute=True):
        result = transition_teacher(profile, 'approved', actor=f.make_admin())
    assert seen == [result.change_id]


# ------------------------------------------------------------------ the audit trail is append-only
def test_audit_rows_cannot_be_edited_or_deleted():
    profile = f.make_teacher_profile(status='in_review')
    transition_teacher(profile, 'approved', actor=f.make_admin())
    change = TeacherStatusChange.objects.get()
    change.reason = 'rewritten'
    with pytest.raises(ValueError):
        change.save()
    with pytest.raises(ValueError):
        change.delete()
    with pytest.raises(ValueError):
        TeacherStatusChange.objects.update(reason='rewritten')
    with pytest.raises(ValueError):
        TeacherStatusChange.objects.all().delete()
    assert TeacherStatusChange.objects.get().reason == ''


def test_deleting_the_tutor_still_cascades():
    profile = f.make_teacher_profile(status='in_review')
    transition_teacher(profile, 'approved', actor=f.make_admin())
    profile.user.delete()
    assert not TeacherStatusChange.objects.exists()


# ------------------------------------------------------------------ creating a profile
def test_create_teacher_profile_writes_a_baseline_audit_row():
    user = f.make_user(role='teacher')
    profile = create_teacher_profile(user, actor='system:test', headline='Hi')
    assert profile.status == 'applied' and (profile.is_verified, profile.is_active) == (False, True)
    change = TeacherStatusChange.objects.get(teacher=profile)
    assert (change.from_status, change.to_status, change.actor) == ('', 'applied', 'system:test')


def test_create_teacher_profile_in_a_given_status():
    profile = create_teacher_profile(f.make_user(role='teacher'), status='approved', actor=f.make_admin())
    assert (profile.is_verified, profile.is_active) == (True, True)
    assert TeacherStatusChange.objects.get(teacher=profile).to_status == 'approved'


def test_create_teacher_profile_validates_status_and_actor():
    with pytest.raises(ValueError):
        create_teacher_profile(f.make_user(role='teacher'), status='verified', actor='system:test')
    with pytest.raises(ValueError):
        create_teacher_profile(f.make_user(role='teacher'), actor=None)
    assert not TeacherProfile.objects.exists()


def test_factory_helper_moves_a_tutor_through_the_service():
    profile = f.make_teacher_profile(status='approved')
    f.advance_teacher(profile, 'in_review', 'approved', 'suspended')
    assert profile.status == 'suspended'
    assert list(TeacherStatusChange.objects.values_list('to_status', flat=True)) == ['in_review', 'approved', 'suspended']
