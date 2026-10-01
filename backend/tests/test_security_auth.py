import pytest
from django.urls import get_resolver
from rest_framework.permissions import AllowAny
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import User

REGISTER = '/api/v1/auth/register/'
ME = '/api/v1/auth/me/'


def _payload(**overrides):
    data = {
        'username': 'newuser', 'email': 'new@example.com',
        'password': 'Str0ng-pass-123', 'password_confirm': 'Str0ng-pass-123',
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
class TestRegistration:
    def test_role_admin_rejected(self):
        res = APIClient().post(REGISTER, _payload(role='admin'), format='json')
        assert res.status_code == 400
        assert not User.objects.filter(username='newuser').exists()

    def test_default_role_is_student(self):
        res = APIClient().post(REGISTER, _payload(), format='json')
        assert res.status_code == 201
        assert User.objects.get(username='newuser').role == 'student'

    def test_teacher_role_allowed(self):
        res = APIClient().post(REGISTER, _payload(role='teacher'), format='json')
        assert res.status_code == 201
        user = User.objects.get(username='newuser')
        assert user.role == 'teacher' and not user.is_staff

    def test_email_required(self):
        data = _payload()
        del data['email']
        assert APIClient().post(REGISTER, data, format='json').status_code == 400

    def test_duplicate_email_case_insensitive(self, student_user):
        res = APIClient().post(REGISTER, _payload(email='STUDENT@test.com'), format='json')
        assert res.status_code == 400
        assert 'email' in res.data

    def test_patch_me_cannot_escalate_role(self, student_user):
        client = APIClient()
        client.force_authenticate(student_user)
        res = client.patch(ME, {'role': 'admin'}, format='json')
        assert res.status_code == 200
        student_user.refresh_from_db()
        assert student_user.role == 'student'

    def test_patch_me_duplicate_email_rejected(self, student_user, teacher_user):
        client = APIClient()
        client.force_authenticate(student_user)
        res = client.patch(ME, {'email': 'TUTOR@test.com'}, format='json')
        assert res.status_code == 400


@pytest.mark.django_db
class TestLogout:
    def test_logout_blacklists_refresh_token(self, student_user):
        refresh = RefreshToken.for_user(student_user)
        client = APIClient()
        client.force_authenticate(student_user)
        assert client.post('/api/v1/auth/logout/', {'refresh': str(refresh)}, format='json').status_code == 205
        res = APIClient().post('/api/v1/auth/token/refresh/', {'refresh': str(refresh)}, format='json')
        assert res.status_code == 401

    def test_logout_requires_auth(self):
        assert APIClient().post('/api/v1/auth/logout/', {'refresh': 'x'}, format='json').status_code == 401

    def test_logout_invalid_token(self, student_user):
        client = APIClient()
        client.force_authenticate(student_user)
        assert client.post('/api/v1/auth/logout/', {'refresh': 'garbage'}, format='json').status_code == 400


# Every API view must declare its permissions explicitly (no silent reliance on defaults).
PUBLIC_ALLOWED_VIEWS = {'TokenRefreshView'}  # SimpleJWT sets AllowAny itself


def _iter_api_views(patterns=None, prefix=''):
    patterns = patterns if patterns is not None else get_resolver().url_patterns
    for p in patterns:
        if hasattr(p, 'url_patterns'):
            yield from _iter_api_views(p.url_patterns, prefix + str(p.pattern))
        else:
            cls = getattr(p.callback, 'cls', None)
            if cls is not None and prefix.startswith('api/'):
                yield prefix + str(p.pattern), cls


def test_every_api_view_declares_permission_classes():
    missing = [
        path for path, cls in _iter_api_views()
        if 'permission_classes' not in {k for c in cls.__mro__ if c.__module__.startswith('apps.') for k in vars(c)}
        and cls.__name__ not in PUBLIC_ALLOWED_VIEWS
    ]
    assert not missing, f"Views relying on default permissions: {missing}"


@pytest.mark.django_db
@pytest.mark.parametrize('url', [
    ME, '/api/v1/bookings/', '/api/v1/payments/credits/', '/api/v1/admin/telemetry/',
])
def test_protected_endpoints_reject_anonymous(url):
    assert APIClient().get(url).status_code == 401


@pytest.mark.django_db
def test_public_endpoints_open_to_anonymous(teacher_user):
    c = APIClient()
    assert c.get('/api/health/').status_code == 200
    assert c.get('/api/v1/teachers/').status_code == 200
    assert c.get(f'/api/v1/teachers/{teacher_user.id}/').status_code == 200
    assert c.post('/api/v1/auth/token/', {'username': 'x', 'password': 'y'}, format='json').status_code == 401


@pytest.mark.django_db
def test_staff_does_not_implicitly_pass_student_or_teacher_checks():
    from apps.users.permissions import IsStudent, IsTeacher
    from django.test import RequestFactory
    staff = User.objects.create_user(username='ops', email='ops@x.com', password='p', role='admin', is_staff=True)
    req = RequestFactory().get('/')
    req.user = staff
    assert not IsStudent().has_permission(req, None)
    assert not IsTeacher().has_permission(req, None)
