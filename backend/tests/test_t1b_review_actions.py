"""
Slice T1b: explicit staff review actions on the tutor status service, the legacy verify endpoint rebuilt on them (no
path-walking), the admin pending queue, and the staff-only `suspended -> rejected` edge (Anesu, 2026-10-05).
"""
import uuid

import pytest
from rest_framework.test import APIClient

import factories as f
from apps.teachers import vetting
from apps.teachers.models import TeacherStatusChange

pytestmark = pytest.mark.django_db
ACTIONS = ('start-review', 'approve', 'request-changes', 'reject', 'suspend', 'reactivate', 'revet', 'reopen')
# action -> {from_status: statuses the audit trail records, in order}
EXPECTED = {
    'start-review': {'applied': ['submitted', 'in_review'], 'submitted': ['in_review'],
                     'changes_requested': ['submitted', 'in_review']},
    'approve': {'in_review': ['approved']},
    'request-changes': {'in_review': ['changes_requested']},
    'reject': {'in_review': ['rejected'], 'suspended': ['rejected']},
    'suspend': {'approved': ['suspended']},
    'reactivate': {'suspended': ['approved']},
    'revet': {'approved': ['in_review']},
    'reopen': {'rejected': ['applied']},
}
TARGET = {'start-review': 'in_review', 'approve': 'approved', 'request-changes': 'changes_requested', 'reject': 'rejected',
          'suspend': 'suspended', 'reactivate': 'approved', 'revet': 'in_review', 'reopen': 'applied'}
ALL = ('applied', 'submitted', 'in_review', 'changes_requested', 'rejected', 'approved', 'suspended')


def api(user):
    c = APIClient()
    if user is not None:
        c.force_authenticate(user=user)
    return c


def act(user, tutor_id, action, reason='because'):
    body = {} if reason is None else {'reason': reason}
    return api(user).post(f'/api/v1/admin/teachers/{tutor_id}/{action}/', body, format='json')


def trail(tutor):
    return list(TeacherStatusChange.objects.filter(teacher=tutor).order_by('created_at').values_list('to_status', flat=True))


# ------------------------------------------------------------------ the edge decided by Anesu
def test_suspended_to_rejected_is_a_staff_only_edge():
    assert vetting.ALLOWED_TRANSITIONS['suspended']['rejected'] == frozenset({vetting.STAFF})
    tutor = f.make_teacher_profile(status='suspended')
    with pytest.raises(vetting.TransitionNotPermitted):
        vetting.transition_teacher(tutor, 'rejected', actor='system:strikes')
    assert vetting.transition_teacher(tutor, 'rejected', actor=f.make_admin(), reason='permanent').changed
    assert tutor.status == 'rejected'


# ------------------------------------------------------------------ explicit actions
class TestExplicitActions:
    @pytest.mark.parametrize('action,start', [(a, s) for a, m in EXPECTED.items() for s in m])
    def test_each_allowed_start_moves_to_the_target_with_one_row_per_edge(self, admin_user, action, start):
        tutor = f.make_teacher_profile(status=start)
        res = act(admin_user, tutor.id, action, reason='rubric ok')
        assert res.status_code == 200, res.json()
        body = res.json()
        assert (body['teacher_id'], body['action'], body['previous_status'], body['status'], body['changed']) == \
            (str(tutor.id), action, start, TARGET[action], True)
        assert trail(tutor) == EXPECTED[action][start]
        rows = TeacherStatusChange.objects.filter(teacher=tutor)
        assert len(body['change_ids']) == rows.count()
        assert all(r.actor_user_id == admin_user.pk and r.reason == 'rubric ok' for r in rows)

    @pytest.mark.parametrize('action,start', [(a, s) for a in EXPECTED for s in ALL
                                              if s not in EXPECTED[a] and s != TARGET[a]])
    def test_every_other_start_is_409_and_changes_nothing(self, admin_user, action, start):
        tutor = f.make_teacher_profile(status=start)
        res = act(admin_user, tutor.id, action)
        assert res.status_code == 409 and res.json()['code'] == 'invalid_transition'
        tutor.refresh_from_db()
        assert tutor.status == start and not TeacherStatusChange.objects.exists()

    @pytest.mark.parametrize('action', ACTIONS)
    def test_repeating_an_action_is_an_idempotent_200(self, admin_user, action):
        tutor = f.make_teacher_profile(status=TARGET[action])
        res = act(admin_user, tutor.id, action)
        assert res.status_code == 200 and res.json()['changed'] is False and res.json()['change_ids'] == []
        assert not TeacherStatusChange.objects.exists()

    @pytest.mark.parametrize('action,start', [('reject', 'in_review'), ('request-changes', 'in_review'), ('suspend', 'approved')])
    @pytest.mark.parametrize('reason', [None, '', '   '])
    def test_decisions_that_reach_the_tutor_need_a_reason(self, admin_user, action, start, reason):
        tutor = f.make_teacher_profile(status=start)
        assert act(admin_user, tutor.id, action, reason=reason).status_code == 400
        tutor.refresh_from_db()
        assert tutor.status == start

    def test_reason_is_capped(self, admin_user):
        tutor = f.make_teacher_profile(status='in_review')
        assert act(admin_user, tutor.id, 'reject', reason='x' * 501).status_code == 400

    def test_suspend_returns_the_future_lessons_it_leaves_without_a_tutor(self, admin_user):
        from apps.bookings.models import Booking
        tutor = f.make_teacher_profile(status='approved')
        confirmed = f.make_booking(teacher=tutor, status=Booking.Status.CONFIRMED, offset_hours=48)
        pending = f.make_booking(teacher=tutor, status=Booking.Status.PENDING_PAYMENT, offset_hours=72)
        res = act(admin_user, tutor.id, 'suspend', reason='complaints')
        assert res.json()['affected_booking_ids'] == [str(confirmed.id), str(pending.id)]
        confirmed.refresh_from_db()
        assert confirmed.status == Booking.Status.CONFIRMED            # cancelling them is a separate staff action

    def test_unknown_tutor_is_404(self, admin_user):
        assert act(admin_user, uuid.uuid4(), 'approve').status_code == 404

    @pytest.mark.parametrize('action', ACTIONS)
    def test_non_staff_are_refused(self, action, student_user, teacher_user):
        tutor = f.make_teacher_profile(status='in_review')
        assert act(None, tutor.id, action).status_code == 401
        for user in (student_user, teacher_user.user, tutor.user):
            assert act(user, tutor.id, action).status_code == 403
        tutor.refresh_from_db()
        assert tutor.status == 'in_review'

    def test_role_admin_without_is_staff_is_staff(self):
        admin = f.make_user('admin', is_staff=False, is_superuser=False)
        tutor = f.make_teacher_profile(status='in_review')
        assert act(admin, tutor.id, 'approve').status_code == 200

    def test_actions_are_throttled(self, admin_user, monkeypatch):
        from django.conf import settings
        from django.core.cache import cache
        from rest_framework.throttling import ScopedRateThrottle
        cache.clear()
        assert settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['admin_teacher_review']
        monkeypatch.setattr(ScopedRateThrottle, 'THROTTLE_RATES',
                            {**ScopedRateThrottle.THROTTLE_RATES, 'admin_teacher_review': '2/hour'})
        from apps.admin_api import teacher_review_views
        assert teacher_review_views.TeacherReviewActionView.throttle_scope == 'admin_teacher_review'
        tutor = f.make_teacher_profile(status='approved')
        codes = [act(admin_user, tutor.id, 'revet').status_code for _ in range(3)]
        assert codes[-1] == 429


# ------------------------------------------------------------------ legacy PATCH /admin/teachers/<id>/verify/ (Slice 8 contract)
def verify(admin, tutor_id, body):
    return api(admin).patch(f'/api/v1/admin/teachers/{tutor_id}/verify/', body, format='json')


class TestLegacyVerify:
    @pytest.mark.parametrize('start,path', [
        ('in_review', ['approved']),
        ('submitted', ['in_review', 'approved']),
        ('applied', ['submitted', 'in_review', 'approved']),
        ('changes_requested', ['submitted', 'in_review', 'approved']),
    ])
    def test_approve_uses_only_review_edges(self, admin_user, start, path):
        tutor = f.make_teacher_profile(status=start)
        res = verify(admin_user, tutor.id, {'is_verified': True})
        assert res.status_code == 200
        assert res.json() == {'success': True, 'teacher_id': str(tutor.id), 'is_verified': True,
                              'message': 'Tutor audition approved and published live.'}
        assert trail(tutor) == path

    @pytest.mark.parametrize('start,path', [
        ('in_review', ['rejected']),
        ('submitted', ['in_review', 'rejected']),
        ('applied', ['submitted', 'in_review', 'rejected']),
        ('changes_requested', ['submitted', 'in_review', 'rejected']),
        ('suspended', ['rejected']),
    ])
    def test_reject_records_the_reason_and_never_passes_approved(self, admin_user, start, path):
        tutor = f.make_teacher_profile(status=start)
        res = verify(admin_user, tutor.id, {'is_verified': False, 'rejection_reason': 'Audio unclear'})
        assert res.status_code == 200 and res.json()['is_verified'] is False
        assert trail(tutor) == path and 'approved' not in trail(tutor)
        assert TeacherStatusChange.objects.filter(teacher=tutor).last().reason == 'Audio unclear'

    def test_reject_without_a_reason_records_a_default(self, admin_user):
        tutor = f.make_teacher_profile(status='in_review')
        assert verify(admin_user, tutor.id, {'is_verified': False}).status_code == 200
        assert TeacherStatusChange.objects.get(teacher=tutor).reason == 'legacy-verify'

    @pytest.mark.parametrize('start,is_verified', [('approved', False), ('suspended', True), ('rejected', True)])
    def test_lifecycle_moves_are_not_vetting_and_are_409(self, admin_user, start, is_verified):
        tutor = f.make_teacher_profile(status=start)
        res = verify(admin_user, tutor.id, {'is_verified': is_verified})
        assert res.status_code == 409 and res.json()['code'] == 'invalid_transition'
        tutor.refresh_from_db()
        assert tutor.status == start and not TeacherStatusChange.objects.exists()

    @pytest.mark.parametrize('start,is_verified', [('approved', True), ('rejected', False)])
    def test_the_same_status_is_a_no_op_200(self, admin_user, start, is_verified):
        tutor = f.make_teacher_profile(status=start)
        assert verify(admin_user, tutor.id, {'is_verified': is_verified}).status_code == 200
        assert not TeacherStatusChange.objects.exists()

    def test_a_failure_halfway_rolls_back_every_step(self, admin_user, monkeypatch):
        table = {src: dict(targets) for src, targets in vetting.ALLOWED_TRANSITIONS.items()}
        table['in_review'].pop('approved')
        monkeypatch.setattr(vetting, 'ALLOWED_TRANSITIONS', table)
        tutor = f.make_teacher_profile(status='applied')
        assert verify(admin_user, tutor.id, {'is_verified': True}).status_code == 409
        tutor.refresh_from_db()
        assert tutor.status == 'applied' and not TeacherStatusChange.objects.exists()

    def test_404_400_403(self, admin_user, student_user):
        assert verify(admin_user, uuid.uuid4(), {'is_verified': True}).status_code == 404
        assert verify(admin_user, uuid.uuid4(), {'is_verified': 'nope'}).status_code == 400
        tutor = f.make_teacher_profile(status='submitted')
        assert verify(student_user, tutor.id, {'is_verified': True}).status_code == 403

    def test_the_path_walking_shim_is_gone(self):
        from apps.admin_api import views
        assert not hasattr(views, '_legacy_verify_path')


# ------------------------------------------------------------------ admin pending queue
class TestPendingQueue:
    def test_lists_applied_submitted_and_in_review_only_oldest_first(self, admin_user):
        made = {s: f.make_teacher_profile(status=s, availability=False) for s in ALL}
        rows = api(admin_user).get('/api/v1/admin/teachers/pending-vetting/').json()
        assert [r['id'] for r in rows] == [str(made[s].id) for s in ('applied', 'submitted', 'in_review')]
        assert [r['status'] for r in rows] == ['applied', 'submitted', 'in_review']

    def test_the_telemetry_count_matches_the_queue(self, admin_user):
        for s in ALL:
            f.make_teacher_profile(status=s, availability=False)
        assert api(admin_user).get('/api/v1/admin/telemetry/').json()['pending_vetting_count'] == 3
