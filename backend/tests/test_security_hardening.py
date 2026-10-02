import pytest
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from apps.users.models import User

REGISTER = '/api/v1/auth/register/'
TOKEN = '/api/v1/auth/token/'


def _payload(**overrides):
    data = {'username': 'newuser', 'email': 'new@example.com',
            'password': 'Str0ng-pass-123', 'password_confirm': 'Str0ng-pass-123'}
    data.update(overrides)
    return data


@pytest.mark.django_db
class TestThrottleCannotBeBypassed:
    def test_rotating_x_forwarded_for_does_not_reset_login_limit(self, monkeypatch):
        monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, 'login', '2/min')
        c = APIClient()
        codes = [c.post(TOKEN, {'username': f'u{i}', 'password': 'x'}, format='json',
                        HTTP_X_FORWARDED_FOR=f'198.51.100.{i}').status_code for i in range(3)]
        assert codes == [401, 401, 429]

    def test_per_username_limit_holds_across_source_ips(self, monkeypatch):
        monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, 'login', '100/min')
        monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, 'login_user', '2/hour')
        c = APIClient()
        codes = [c.post(TOKEN, {'username': 'Victim', 'password': 'guess'}, format='json',
                        REMOTE_ADDR=f'203.0.113.{i}').status_code for i in range(3)]
        assert codes == [401, 401, 429]
        # a different account is unaffected, and case does not create a fresh bucket
        assert c.post(TOKEN, {'username': 'other', 'password': 'x'}, format='json').status_code == 401
        assert c.post(TOKEN, {'username': 'VICTIM', 'password': 'x'}, format='json').status_code == 429

    def test_non_object_login_body_does_not_crash_throttle(self):
        assert APIClient().post(TOKEN, ['x'], format='json').status_code in (400, 401, 415)


@pytest.mark.django_db
class TestRegistrationHardening:
    def test_invalid_timezone_rejected(self):
        res = APIClient().post(REGISTER, _payload(timezone='Mars/Olympus'), format='json')
        assert res.status_code == 400 and 'timezone' in res.data

    def test_valid_timezone_accepted(self):
        assert APIClient().post(REGISTER, _payload(timezone='Asia/Tokyo'), format='json').status_code == 201

    def test_username_unique_case_insensitively(self, student_user):
        res = APIClient().post(REGISTER, _payload(username=student_user.username.upper(), email='a@b.co'), format='json')
        assert res.status_code == 400 and 'username' in res.data

    def test_password_similar_to_username_rejected(self):
        res = APIClient().post(REGISTER, _payload(username='johnsmith', password='johnsmith1', password_confirm='johnsmith1'),
                               format='json')
        assert res.status_code == 400 and 'password' in res.data
        assert not User.objects.filter(username='johnsmith').exists()

    def test_patch_me_invalid_timezone_rejected(self, student_user):
        c = APIClient()
        c.force_authenticate(student_user)
        assert c.patch('/api/v1/auth/me/', {'timezone': '../../etc/passwd'}, format='json').status_code == 400
        assert c.patch('/api/v1/auth/me/', {'timezone': 'Africa/Johannesburg'}, format='json').status_code == 200

    def test_patch_me_cannot_take_another_users_username_in_other_case(self, student_user, teacher_user):
        c = APIClient()
        c.force_authenticate(student_user)
        res = c.patch('/api/v1/auth/me/', {'username': teacher_user.user.username.upper()}, format='json')
        assert res.status_code == 400


@pytest.mark.django_db
class TestTokenLifecycle:
    def test_deactivated_user_with_valid_access_token_is_locked_out(self, student_user):
        from rest_framework_simplejwt.tokens import RefreshToken
        access = str(RefreshToken.for_user(student_user).access_token)
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        assert c.get('/api/v1/auth/me/').status_code == 200
        student_user.is_active = False
        student_user.save()
        assert c.get('/api/v1/auth/me/').status_code == 401
