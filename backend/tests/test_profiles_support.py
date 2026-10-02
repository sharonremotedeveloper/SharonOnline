import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.integrations.email import EmailDeliveryError
from apps.users.models import StudentProfile, SupportInquiry
from apps.users.tasks import send_support_inquiry_notification


PROFILE = '/api/v1/student/profile/'
INQUIRIES = '/api/v1/auth/inquiries/'


def authenticated(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(user).access_token}')
    return client


@pytest.mark.django_db
class TestStudentProfile:
    def test_get_has_empty_unset_learning_fields_not_fabricated_defaults(self, student_user):
        body = authenticated(student_user).get(PROFILE).json()
        assert body == {
            'id': str(student_user.id),
            'full_name': student_user.username,
            'email': student_user.email,
            'country': 'JP',
            'timezone': 'Asia/Tokyo',
            'target_level': '',
            'learning_goals': '',
        }

    def test_patch_persists_user_and_one_to_one_profile_fields(self, student_user):
        response = authenticated(student_user).patch(PROFILE, {
            'full_name': '  Kenji   Sato  ',
            'country': 'za',
            'timezone': 'Africa/Johannesburg',
            'target_level': 'B2',
            'learning_goals': 'Lead technical meetings clearly.',
        }, format='json')
        assert response.status_code == 200
        student_user.refresh_from_db()
        profile = StudentProfile.objects.get(user=student_user)
        assert (student_user.first_name, student_user.last_name) == ('Kenji', 'Sato')
        assert (student_user.country, student_user.timezone) == ('ZA', 'Africa/Johannesburg')
        assert (profile.target_level, profile.learning_goals) == ('B2', 'Lead technical meetings clearly.')
        assert authenticated(student_user).get(PROFILE).json() == response.json()['profile']

    @pytest.mark.parametrize('payload,field', [
        ({'timezone': 'Mars/Olympus'}, 'timezone'),
        ({'country': 'XX'}, 'country'),
        ({'learning_goals': 'x' * 2001}, 'learning_goals'),
        ({'target_level': 'x' * 65}, 'target_level'),
    ])
    def test_patch_validates_profile_contract(self, student_user, payload, field):
        response = authenticated(student_user).patch(PROFILE, payload, format='json')
        assert response.status_code == 400
        assert field in response.json()

    def test_non_student_cannot_use_student_profile(self, teacher_user):
        assert authenticated(teacher_user.user).get(PROFILE).status_code == 403


@pytest.mark.django_db
class TestSupportInquiry:
    def test_public_endpoint_persists_before_queueing(self, monkeypatch, django_capture_on_commit_callbacks):
        queued = []
        monkeypatch.setattr('apps.users.tasks.send_support_inquiry_notification.delay', queued.append)
        with django_capture_on_commit_callbacks(execute=True):
            response = APIClient().post(INQUIRIES, {
                'name': ' Aiko  Tanaka ',
                'email': 'aiko@example.com',
                'user_type': 'student',
                'subject': ' Checkout help ',
                'message': 'Please help with my payment.',
            }, format='json')
        assert response.status_code == 202
        inquiry = SupportInquiry.objects.get()
        assert queued == [str(inquiry.id)]
        assert inquiry.sender_name == 'Aiko Tanaka'
        assert inquiry.subject == 'Checkout help'
        assert inquiry.delivery_state == SupportInquiry.DeliveryState.PENDING

    def test_sender_type_defaults_to_other(self, monkeypatch, django_capture_on_commit_callbacks):
        monkeypatch.setattr('apps.users.tasks.send_support_inquiry_notification.delay', lambda _pk: None)
        with django_capture_on_commit_callbacks(execute=True):
            response = APIClient().post(INQUIRIES, {
                'name': 'Visitor', 'email': 'visitor@example.com', 'subject': 'Question', 'message': 'Hello',
            }, format='json')
        assert response.status_code == 202
        assert SupportInquiry.objects.get().sender_type == SupportInquiry.SenderType.OTHER

    @pytest.mark.parametrize('payload,field', [
        ({'name': '', 'email': 'a@b.com', 'user_type': 'other', 'subject': 's', 'message': 'm'}, 'name'),
        ({'name': 'A', 'email': 'bad', 'user_type': 'other', 'subject': 's', 'message': 'm'}, 'email'),
        ({'name': 'A', 'email': 'a@b.com', 'user_type': 'invalid', 'subject': 's', 'message': 'm'}, 'user_type'),
        ({'name': 'A', 'email': 'a@b.com', 'user_type': 'other', 'subject': ' ', 'message': 'm'}, 'subject'),
    ])
    def test_public_endpoint_validates_input(self, payload, field):
        response = APIClient().post(INQUIRIES, payload, format='json')
        assert response.status_code == 400
        assert field in response.json()

    def test_delivery_marks_sent(self, monkeypatch, settings):
        inquiry = SupportInquiry.objects.create(
            sender_name='Aiko', sender_email='aiko@example.com', sender_type='student',
            subject='Help', message='A message',
        )
        sent = []
        settings.SUPPORT_TO_EMAIL = 'support@example.com'
        monkeypatch.setattr('apps.users.tasks.send_email', lambda *args: sent.append(args))
        send_support_inquiry_notification.run(str(inquiry.id))
        inquiry.refresh_from_db()
        assert sent[0][0] == 'support@example.com'
        assert inquiry.delivery_state == SupportInquiry.DeliveryState.SENT
        assert inquiry.delivery_attempts == 1 and inquiry.delivered_at is not None

    def test_delivery_failure_stays_retryable(self, monkeypatch):
        inquiry = SupportInquiry.objects.create(
            sender_name='Aiko', sender_email='aiko@example.com', sender_type='student',
            subject='Help', message='A message',
        )
        monkeypatch.setattr('apps.users.tasks.send_email', lambda *args: (_ for _ in ()).throw(EmailDeliveryError('provider down')))
        monkeypatch.setattr(send_support_inquiry_notification, 'retry', lambda **kwargs: (_ for _ in ()).throw(kwargs['exc']))
        with pytest.raises(EmailDeliveryError):
            send_support_inquiry_notification.run(str(inquiry.id))
        inquiry.refresh_from_db()
        assert inquiry.delivery_state == SupportInquiry.DeliveryState.RETRYABLE
        assert inquiry.delivery_attempts == 1
        assert inquiry.last_delivery_error == 'provider down'
