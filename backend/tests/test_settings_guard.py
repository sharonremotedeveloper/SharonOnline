import pytest
from django.core.exceptions import ImproperlyConfigured

from config.settings.guard import validate_production_settings

GOOD = {
    'DJANGO_SECRET_KEY': 'x' * 60,
    'DJANGO_ALLOWED_HOSTS': 'api.sharonesl.com',
    'CORS_ALLOWED_ORIGINS': 'https://sharonesl.com',
    'CSRF_TRUSTED_ORIGINS': 'https://sharonesl.com,https://api.sharonesl.com',
    'ZOOM_WEBHOOK_SECRET_TOKEN': 'zoom-secret',
}


def test_valid_env_passes():
    validate_production_settings(dict(GOOD))


@pytest.mark.parametrize('key,value', [
    ('DJANGO_SECRET_KEY', ''),
    ('DJANGO_SECRET_KEY', 'django-insecure-' + 'x' * 60),
    ('DJANGO_SECRET_KEY', 'short'),
    ('DJANGO_ALLOWED_HOSTS', ''),
    ('DJANGO_ALLOWED_HOSTS', 'api.sharonesl.com,localhost'),
    ('DJANGO_ALLOWED_HOSTS', '*'),
    ('CORS_ALLOWED_ORIGINS', ''),
    ('CORS_ALLOWED_ORIGINS', 'https://sharonesl.com,http://localhost:3000'),
    ('CORS_ALLOWED_ORIGINS', 'http://sharonesl.com'),
    ('CSRF_TRUSTED_ORIGINS', ''),
    ('CSRF_TRUSTED_ORIGINS', 'https://127.0.0.1:3000'),
    ('ZOOM_WEBHOOK_SECRET_TOKEN', ''),
])
def test_unsafe_env_rejected(key, value):
    env = dict(GOOD)
    env[key] = value
    with pytest.raises(ImproperlyConfigured):
        validate_production_settings(env)


@pytest.mark.django_db
def test_zoom_webhook_fails_closed_without_secret(settings):
    from apps.integrations.zoom import zoom_client
    settings.ZOOM_WEBHOOK_SECRET_TOKEN = ''
    ok, reason = zoom_client.verify_webhook_signature(
        {'HTTP_X_ZM_SIGNATURE': 'v0=abc', 'HTTP_X_ZM_REQUEST_TIMESTAMP': '1'}, b'{}')
    assert not ok


@pytest.mark.parametrize('extra', [
    {'PAYFAST_SKIP_IP_CHECK': 'true'},
    {'PAYFAST_SANDBOX': 'False'},  # live but no credentials
    {'PAYFAST_SANDBOX': 'False', 'PAYFAST_MERCHANT_ID': '10000100', 'PAYFAST_MERCHANT_KEY': 'k',
     'PAYFAST_PASSPHRASE': 'p', 'PAYFAST_NOTIFY_URL': 'https://api.sharonesl.com/x'},
    {'PAYPAL_CLIENT_ID': 'abc'},  # no webhook id
])
def test_unsafe_gateway_config_rejected(extra):
    with pytest.raises(ImproperlyConfigured):
        validate_production_settings({**GOOD, **extra})


def test_live_payfast_with_full_config_passes():
    validate_production_settings({**GOOD, 'PAYFAST_SANDBOX': 'False', 'PAYFAST_MERCHANT_ID': '12345678',
                                  'PAYFAST_MERCHANT_KEY': 'k', 'PAYFAST_PASSPHRASE': 'p',
                                  'PAYFAST_NOTIFY_URL': 'https://api.sharonesl.com/api/v1/payments/webhooks/payfast/'})
