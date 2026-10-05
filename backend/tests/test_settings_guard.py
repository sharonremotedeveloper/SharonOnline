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
    'ESKOMSEPUSH_API_KEY': 'eskom-provider-key',
    'THROTTLE_NUM_PROXIES': '1',
    'FRONTEND_BASE_URL': 'https://sharonesl.com',
    'RESEND_API_KEY': 're_live_abcdefghijklmnop',
    'PAYOUT_DATA_KEYS': json.dumps({'v1': Fernet.generate_key().decode()}),
    'PAYOUT_DATA_ACTIVE_KEY': 'v1',
    'INTEGRATION_DATA_KEYS': json.dumps({'v1': Fernet.generate_key().decode()}),
    'INTEGRATION_DATA_ACTIVE_KEY': 'v1',
    'CLOUDFLARE_R2_PRIVATE_BUCKET_NAME': 'esl-private',
    'REFUND_GATEWAY_BACKEND': 'apps.payments.services.refund_gateways.RoutingRefundGateway',
    # Slice Z1: production refuses to boot without Zoom S2S credentials.
    'ZOOM_ACCOUNT_ID': 'zoom-account', 'ZOOM_CLIENT_ID': 'zoom-client', 'ZOOM_CLIENT_SECRET': 'zoom-secret-value',
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
    ('ESKOMSEPUSH_API_KEY', ''),
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


LIVE_PAYFAST = {'PAYFAST_SANDBOX': 'False', 'PAYFAST_MERCHANT_ID': '12345678', 'PAYFAST_MERCHANT_KEY': 'k',
                'PAYFAST_PASSPHRASE': 'p', 'PAYFAST_TRUSTED_PROXY_COUNT': '1',
                'PAYFAST_NOTIFY_URL': 'https://api.sharonesl.com/api/v1/payments/webhooks/payfast/',
                'PAYFAST_RETURN_URL': 'https://sharonesl.com/student/checkout/return',
                'PAYFAST_CANCEL_URL': 'https://sharonesl.com/student/checkout/cancel'}


def test_live_payfast_with_return_and_cancel_urls_passes():
    validate_production_settings({**GOOD, **LIVE_PAYFAST})


@pytest.mark.parametrize('name,value', [
    ('PAYFAST_RETURN_URL', 'http://sharonesl.com/student/checkout/return'),
    ('PAYFAST_CANCEL_URL', 'http://sharonesl.com/student/checkout/cancel'),
    ('PAYFAST_RETURN_URL', 'https://localhost:3000/student/checkout/return'),
    ('PAYFAST_CANCEL_URL', 'https://127.0.0.1/student/checkout/cancel'),
])
def test_live_payfast_rejects_insecure_or_local_return_cancel_urls(name, value):
    with pytest.raises(ImproperlyConfigured):
        validate_production_settings({**GOOD, **LIVE_PAYFAST, name: value})


def test_live_payfast_return_cancel_urls_default_from_frontend_when_unset():
    env = {**GOOD, **LIVE_PAYFAST}
    del env['PAYFAST_RETURN_URL'], env['PAYFAST_CANCEL_URL']
    validate_production_settings(env)  # defaults derive from the (already guarded https) FRONTEND_BASE_URL


# ---- Task 10.7 QA H2: production must refuse the manual (money-less) refund backend AT BOOT --------------------------------
MANUAL_PATHS = [
    'apps.payments.services.refunds.ManualSandboxRefundGateway',
    'apps.payments.services.refund_gateways.ManualSandboxRefundGateway',
    'some.other.module.ManualSandboxRefundGateway',
]


@pytest.mark.parametrize('backend', MANUAL_PATHS)
def test_the_manual_refund_backend_is_refused_at_boot(backend):
    with pytest.raises(ImproperlyConfigured, match='REFUND_GATEWAY_BACKEND'):
        validate_production_settings({**GOOD, 'REFUND_GATEWAY_BACKEND': backend})


@pytest.mark.parametrize('blank', ['', '   '])
def test_an_unset_or_blank_refund_backend_resolves_to_the_manual_default_and_is_refused(blank):
    env = {k: v for k, v in GOOD.items() if k != 'REFUND_GATEWAY_BACKEND'}
    with pytest.raises(ImproperlyConfigured, match='REFUND_GATEWAY_BACKEND'):
        validate_production_settings(env)
    with pytest.raises(ImproperlyConfigured, match='REFUND_GATEWAY_BACKEND'):
        validate_production_settings({**env, 'REFUND_GATEWAY_BACKEND': blank})


def test_the_routing_refund_backend_is_accepted():
    validate_production_settings({**GOOD, 'REFUND_GATEWAY_BACKEND': 'apps.payments.services.refund_gateways.RoutingRefundGateway'})


@pytest.mark.parametrize('flag', ['1', 'true', 'YES'])
def test_the_manual_refund_backend_needs_the_explicit_override(flag):
    validate_production_settings({**GOOD, 'REFUND_GATEWAY_BACKEND': MANUAL_PATHS[0], 'ALLOW_MANUAL_REFUNDS_IN_PROD': flag})


@pytest.mark.parametrize('flag', ['', '0', 'false', 'no'])
def test_a_falsy_override_does_not_unlock_the_manual_backend(flag):
    with pytest.raises(ImproperlyConfigured, match='REFUND_GATEWAY_BACKEND'):
        validate_production_settings({**GOOD, 'REFUND_GATEWAY_BACKEND': MANUAL_PATHS[0], 'ALLOW_MANUAL_REFUNDS_IN_PROD': flag})


def test_the_override_is_not_needed_for_the_routing_backend():
    validate_production_settings({**GOOD, 'ALLOW_MANUAL_REFUNDS_IN_PROD': '0'})


def test_the_error_names_the_override_and_the_production_value():
    with pytest.raises(ImproperlyConfigured) as raised:
        validate_production_settings({**GOOD, 'REFUND_GATEWAY_BACKEND': MANUAL_PATHS[0]})
    text = str(raised.value)
    assert 'ALLOW_MANUAL_REFUNDS_IN_PROD' in text and 'RoutingRefundGateway' in text


def test_a_blank_refund_backend_env_means_the_default_in_base_settings(monkeypatch):
    from importlib import import_module, reload
    base = import_module('config.settings.base')
    try:
        monkeypatch.setenv('REFUND_GATEWAY_BACKEND', '')
        assert reload(base).REFUND_GATEWAY_BACKEND == 'apps.payments.services.refunds.ManualSandboxRefundGateway'
        monkeypatch.setenv('REFUND_GATEWAY_BACKEND', '   ')
        assert reload(base).REFUND_GATEWAY_BACKEND == 'apps.payments.services.refunds.ManualSandboxRefundGateway'
        monkeypatch.setenv('REFUND_GATEWAY_BACKEND', 'apps.payments.services.refund_gateways.RoutingRefundGateway')
        assert reload(base).REFUND_GATEWAY_BACKEND.endswith('RoutingRefundGateway')
    finally:
        monkeypatch.undo()
        reload(base)


def test_env_example_documents_both_refund_settings():
    from pathlib import Path
    example = (Path(__file__).resolve().parents[2] / '.env.example').read_text(encoding='utf-8')
    assert 'REFUND_GATEWAY_BACKEND=' in example and 'ALLOW_MANUAL_REFUNDS_IN_PROD=' in example
    assert 'apps.payments.services.refund_gateways.RoutingRefundGateway' in example


def test_zoom_video_sdk_passes_with_32_plus_char_secret():
    env = dict(GOOD)
    for k in ('ZOOM_ACCOUNT_ID', 'ZOOM_CLIENT_ID', 'ZOOM_CLIENT_SECRET'):
        del env[k]
    env['ZOOM_VIDEO_SDK_KEY'] = 'test-video-sdk-key-1234567890'
    env['ZOOM_VIDEO_SDK_SECRET'] = 'x' * 32
    validate_production_settings(env)


def test_zoom_video_sdk_rejects_secret_shorter_than_32_chars():
    env = dict(GOOD)
    env['ZOOM_VIDEO_SDK_KEY'] = 'test-video-sdk-key-1234567890'
    env['ZOOM_VIDEO_SDK_SECRET'] = 'short-18-byte-key!'
    with pytest.raises(ImproperlyConfigured, match='ZOOM_VIDEO_SDK_SECRET must be at least 32 characters'):
        validate_production_settings(env)


def test_zoom_video_sdk_rejects_key_without_secret():
    env = dict(GOOD)
    env['ZOOM_VIDEO_SDK_KEY'] = 'test-video-sdk-key'
    env['ZOOM_VIDEO_SDK_SECRET'] = ''
    with pytest.raises(ImproperlyConfigured, match='ZOOM_VIDEO_SDK_SECRET must be set'):
        validate_production_settings(env)


def test_zoom_video_sdk_rejects_secret_without_key():
    env = dict(GOOD)
    env['ZOOM_VIDEO_SDK_KEY'] = ''
    env['ZOOM_VIDEO_SDK_SECRET'] = 'x' * 32
    with pytest.raises(ImproperlyConfigured, match='ZOOM_VIDEO_SDK_KEY must be set'):
        validate_production_settings(env)

