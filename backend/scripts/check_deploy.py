"""
Run Django's `check --deploy` against the PRODUCTION settings module, with throwaway but valid configuration.

Why a script: production settings refuse to load without a dozen real-looking secrets (config/settings/guard.py), so a bare
`manage.py check --deploy` cannot run in CI. The values below are random per run, never used for anything but this check, and
never touch a database or any provider (no connection is made).

    python scripts/check_deploy.py          # exits non-zero on any warning or error
"""
import json
import os
import secrets
import sys

from cryptography.fernet import Fernet

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def throwaway_environment() -> dict:
    key_id = 'ci1'
    return {
        'DJANGO_SETTINGS_MODULE': 'config.settings.production',
        'DJANGO_SECRET_KEY': secrets.token_urlsafe(64),
        'DJANGO_ALLOWED_HOSTS': 'api.sharonesl.com',
        'CORS_ALLOWED_ORIGINS': 'https://sharonesl.com',
        'CSRF_TRUSTED_ORIGINS': 'https://sharonesl.com',
        'FRONTEND_BASE_URL': 'https://sharonesl.com',
        'RESEND_API_KEY': 're_ci_' + secrets.token_hex(8),
        'ZOOM_WEBHOOK_SECRET_TOKEN': secrets.token_hex(16),
        'ESKOMSEPUSH_API_KEY': secrets.token_hex(8),
        'PAYOUT_DATA_KEYS': json.dumps({key_id: Fernet.generate_key().decode()}),
        'PAYOUT_DATA_ACTIVE_KEY': key_id,
        'THROTTLE_NUM_PROXIES': '1',
        'DATABASE_URL': 'postgresql://ci:ci@db.invalid:5432/ci',
        'REDIS_URL': 'rediss://cache.invalid:6379/0',
        # Production must route refunds to the real gateways; the manual backend moves no money (Task 10.7).
        'REFUND_GATEWAY_BACKEND': 'apps.payments.services.refund_gateways.RoutingRefundGateway',
    }


def refund_backend_problems(backend: str) -> list:
    """Reasons a production deployment must not start with this REFUND_GATEWAY_BACKEND (empty list = fine)."""
    if not backend or backend.rsplit('.', 1)[-1] == 'ManualSandboxRefundGateway':
        return ["REFUND_GATEWAY_BACKEND is the manual sandbox backend: refunds would never reach the students' payment methods. "
                "Set it to apps.payments.services.refund_gateways.RoutingRefundGateway."]
    return []


def main() -> int:
    os.chdir(BACKEND_DIR)
    sys.path.insert(0, BACKEND_DIR)
    environment = throwaway_environment()
    for name in ('REFUND_GATEWAY_BACKEND',):               # the one throwaway value a caller may override, to prove the check bites
        if name in os.environ:
            environment[name] = os.environ[name]
    os.environ.update(environment)

    import django
    from django.core.management import call_command

    django.setup()
    from django.conf import settings

    problems = refund_backend_problems(getattr(settings, 'REFUND_GATEWAY_BACKEND', ''))
    for problem in problems:
        print(f'check --deploy: {problem}', file=sys.stderr)
    if problems:
        return 1
    call_command('check', deploy=True, fail_level='WARNING')
    print('check --deploy: no issues against the production settings')
    return 0


if __name__ == '__main__':
    sys.exit(main())
