import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

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
    # Daily.co video conferencing credentials (Decision D-14 / Requirement R4)
    'DAILY_API_KEY': 'daily-live-api-key-test-value-0123456789',
    'DAILY_DOMAIN': 'sharonesl.daily.co',
    'DAILY_WEBHOOK_SECRET': 'daily-webhook-secret-base64-at-least-16-chars',
    # Slice Z1: legacy Zoom credentials retained during transition
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
    ('DAILY_API_KEY', ''),
    ('DAILY_API_KEY', '   '),
    ('DAILY_DOMAIN', ''),
    ('DAILY_DOMAIN', '   '),
    ('DAILY_DOMAIN', 'localhost'),
    ('DAILY_DOMAIN', 'http://localhost:3000'),
    ('DAILY_DOMAIN', '127.0.0.1'),
    ('DAILY_WEBHOOK_SECRET', ''),
    ('DAILY_WEBHOOK_SECRET', '   '),
    ('DAILY_WEBHOOK_SECRET', 'short-secret'),  # < 16 chars
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


# ==============================================================================
# Daily.co Video Conferencing Settings Guard Tests (Decision D-14 / Requirement R4)
# ==============================================================================

@pytest.mark.parametrize('value', ['', '   ', None])
def test_production_refuses_missing_or_blank_daily_api_key(value):
    """Production boot must fail fast if DAILY_API_KEY is missing or whitespace."""
    env = dict(GOOD)
    if value is None:
        del env['DAILY_API_KEY']
    else:
        env['DAILY_API_KEY'] = value
    with pytest.raises(ImproperlyConfigured, match='DAILY_API_KEY'):
        validate_production_settings(env)


@pytest.mark.parametrize('value', ['', '   ', None])
def test_production_refuses_missing_or_blank_daily_domain(value):
    """Production boot must fail fast if DAILY_DOMAIN is missing or whitespace."""
    env = dict(GOOD)
    if value is None:
        del env['DAILY_DOMAIN']
    else:
        env['DAILY_DOMAIN'] = value
    with pytest.raises(ImproperlyConfigured, match='DAILY_DOMAIN'):
        validate_production_settings(env)


@pytest.mark.parametrize('bad_domain', ['localhost', 'http://localhost:3000', '127.0.0.1', '0.0.0.0', 'sub.localhost'])  # noqa: S104
def test_production_refuses_localhost_daily_domain(bad_domain):
    """Production boot must reject localhost / loopback Daily domains."""
    env = dict(GOOD, DAILY_DOMAIN=bad_domain)
    with pytest.raises(ImproperlyConfigured, match='DAILY_DOMAIN must not be localhost'):
        validate_production_settings(env)


@pytest.mark.parametrize('value', ['', '   ', None])
def test_production_refuses_missing_or_blank_daily_webhook_secret(value):
    """Production boot must fail fast if DAILY_WEBHOOK_SECRET is missing or whitespace."""
    env = dict(GOOD)
    if value is None:
        del env['DAILY_WEBHOOK_SECRET']
    else:
        env['DAILY_WEBHOOK_SECRET'] = value
    with pytest.raises(ImproperlyConfigured, match='DAILY_WEBHOOK_SECRET'):
        validate_production_settings(env)


@pytest.mark.parametrize('short_secret', ['a', 'secret', '123456789012345'])
def test_production_refuses_short_daily_webhook_secret(short_secret):
    """Production boot requires at least 16 chars for DAILY_WEBHOOK_SECRET entropy."""
    env = dict(GOOD, DAILY_WEBHOOK_SECRET=short_secret)
    with pytest.raises(ImproperlyConfigured, match='DAILY_WEBHOOK_SECRET must be at least 16 characters'):
        validate_production_settings(env)


def test_valid_daily_settings_pass():
    """Production boot succeeds cleanly with valid Daily credentials in GOOD."""
    validate_production_settings(dict(GOOD))


@pytest.mark.parametrize('domain', ['sharonesl', 'sharonesl.daily.co', 'custom.domain.com'])
def test_valid_daily_domain_variants_pass(domain):
    """Both subdomains and fully-qualified Daily domains pass validation cleanly."""
    env = dict(GOOD, DAILY_DOMAIN=domain)
    validate_production_settings(env)


def test_daily_boots_without_legacy_zoom_credentials():
    """Daily credentials alone are sufficient for production boot once Zoom is removed."""
    env = dict(GOOD)
    for zoom_key in ('ZOOM_ACCOUNT_ID', 'ZOOM_CLIENT_ID', 'ZOOM_CLIENT_SECRET',
                     'ZOOM_WEBHOOK_SECRET_TOKEN', 'ZOOM_VIDEO_SDK_KEY', 'ZOOM_VIDEO_SDK_SECRET'):
        env.pop(zoom_key, None)
    # When Zoom boot guard is decoupled, this must pass without errors
    validate_production_settings(env)


def test_env_example_documents_daily_settings():
    """Documentation integrity: .env.example must document the new Daily settings."""
    example = (Path(__file__).resolve().parents[2] / '.env.example').read_text(encoding='utf-8')
    for name in ('DAILY_API_KEY=', 'DAILY_DOMAIN=', 'DAILY_WEBHOOK_SECRET='):
        assert name in example, f"{name} is missing from .env.example"


# ==============================================================================
# Daily.co Deploy Check Tests (scripts/check_deploy.py)
# ==============================================================================

SCRIPT = Path(__file__).resolve().parent.parent / 'scripts' / 'check_deploy.py'


def _load_check_deploy():
    spec = importlib.util.spec_from_file_location('check_deploy_daily_test', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_deploy_check_and_the_boot_guard_name_the_same_daily_settings():
    """Contract parity: check_deploy.DAILY_CREDENTIALS must exactly match guard.DAILY_CREDENTIAL_SETTINGS."""
    from config.settings import guard
    script = _load_check_deploy()
    assert hasattr(script, 'DAILY_CREDENTIALS'), "check_deploy.py must define DAILY_CREDENTIALS"
    assert hasattr(guard, 'DAILY_CREDENTIAL_SETTINGS'), "guard.py must define DAILY_CREDENTIAL_SETTINGS"
    assert tuple(script.DAILY_CREDENTIALS) == tuple(guard.DAILY_CREDENTIAL_SETTINGS)
    assert set(script.DAILY_CREDENTIALS) == {'DAILY_API_KEY', 'DAILY_DOMAIN', 'DAILY_WEBHOOK_SECRET'}


@pytest.mark.parametrize('name', ['DAILY_API_KEY', 'DAILY_DOMAIN', 'DAILY_WEBHOOK_SECRET'])
@pytest.mark.parametrize('bad_value', ['', '   '])
def test_daily_credentials_problems_reports_missing_setting(name, bad_value):
    """daily_credentials_problems must detect and report missing or whitespace Daily settings."""
    script = _load_check_deploy()
    env = {
        'DAILY_API_KEY': 'valid-api-key',
        'DAILY_DOMAIN': 'sharonesl.daily.co',
        'DAILY_WEBHOOK_SECRET': 'valid-webhook-secret-16chars',
    }
    env[name] = bad_value
    problems = script.daily_credentials_problems(env)
    assert any(name in p for p in problems), f"Expected problem mentioning {name}, got {problems}"


@pytest.mark.parametrize('bad_domain', ['localhost', 'http://localhost:3000', '127.0.0.1'])
def test_daily_credentials_problems_reports_localhost_domain(bad_domain):
    """daily_credentials_problems must reject localhost domains."""
    script = _load_check_deploy()
    env = {
        'DAILY_API_KEY': 'valid-api-key',
        'DAILY_DOMAIN': bad_domain,
        'DAILY_WEBHOOK_SECRET': 'valid-webhook-secret-16chars',
    }
    problems = script.daily_credentials_problems(env)
    assert any('localhost' in p.lower() for p in problems)


def test_daily_credentials_problems_reports_short_webhook_secret():
    """daily_credentials_problems must report secrets under 16 characters."""
    script = _load_check_deploy()
    env = {
        'DAILY_API_KEY': 'valid-api-key',
        'DAILY_DOMAIN': 'sharonesl.daily.co',
        'DAILY_WEBHOOK_SECRET': 'short',
    }
    problems = script.daily_credentials_problems(env)
    assert any('16 characters' in p for p in problems)


def test_daily_credentials_problems_clean_when_all_present():
    """daily_credentials_problems returns empty list when all settings are valid."""
    script = _load_check_deploy()
    env = {
        'DAILY_API_KEY': 'valid-api-key',
        'DAILY_DOMAIN': 'sharonesl.daily.co',
        'DAILY_WEBHOOK_SECRET': 'valid-webhook-secret-16chars',
    }
    assert script.daily_credentials_problems(env) == []


def test_throwaway_environment_contains_valid_daily_credentials():
    """throwaway_environment() must generate valid dummy credentials for Daily."""
    script = _load_check_deploy()
    env = script.throwaway_environment()
    for name in ('DAILY_API_KEY', 'DAILY_DOMAIN', 'DAILY_WEBHOOK_SECRET'):
        assert name in env, f"{name} missing from throwaway_environment()"
        assert (env[name] or '').strip() != '', f"{name} is empty in throwaway_environment()"
    assert script.daily_credentials_problems(env) == []


def _run_check_deploy(extra_env=None):
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    backend_dir = Path(__file__).resolve().parent.parent
    return subprocess.run([sys.executable, str(SCRIPT)], cwd=backend_dir, env=env, capture_output=True, text=True, timeout=180)  # noqa: S603


def test_check_deploy_script_passes_with_default_throwaway_env():
    """Default throwaway environment passes check --deploy cleanly."""
    done = _run_check_deploy()
    assert done.returncode == 0, f"check_deploy failed: {done.stdout}\n{done.stderr}"
    assert 'no issues against the production settings' in done.stdout


@pytest.mark.parametrize('name', ['DAILY_API_KEY', 'DAILY_DOMAIN', 'DAILY_WEBHOOK_SECRET'])
def test_check_deploy_script_fails_when_daily_credential_empty(name):
    """Overriding any Daily credential to empty in the environment fails check_deploy."""
    done = _run_check_deploy({name: ''})
    assert done.returncode != 0
    combined = done.stdout + done.stderr
    assert name in combined, f"Expected {name} in output, got: {combined}"


