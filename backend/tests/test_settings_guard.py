import json
import pytest
from cryptography.fernet import Fernet
from django.core.exceptions import ImproperlyConfigured

from config.settings.guard import validate_production_settings

GOOD = {
    'DJANGO_SECRET_KEY': 'x' * 60,
    'DJANGO_ALLOWED_HOSTS': 'api.sharonesl.com',
    'CORS_ALLOWED_ORIGINS': 'https://sharonesl.com',
    'CSRF_TRUSTED_ORIGINS': 'https://sharonesl.com,https://api.sharonesl.com',
    'ZOOM_WEBHOOK_SECRET_TOKEN': 'zoom-secret',
    'THROTTLE_NUM_PROXIES': '1',
    'FRONTEND_BASE_URL': 'https://sharonesl.com',
    'RESEND_API_KEY': 're_live_abcdefghijklmnop',
    'PAYOUT_DATA_KEYS': json.dumps({'v1': Fernet.generate_key().decode()}),
    'PAYOUT_DATA_ACTIVE_KEY': 'v1',
}


def test_valid_env_passes():
    validate_production_settings(dict(GOOD))


@pytest.mark.parametrize('key,value', [
    ('DJANGO_SECRET_KEY', ''),
    ('FRONTEND_BASE_URL', ''),
    ('FRONTEND_BASE_URL', 'http://sharonesl.com'),
    ('FRONTEND_BASE_URL', 'https://localhost:3000'),
    ('RESEND_API_KEY', ''),
    ('RESEND_API_KEY', 're_dev_placeholder'),
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
    ('PAYOUT_DATA_KEYS', '{}'),
    ('PAYOUT_DATA_ACTIVE_KEY', ''),
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
    {'PAYPAL_CLIENT_ID': 'abc'},  # no webhook id / secret
    {'PAYPAL_CLIENT_ID': 'abc', 'PAYPAL_CLIENT_SECRET': 's', 'PAYPAL_WEBHOOK_ID': 'w', 'PAYPAL_MODE': 'LIVE '.strip() + 'X'},
    # sandbox PayFast configured in production without the explicit staging opt-in
    {'PAYFAST_MERCHANT_ID': '10000100', 'PAYFAST_PASSPHRASE': 'p', 'PAYFAST_TRUSTED_PROXY_COUNT': '1'},
    # configured but empty passphrase -> signature is forgeable
    {'PAYFAST_MERCHANT_ID': '10000100', 'ALLOW_PAYMENT_SANDBOX_IN_PROD': '1', 'PAYFAST_TRUSTED_PROXY_COUNT': '1'},
    # configured but no trusted proxy count -> every ITN would fail the IP check
    {'PAYFAST_MERCHANT_ID': '10000100', 'PAYFAST_PASSPHRASE': 'p', 'ALLOW_PAYMENT_SANDBOX_IN_PROD': '1'},
    {'PAYFAST_SANDBOX': 'False', 'PAYFAST_MERCHANT_ID': '12345678', 'PAYFAST_MERCHANT_KEY': 'k',
     'PAYFAST_PASSPHRASE': 'p', 'PAYFAST_TRUSTED_PROXY_COUNT': '1', 'PAYFAST_NOTIFY_URL': 'http://api.sharonesl.com/x'},
])
def test_unsafe_gateway_config_rejected(extra):
    with pytest.raises(ImproperlyConfigured):
        validate_production_settings({**GOOD, **extra})


def test_live_payfast_with_full_config_passes():
    validate_production_settings({**GOOD, 'PAYFAST_SANDBOX': 'False', 'PAYFAST_MERCHANT_ID': '12345678',
                                  'PAYFAST_MERCHANT_KEY': 'k', 'PAYFAST_PASSPHRASE': 'p',
                                  'PAYFAST_TRUSTED_PROXY_COUNT': '1',
                                  'PAYFAST_NOTIFY_URL': 'https://api.sharonesl.com/api/v1/payments/webhooks/payfast/'})


def test_missing_proxy_count_rejected_unless_explicitly_direct():
    env = {k: v for k, v in GOOD.items() if k != 'THROTTLE_NUM_PROXIES'}
    with pytest.raises(ImproperlyConfigured):
        validate_production_settings(env)
    validate_production_settings({**env, 'BEHIND_NO_PROXY': '1'})


def test_sandbox_allowed_only_with_explicit_staging_opt_in():
    validate_production_settings({**GOOD, 'PAYFAST_MERCHANT_ID': '10000100', 'PAYFAST_PASSPHRASE': 'p',
                                  'PAYFAST_TRUSTED_PROXY_COUNT': '1', 'ALLOW_PAYMENT_SANDBOX_IN_PROD': '1'})


def test_throttle_num_proxies_zero_is_not_none():
    """DRF treats None as 'trust the client X-Forwarded-For'. 0 must stay 0."""
    from django.conf import settings
    assert settings.REST_FRAMEWORK['NUM_PROXIES'] is not None
