from unittest.mock import MagicMock, patch

import pytest
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from apps.common.upload_policy import clamp_expires

URL = '/api/v1/integrations/storage/presigned-url/'


@pytest.fixture
def client(student_user):
    c = APIClient()
    c.force_authenticate(student_user)
    return c


def _body(student, **kw):
    body = {'action': 'upload', 'key': f'students/avatars/{student.id}/me.png',
            'content_type': 'image/png', 'size': 1000}
    body.update(kw)
    return body


@pytest.mark.django_db
class TestUploadPolicy:
    def test_valid_upload(self, client, student_user):
        assert client.post(URL, _body(student_user), format='json').status_code == 200

    def test_bad_content_type_rejected(self, client, student_user):
        assert client.post(URL, _body(student_user, content_type='text/html'), format='json').status_code == 400

    def test_missing_content_type_rejected(self, client, student_user):
        body = _body(student_user)
        del body['content_type']
        assert client.post(URL, body, format='json').status_code == 400

    def test_oversize_rejected(self, client, student_user):
        assert client.post(URL, _body(student_user, size=6 * 1024 * 1024), format='json').status_code == 400

    def test_missing_size_rejected(self, client, student_user):
        body = _body(student_user)
        del body['size']
        assert client.post(URL, body, format='json').status_code == 400

    def test_prefix_requires_trailing_slash(self, client, student_user):
        res = client.post(URL, _body(student_user, key=f'students/avatars/{student_user.id}evil.png'), format='json')
        assert res.status_code == 403

    def test_encoded_and_double_slash_keys_rejected(self, client, student_user):
        for bad in (f'students/avatars/{student_user.id}//x.png', f'students/avatars/{student_user.id}/%2e%2e/x.png'):
            assert client.post(URL, _body(student_user, key=bad), format='json').status_code == 400

    def test_expiry_is_clamped(self):
        assert clamp_expires(10**9) == 900
        assert clamp_expires(1) == 60
        assert clamp_expires('abc') == 900

    def test_content_length_is_signed_into_url(self, student_user):
        from apps.common.r2_client import generate_presigned_upload_url
        mock = MagicMock()
        mock.generate_presigned_url.return_value = 'https://r2/x'
        with patch('apps.common.r2_client.get_r2_client', return_value=mock):
            generate_presigned_upload_url('a/b.png', content_type='image/png', content_length=1234)
        params = mock.generate_presigned_url.call_args.kwargs['Params']
        assert params['ContentLength'] == 1234 and params['ContentType'] == 'image/png'


@pytest.mark.django_db
class TestThrottling:
    def test_login_throttled(self, monkeypatch):
        monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, 'login', '2/min')
        c = APIClient()
        codes = [c.post('/api/v1/auth/token/', {'username': 'a', 'password': 'b'}, format='json').status_code
                 for _ in range(3)]
        assert codes == [401, 401, 429]

    def test_register_throttled(self, monkeypatch):
        monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, 'register', '1/hour')
        c = APIClient()
        assert c.post('/api/v1/auth/register/', {}, format='json').status_code == 400
        res = c.post('/api/v1/auth/register/', {}, format='json')
        assert res.status_code == 429 and 'Retry-After' in res

    def test_upload_throttled(self, client, student_user, monkeypatch):
        monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, 'upload', '1/hour')
        assert client.post(URL, _body(student_user), format='json').status_code == 200
        assert client.post(URL, _body(student_user), format='json').status_code == 429

    def test_webhook_throttled(self, monkeypatch):
        monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, 'webhook', '1/min')
        c = APIClient()
        c.post('/api/v1/payments/webhooks/paypal/', {}, format='json')
        assert c.post('/api/v1/payments/webhooks/paypal/', {}, format='json').status_code == 429
