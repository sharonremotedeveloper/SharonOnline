"""Slice T4a: vetting backend (plan sections 3.1 and 4): a rubric on approval, structured change requests, asset integrity
(what the reviewer looked at must be what is approved), the staff review packet, what the tutor may see, and the admin alert
when a tutor submits. Provisional (D-11): 4 criteria x 1-5, every score >= VETTING_MIN_RUBRIC_SCORE (3)."""
import pytest
from rest_framework.test import APIClient

import factories as f
from apps.notifications.models import Notification
from apps.teachers import vetting
from apps.teachers.models import TeacherAsset, TeacherStatusChange

pytestmark = pytest.mark.django_db
GOOD = {'pronunciation': 4, 'teaching_presence': 5, 'professionalism': 4, 'credentials': 3}


def api(user):
    c = APIClient()
    if user is not None:
        c.force_authenticate(user=user)
    return c


def post(user, tutor, action, **body):
    return api(user).post(f'/api/v1/admin/teachers/{tutor.id}/{action}/', body, format='json')


def in_review():
    return f.make_teacher_profile(status='in_review')


def asset(tutor, kind='intro_video', etag='etag-1', replaced=False):
    from django.utils import timezone
    return TeacherAsset.objects.create(
        teacher=tutor, kind=kind, object_key=f'private/x/{etag}', etag=etag, content_type='video/mp4', size_bytes=10,
        replaced_at=timezone.now() if replaced else None)


# ------------------------------------------------------------------ rubric
class TestRubricOnApproval:
    def test_approve_without_a_rubric_is_refused(self, admin_user):
        tutor = in_review()
        res = post(admin_user, tutor, 'approve')
        assert res.status_code == 400 and res.json()['code'] == 'rubric_required'
        tutor.refresh_from_db()
        assert tutor.status == 'in_review'

    @pytest.mark.parametrize('rubric', [
        {'pronunciation': 4, 'teaching_presence': 5, 'professionalism': 4},                       # missing criterion
        {**GOOD, 'charisma': 5},                                                                    # unknown criterion
        {**GOOD, 'credentials': 0}, {**GOOD, 'credentials': 6}, {**GOOD, 'credentials': 3.5},       # out of range / not int
        {**GOOD, 'credentials': '4'}, {**GOOD, 'credentials': True}, 'good', [],
    ])
    def test_a_malformed_rubric_is_refused(self, admin_user, rubric):
        tutor = in_review()
        res = post(admin_user, tutor, 'approve', rubric=rubric)
        assert res.status_code == 400
        tutor.refresh_from_db()
        assert tutor.status == 'in_review'

    def test_any_score_below_the_minimum_blocks_approval(self, admin_user):
        tutor = in_review()
        res = post(admin_user, tutor, 'approve', rubric={**GOOD, 'pronunciation': 2})
        assert res.status_code == 400 and res.json()['code'] == 'rubric_below_threshold'
        tutor.refresh_from_db()
        assert tutor.status == 'in_review'

    def test_the_minimum_is_a_setting(self, admin_user, settings):
        settings.VETTING_MIN_RUBRIC_SCORE = 4
        tutor = in_review()
        assert post(admin_user, tutor, 'approve', rubric=GOOD).status_code == 400     # credentials 3 < 4
        settings.VETTING_MIN_RUBRIC_SCORE = 3
        assert post(admin_user, tutor, 'approve', rubric=GOOD).status_code == 200

    def test_a_valid_rubric_approves_and_is_stored_on_the_audit_row(self, admin_user):
        tutor = in_review()
        res = post(admin_user, tutor, 'approve', rubric=GOOD, reason='great accent')
        assert res.status_code == 200 and res.json()['status'] == 'approved'
        row = TeacherStatusChange.objects.get(teacher=tutor, to_status='approved')
        assert row.rubric['scores'] == GOOD and row.reason == 'great accent'

    def test_the_legacy_verify_endpoint_cannot_bypass_the_rubric(self, admin_user):
        tutor = in_review()
        res = api(admin_user).patch(f'/api/v1/admin/teachers/{tutor.id}/verify/', {'is_verified': True}, format='json')
        assert res.status_code == 400
        tutor.refresh_from_db()
        assert tutor.status == 'in_review'
        res = api(admin_user).patch(f'/api/v1/admin/teachers/{tutor.id}/verify/', {'is_verified': True, 'rubric': GOOD},
                                    format='json')
        assert res.status_code == 200

    def test_rejecting_needs_no_rubric_but_a_reason(self, admin_user):
        tutor = in_review()
        assert post(admin_user, tutor, 'reject').status_code == 400
        assert post(admin_user, tutor, 'reject', reason='not a fit').status_code == 200


# ------------------------------------------------------------------ structured change requests
class TestRequestChanges:
    def test_requested_changes_are_stored_and_must_be_known_asset_kinds(self, admin_user):
        tutor = in_review()
        bad = post(admin_user, tutor, 'request-changes', reason='fix', requested_changes=['intro_video', 'haircut'])
        assert bad.status_code == 400
        ok = post(admin_user, tutor, 'request-changes', reason='Re-record the intro, the audio is noisy.',
                  requested_changes=['intro_video', 'accent_audio'])
        assert ok.status_code == 200
        row = TeacherStatusChange.objects.get(teacher=tutor, to_status='changes_requested')
        assert row.rubric['requested_changes'] == ['intro_video', 'accent_audio']

    def test_a_reason_is_still_required(self, admin_user):
        assert post(admin_user, in_review(), 'request-changes', requested_changes=['intro_video']).status_code == 400


# ------------------------------------------------------------------ asset integrity
class TestReviewedAssetsMustMatch:
    def test_approval_records_the_asset_hashes_the_reviewer_saw(self, admin_user):
        tutor = in_review()
        asset(tutor, 'intro_video', 'v-1')
        asset(tutor, 'accent_audio', 'a-1')
        res = post(admin_user, tutor, 'approve', rubric=GOOD, reviewed_assets={'intro_video': 'v-1', 'accent_audio': 'a-1'})
        assert res.status_code == 200
        row = TeacherStatusChange.objects.get(teacher=tutor, to_status='approved')
        assert row.reviewed_assets == {'intro_video': 'v-1', 'accent_audio': 'a-1'}

    def test_content_swapped_after_the_review_blocks_approval(self, admin_user):
        tutor = in_review()
        asset(tutor, 'intro_video', 'v-1', replaced=True)
        asset(tutor, 'intro_video', 'v-2')                      # the tutor replaced the video after the reviewer opened it
        res = post(admin_user, tutor, 'approve', rubric=GOOD, reviewed_assets={'intro_video': 'v-1'})
        assert res.status_code == 409 and res.json()['code'] == 'assets_changed'
        tutor.refresh_from_db()
        assert tutor.status == 'in_review'

    def test_a_reviewer_who_did_not_report_what_they_saw_cannot_approve_a_tutor_with_assets(self, admin_user):
        tutor = in_review()
        asset(tutor, 'intro_video', 'v-1')
        res = post(admin_user, tutor, 'approve', rubric=GOOD)
        assert res.status_code == 409 and res.json()['code'] == 'assets_review_required'

    def test_an_asset_the_reviewer_never_saw_blocks_approval(self, admin_user):
        tutor = in_review()
        asset(tutor, 'intro_video', 'v-1')
        asset(tutor, 'accent_audio', 'a-1')
        res = post(admin_user, tutor, 'approve', rubric=GOOD, reviewed_assets={'intro_video': 'v-1'})
        assert res.status_code == 409 and res.json()['code'] == 'assets_changed'

    def test_replaced_assets_are_ignored_and_a_tutor_without_assets_needs_none(self, admin_user):
        tutor = in_review()
        asset(tutor, 'intro_video', 'old', replaced=True)
        assert post(admin_user, tutor, 'approve', rubric=GOOD).status_code == 200

    def test_required_asset_kinds_are_a_setting(self, admin_user, settings):
        settings.VETTING_REQUIRED_ASSET_KINDS = ('intro_video', 'tefl_certificate')
        tutor = in_review()
        asset(tutor, 'intro_video', 'v-1')
        res = post(admin_user, tutor, 'approve', rubric=GOOD, reviewed_assets={'intro_video': 'v-1'})
        assert res.status_code == 400 and res.json()['code'] == 'required_assets_missing'


# ------------------------------------------------------------------ review packet (staff only)
class TestReviewPacket:
    def url(self, tutor):
        return f'/api/v1/admin/teachers/{tutor.id}/review-packet/'

    def test_staff_get_profile_history_and_asset_fingerprints_but_no_storage_keys(self, admin_user):
        tutor = in_review()
        asset(tutor, 'intro_video', 'v-1')
        asset(tutor, 'tefl_certificate', 't-1')
        post(admin_user, tutor, 'request-changes', reason='fix audio', requested_changes=['accent_audio'])
        res = api(admin_user).get(self.url(tutor))
        assert res.status_code == 200
        body = res.json()
        assert body['teacher_id'] == str(tutor.id) and body['status'] == 'changes_requested'
        assert {a['kind']: a['etag'] for a in body['assets']} == {'intro_video': 'v-1', 'tefl_certificate': 't-1'}
        assert 'object_key' not in str(body) and 'private/' not in str(body)          # audited download only
        assert body['history'][0]['to_status'] == 'changes_requested' and body['history'][0]['reason'] == 'fix audio'
        assert body['criteria'] == ['pronunciation', 'teaching_presence', 'professionalism', 'credentials']
        assert body['min_score'] == 3 and body['sla_strikes'] == 0

    @pytest.mark.parametrize('who', ['student', 'tutor', 'anon'])
    def test_only_staff(self, who):
        tutor = in_review()
        user = {'student': f.make_student(), 'tutor': tutor.user, 'anon': None}[who]
        assert api(user).get(self.url(tutor)).status_code in (401, 403)

    def test_unknown_tutor_is_404(self, admin_user):
        import uuid
        assert api(admin_user).get(f'/api/v1/admin/teachers/{uuid.uuid4()}/review-packet/').status_code == 404


# ------------------------------------------------------------------ what the tutor may see
class TestTutorFeedback:
    def test_the_tutor_sees_the_reason_and_requested_changes_but_never_the_scores(self, admin_user):
        tutor = in_review()
        post(admin_user, tutor, 'request-changes', reason='Re-record the intro.', requested_changes=['intro_video'])
        res = api(tutor.user).get('/api/v1/teachers/me/')
        fb = res.json()['review_feedback']
        assert fb['status'] == 'changes_requested' and fb['reason'] == 'Re-record the intro.'
        assert fb['requested_changes'] == ['intro_video'] and fb['decided_at']
        assert 'rubric' not in str(res.json()) and 'score' not in str(res.json())

    def test_scores_stay_hidden_after_an_approval_and_feedback_clears(self, admin_user):
        tutor = in_review()
        post(admin_user, tutor, 'approve', rubric=GOOD, reason='welcome')
        body = api(tutor.user).get('/api/v1/teachers/me/').json()
        assert body['review_feedback'] is None
        assert '"pronunciation"' not in str(body)

    def test_a_rejection_reason_is_shown(self, admin_user):
        tutor = in_review()
        post(admin_user, tutor, 'reject', reason='Insufficient English fluency.')
        assert api(tutor.user).get('/api/v1/teachers/me/').json()['review_feedback']['reason'] == \
            'Insufficient English fluency.'

    def test_a_new_tutor_has_no_feedback(self):
        assert api(f.make_teacher_profile(status='applied').user).get('/api/v1/teachers/me/').json()['review_feedback'] is None


# ------------------------------------------------------------------ admin alert when a tutor submits
class TestSubmittedAlert:
    def alerts(self):
        return Notification.objects.filter(kind='admin_alert', payload__alert='vetting_submitted')

    def test_a_tutor_submitting_alerts_staff_once(self, admin_user, django_capture_on_commit_callbacks):
        tutor = f.make_teacher_profile(status='applied')
        with django_capture_on_commit_callbacks(execute=True):
            vetting.transition_teacher(tutor, 'submitted', actor=tutor.user)
        rows = self.alerts()
        assert rows.filter(user=admin_user).count() == 1
        assert rows.first().payload['teacher_id'] == str(tutor.id)

    def test_a_staff_lead_in_does_not_alert(self, admin_user, django_capture_on_commit_callbacks):
        tutor = f.make_teacher_profile(status='applied')
        with django_capture_on_commit_callbacks(execute=True):
            vetting.transition_teacher(tutor, 'submitted', actor=admin_user)
        assert not self.alerts().exists()

    def test_a_resubmission_after_changes_alerts_again(self, admin_user, django_capture_on_commit_callbacks):
        tutor = f.make_teacher_profile(status='changes_requested')
        with django_capture_on_commit_callbacks(execute=True):
            vetting.transition_teacher(tutor, 'submitted', actor=tutor.user)
        assert self.alerts().count() == 1


# ------------------------------------------------------------------ review-round details (added from the mutation run)
class TestReviewRounds:
    def test_legacy_approval_from_submitted_records_the_evidence_on_the_approval_step_only(self, admin_user):
        tutor = f.make_teacher_profile(status='submitted')
        res = api(admin_user).patch(f'/api/v1/admin/teachers/{tutor.id}/verify/', {'is_verified': True, 'rubric': GOOD},
                                    format='json')
        assert res.status_code == 200
        rows = {r.to_status: r for r in TeacherStatusChange.objects.filter(teacher=tutor)}
        assert rows['approved'].rubric['scores'] == GOOD
        assert not rows['in_review'].rubric

    def test_repeating_an_approval_is_a_no_op_even_without_a_rubric(self, admin_user):
        tutor = f.make_teacher_profile(status='approved')
        res = post(admin_user, tutor, 'approve')
        assert res.status_code == 200 and res.json()['changed'] is False

    def test_the_tutor_sees_the_latest_feedback_of_a_second_round(self, admin_user):
        tutor = in_review()
        post(admin_user, tutor, 'request-changes', reason='First: audio.', requested_changes=['accent_audio'])
        vetting.transition_teacher(tutor, 'submitted', actor=tutor.user)
        post(admin_user, tutor, 'start-review')
        post(admin_user, tutor, 'request-changes', reason='Second: video.', requested_changes=['intro_video'])
        fb = api(tutor.user).get('/api/v1/teachers/me/').json()['review_feedback']
        assert fb['reason'] == 'Second: video.' and fb['requested_changes'] == ['intro_video']

    def test_the_packet_lists_only_live_uploads(self, admin_user):
        tutor = in_review()
        asset(tutor, 'intro_video', 'old', replaced=True)
        asset(tutor, 'intro_video', 'new')
        body = api(admin_user).get(f'/api/v1/admin/teachers/{tutor.id}/review-packet/').json()
        assert [a['etag'] for a in body['assets']] == ['new']


class TestMutationSurvivors:
    def test_a_boolean_or_float_score_is_invalid_even_when_the_minimum_is_one(self, admin_user, settings):
        settings.VETTING_MIN_RUBRIC_SCORE = 1
        for bad in (True, 2.0):
            res = post(admin_user, in_review(), 'approve', rubric={**GOOD, 'credentials': bad})
            assert res.status_code == 400 and res.json()['code'] == 'rubric_invalid'

    def test_approval_succeeds_when_every_required_upload_is_present(self, admin_user, settings):
        settings.VETTING_REQUIRED_ASSET_KINDS = ('intro_video', 'tefl_certificate')
        tutor = in_review()
        asset(tutor, 'intro_video', 'v-1')
        asset(tutor, 'tefl_certificate', 't-1')
        res = post(admin_user, tutor, 'approve', rubric=GOOD, reviewed_assets={'intro_video': 'v-1', 'tefl_certificate': 't-1'})
        assert res.status_code == 200
