"""Slice T5a: the tutor application funnel (plan section 3.9). A tutor completes five steps (profile, uploads, power backup,
speed test, declaration) and submits; submitting is the ONLY way an applicant reaches the review queue (the staff lead-in
`applied -> submitted` of slice T1b is gone). Provisional until D-11: required uploads, 10 / 5 Mbps, 7-day-old speed test."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

import factories as f
from apps.notifications.models import Notification
from apps.teachers import review, vetting
from apps.teachers.models import TeacherApplication, TeacherAsset, TeacherStatusChange

pytestmark = pytest.mark.django_db
URL = '/api/v1/teachers/me/application/'
SUBMIT = URL + 'submit/'
KINDS = ('avatar', 'accent_audio', 'intro_video', 'tefl_certificate', 'identity_document')


def api(user):
    c = APIClient()
    if user is not None:
        c.force_authenticate(user=user)
    return c


def applicant(status='applied', **fields):
    fields = {'headline': 'Certified TEFL tutor', 'bio': 'I teach.', 'specialties': ['FreeTalk'], **fields}
    return f.make_teacher_profile(status=status, **fields)


def upload(tutor, kind, etag=None, *, replaced=False):
    return TeacherAsset.objects.create(teacher=tutor, kind=kind, object_key=f'k/{kind}/{etag or kind}', etag=etag or kind,
                                       content_type='application/pdf', size_bytes=1,
                                       replaced_at=timezone.now() if replaced else None)


def complete(tutor, *, skip=()):
    """Everything the funnel needs except the steps in `skip`."""
    client = api(tutor.user)
    if 'uploads' not in skip:
        for kind in KINDS:
            upload(tutor, kind)
    body = {}
    if 'speed_test' not in skip:
        body['speed_test'] = {'download_mbps': '42.5', 'upload_mbps': '12'}
    if 'power_backup' not in skip:
        body['confirm_power_backup'] = True
    if 'declaration' not in skip:
        body['accept_declaration'] = True
    if body:
        assert client.patch(URL, body, format='json').status_code == 200
    return client


# ------------------------------------------------------------------ progress
class TestProgress:
    def test_a_new_applicant_sees_every_step_incomplete_and_cannot_submit(self):
        tutor = applicant(headline='', bio='', specialties=[])
        body = api(tutor.user).get(URL).json()
        assert body['status'] == 'applied' and body['can_submit'] is False and body['editable'] is True
        assert [s['key'] for s in body['steps']] == ['profile', 'uploads', 'power_backup', 'speed_test', 'declaration']
        assert not any(s['complete'] for s in body['steps'])
        assert body['requirements'] == {'upload_kinds': list(KINDS), 'min_download_mbps': 10.0, 'min_upload_mbps': 5.0,
                                        'speed_test_max_age_hours': 168}

    def test_a_finished_applicant_can_submit(self):
        tutor = applicant()
        body = complete(tutor).get(URL).json()
        assert all(s['complete'] for s in body['steps']) and body['can_submit'] is True

    def test_replaced_uploads_do_not_count_and_a_missing_kind_is_named(self):
        tutor = applicant()
        for kind in KINDS[:-1]:
            upload(tutor, kind)
        upload(tutor, 'identity_document', replaced=True)
        step = {s['key']: s for s in api(tutor.user).get(URL).json()['steps']}['uploads']
        assert step['complete'] is False and step['missing'] == ['identity_document']

    def test_the_profile_step_needs_headline_bio_and_a_specialty(self):
        tutor = applicant(bio='')
        step = {s['key']: s for s in api(tutor.user).get(URL).json()['steps']}['profile']
        assert step['complete'] is False and step['missing'] == ['bio']

    def test_only_tutors_and_only_their_own(self):
        assert api(None).get(URL).status_code in (401, 403)
        assert api(f.make_student()).get(URL).status_code == 403
        one, two = applicant(), applicant()
        api(one.user).patch(URL, {'accept_declaration': True}, format='json')
        assert {s['key']: s for s in api(two.user).get(URL).json()['steps']}['declaration']['complete'] is False


# ------------------------------------------------------------------ editing
class TestEditing:
    @pytest.mark.parametrize('speed', [{'download_mbps': '9.9', 'upload_mbps': '12'}, {'download_mbps': '42', 'upload_mbps': '4.9'}])
    def test_a_slow_connection_is_recorded_but_does_not_complete_the_step(self, speed):
        tutor = applicant()
        res = api(tutor.user).patch(URL, {'speed_test': speed}, format='json')
        assert res.status_code == 200
        step = {s['key']: s for s in res.json()['steps']}['speed_test']
        assert step['complete'] is False and 'below' in step['detail'].lower()

    @pytest.mark.parametrize('bad', [{'download_mbps': '-1', 'upload_mbps': '5'}, {'download_mbps': 'x', 'upload_mbps': '5'},
                                     {'download_mbps': '10'}, {'download_mbps': '99999', 'upload_mbps': '5'}, 'fast'])
    def test_nonsense_speed_results_are_rejected(self, bad):
        assert api(applicant().user).patch(URL, {'speed_test': bad}, format='json').status_code == 400

    def test_a_stale_speed_test_does_not_count(self):
        tutor = applicant()
        complete(tutor)
        TeacherApplication.objects.filter(teacher=tutor).update(speed_test_at=timezone.now() - timedelta(hours=169))
        assert {s['key']: s for s in api(tutor.user).get(URL).json()['steps']}['speed_test']['complete'] is False

    def test_unknown_or_service_owned_fields_are_refused(self):
        client = api(applicant().user)
        for body in ({'submitted_at': '2026-01-01T00:00:00Z'}, {'status': 'approved'}, {'surprise': 1}):
            assert client.patch(URL, body, format='json').status_code == 400

    def test_confirmations_must_be_true_and_are_stamped_once(self):
        tutor = applicant()
        client = api(tutor.user)
        assert client.patch(URL, {'accept_declaration': False}, format='json').status_code == 400
        client.patch(URL, {'accept_declaration': True}, format='json')
        first = TeacherApplication.objects.get(teacher=tutor).declaration_accepted_at
        client.patch(URL, {'accept_declaration': True}, format='json')
        assert TeacherApplication.objects.get(teacher=tutor).declaration_accepted_at == first

    @pytest.mark.parametrize('status', ['submitted', 'in_review', 'approved', 'rejected', 'suspended'])
    def test_the_application_is_locked_once_it_has_been_sent(self, status):
        tutor = applicant(status)
        res = api(tutor.user).patch(URL, {'accept_declaration': True}, format='json')
        assert res.status_code == 409 and res.json()['code'] == 'application_locked'
        assert api(tutor.user).get(URL).json()['editable'] is False

    def test_it_is_editable_again_after_changes_are_requested(self):
        tutor = applicant('changes_requested')
        assert api(tutor.user).patch(URL, {'accept_declaration': True}, format='json').status_code == 200


# ------------------------------------------------------------------ submit
class TestSubmit:
    def test_an_incomplete_application_lists_what_is_missing_and_changes_nothing(self):
        tutor = applicant()
        res = complete(tutor, skip=('uploads', 'speed_test')).post(SUBMIT)
        assert res.status_code == 400 and res.json()['code'] == 'application_incomplete'
        assert set(res.json()['missing']) == {'uploads', 'speed_test'}
        tutor.refresh_from_db()
        assert tutor.status == 'applied'

    def test_a_complete_application_is_submitted_by_the_tutor_with_an_audit_row_and_a_staff_alert(
            self, admin_user, django_capture_on_commit_callbacks):
        tutor = applicant()
        client = complete(tutor)
        with django_capture_on_commit_callbacks(execute=True):
            res = client.post(SUBMIT)
        assert res.status_code == 200 and res.json()['status'] == 'submitted'
        tutor.refresh_from_db()
        assert tutor.status == 'submitted'
        row = TeacherStatusChange.objects.get(teacher=tutor, to_status='submitted')
        assert row.actor_user_id == tutor.user_id
        assert TeacherApplication.objects.get(teacher=tutor).submitted_at is not None
        assert Notification.objects.filter(user=admin_user, payload__alert='vetting_submitted').count() == 1

    def test_submitting_twice_is_a_no_op(self):
        tutor = applicant()
        client = complete(tutor)
        client.post(SUBMIT)
        res = client.post(SUBMIT)
        assert res.status_code == 200
        assert TeacherStatusChange.objects.filter(teacher=tutor, to_status='submitted').count() == 1

    def test_resubmitting_after_changes_were_requested(self, admin_user):
        tutor = applicant()
        client = complete(tutor)
        client.post(SUBMIT)
        review.apply_review_action(tutor.pk, 'start-review', actor=admin_user)
        review.apply_review_action(tutor.pk, 'request-changes', actor=admin_user, reason='fix',
                                   requested_changes=['intro_video'])
        res = client.post(SUBMIT)
        assert res.status_code == 200 and res.json()['status'] == 'submitted'
        assert TeacherStatusChange.objects.filter(teacher=tutor, to_status='submitted').count() == 2

    @pytest.mark.parametrize('status', ['in_review', 'approved', 'rejected', 'suspended'])
    def test_other_statuses_cannot_submit(self, status):
        tutor = applicant(status)
        res = api(tutor.user).post(SUBMIT)
        assert res.status_code == 409 and res.json()['code'] == 'cannot_submit'

    def test_a_replaced_upload_after_the_check_cannot_slip_through(self):
        tutor = applicant()
        client = complete(tutor)
        TeacherAsset.objects.filter(teacher=tutor, kind='intro_video').update(replaced_at=timezone.now())
        assert client.post(SUBMIT).status_code == 400

    def test_students_cannot_submit(self):
        assert api(f.make_student()).post(SUBMIT).status_code == 403


# ------------------------------------------------------------------ the staff lead-in is gone
class TestStaffCannotReceiveTheApplicationForTheTutor:
    def test_start_review_needs_a_submitted_application(self, admin_user):
        for status in ('applied', 'changes_requested'):
            tutor = applicant(status)
            with pytest.raises(vetting.InvalidTeacherTransition):
                review.apply_review_action(tutor.pk, 'start-review', actor=admin_user)
            tutor.refresh_from_db()
            assert tutor.status == status

    def test_the_pending_queue_lists_only_applications_that_were_sent(self, admin_user):
        sent, working = applicant('submitted'), applicant('applied')
        ids = [row['id'] for row in api(admin_user).get('/api/v1/admin/teachers/pending-vetting/').json()]
        assert str(sent.id) in ids and str(working.id) not in ids

    def test_the_review_packet_shows_the_application(self, admin_user):
        tutor = applicant()
        complete(tutor).post(SUBMIT)
        body = api(admin_user).get(f'/api/v1/admin/teachers/{tutor.id}/review-packet/').json()
        assert Decimal(str(body['application']['speed_test_download_mbps'])) == Decimal('42.5')
        assert body['application']['submitted_at'] and body['application']['power_backup_confirmed']
