import logging
import os
import json
from urllib.parse import urlparse

from cryptography.fernet import Fernet
from django.core.exceptions import ImproperlyConfigured

_DEV_SECRET_PREFIX = 'django-insecure'
SANDBOX_PAYFAST_MERCHANT_ID = '10000100'
_DEFAULT_REFUND_BACKEND = 'apps.payments.services.refunds.ManualSandboxRefundGateway'    # what settings/base.py uses when the env is unset
_ROUTING_REFUND_BACKEND = 'apps.payments.services.refund_gateways.RoutingRefundGateway'
_LOCAL_HOSTS = {'localhost', '127.0.0.1', '0.0.0.0', 'backend', '::1'}


def _is_local_origin(origin: str) -> bool:
    host = urlparse(origin).hostname or ''
    return host in _LOCAL_HOSTS or host.endswith('.localhost')


_log = logging.getLogger(__name__)

EMAIL_MODES = ('resend', 'console')


def resolve_email_backend_mode(env=os.environ) -> str:
    """EMAIL_BACKEND_MODE when set; otherwise 'resend' with a real RESEND_API_KEY and 'console' without one (slice N1c).

    Used by settings/base.py and by the production guard below, so both read the same answer from the same environment.
    """
    explicit = (env.get('EMAIL_BACKEND_MODE', '') or '').strip().lower()
    if explicit:
        return explicit
    key = env.get('RESEND_API_KEY', '') or ''
    return 'resend' if key and not key.startswith('re_dev') else 'console'


def validate_production_settings(env=os.environ):
    """Fail fast: refuse to boot production with dev defaults or missing security config."""
    errors = []
    secret = env.get('DJANGO_SECRET_KEY', '')
    if not secret or secret.startswith(_DEV_SECRET_PREFIX) or len(secret) < 50:
        errors.append('DJANGO_SECRET_KEY must be a unique random value (>=50 chars, not the dev key)')

    hosts = [h.strip() for h in env.get('DJANGO_ALLOWED_HOSTS', '').split(',') if h.strip()]
    if not hosts or any(h in _LOCAL_HOSTS or h == '*' for h in hosts):
        errors.append('DJANGO_ALLOWED_HOSTS must list real hostnames (no localhost, internal names or *)')

    for name in ('CORS_ALLOWED_ORIGINS', 'CSRF_TRUSTED_ORIGINS'):
        origins = [o.strip() for o in env.get(name, '').split(',') if o.strip()]
        if not origins:
            errors.append(f'{name} must be set')
        elif any(_is_local_origin(o) or not o.startswith('https://') for o in origins):
            errors.append(f'{name} must be https:// origins and must not include localhost')

    frontend = env.get('FRONTEND_BASE_URL', '')
    if not frontend.startswith('https://') or _is_local_origin(frontend):
        errors.append('FRONTEND_BASE_URL must be the public https:// site URL (it is the base of every password-reset / verification link)')
    resend_key = env.get('RESEND_API_KEY', '')
    if not resend_key or resend_key.startswith('re_dev'):
        errors.append('RESEND_API_KEY must be a real key: without it password-reset and verification e-mails are silently not sent')
    email_mode = resolve_email_backend_mode(env)
    if email_mode != 'resend':
        errors.append(f"EMAIL_BACKEND_MODE must be 'resend' in production (got {email_mode!r}); "
                      f"'console' only prints e-mails and is for local development and tests")

    if not env.get('ZOOM_WEBHOOK_SECRET_TOKEN'):
        errors.append('ZOOM_WEBHOOK_SECRET_TOKEN must be set')
    if not env.get('ESKOMSEPUSH_API_KEY'):
        errors.append('ESKOMSEPUSH_API_KEY must be set so Power Guard never fabricates provider status')

    try:
        payout_keys = json.loads(env.get('PAYOUT_DATA_KEYS', '{}'))
    except ValueError:
        payout_keys = {}
    payout_active = env.get('PAYOUT_DATA_ACTIVE_KEY', '')
    if not isinstance(payout_keys, dict) or not payout_active or payout_active not in payout_keys:
        errors.append('PAYOUT_DATA_KEYS must be a JSON keyring containing PAYOUT_DATA_ACTIVE_KEY')
    else:
        try:
            for key in payout_keys.values():
                Fernet(str(key).encode('ascii'))
        except (ValueError, UnicodeError):
            errors.append('Every PAYOUT_DATA_KEYS value must be a valid Fernet key')

    truthy = ('1', 'true', 'yes')
    no_proxy = env.get('BEHIND_NO_PROXY', '').lower() in truthy

    def _int(name):
        try:
            return int(env.get(name, '0') or 0)
        except ValueError:
            return -1

    # Client-IP trust. With 0 trusted proxies every request appears to come from the load balancer (one shared
    # throttle bucket, and PayFast's source-IP check can never match); a wrong number lets clients spoof X-Forwarded-For.
    if not no_proxy and _int('THROTTLE_NUM_PROXIES') < 1:
        errors.append('THROTTLE_NUM_PROXIES must be >= 1 behind a reverse proxy (or set BEHIND_NO_PROXY=1 if directly exposed)')

    payfast_configured = bool(env.get('PAYFAST_MERCHANT_ID'))
    if env.get('PAYFAST_SKIP_IP_CHECK', '').lower() in truthy:
        errors.append('PAYFAST_SKIP_IP_CHECK must not be enabled in production')
    payfast_sandbox = env.get('PAYFAST_SANDBOX', 'True').lower() in truthy
    if payfast_sandbox and payfast_configured and env.get('ALLOW_PAYMENT_SANDBOX_IN_PROD', '').lower() not in truthy:
        errors.append('PAYFAST_SANDBOX is on in production; set ALLOW_PAYMENT_SANDBOX_IN_PROD=1 only for a deliberate staging deploy')
    if not payfast_sandbox:  # live PayFast
        for name in ('PAYFAST_MERCHANT_ID', 'PAYFAST_MERCHANT_KEY', 'PAYFAST_PASSPHRASE', 'PAYFAST_NOTIFY_URL'):
            if not env.get(name):
                errors.append(f'{name} is required when PAYFAST_SANDBOX is false')
        if env.get('PAYFAST_MERCHANT_ID') == SANDBOX_PAYFAST_MERCHANT_ID:
            errors.append('PayFast sandbox merchant id must not be used with PAYFAST_SANDBOX=False')
    if payfast_configured:
        # An empty passphrase makes the ITN signature a plain MD5 of public data that anyone can compute.
        if not env.get('PAYFAST_PASSPHRASE'):
            errors.append('PAYFAST_PASSPHRASE is required whenever PayFast is configured')
        if not no_proxy and _int('PAYFAST_TRUSTED_PROXY_COUNT') < 1:
            errors.append('PAYFAST_TRUSTED_PROXY_COUNT must be >= 1 behind a reverse proxy, otherwise every ITN fails the source-IP check')
        notify = env.get('PAYFAST_NOTIFY_URL', '')
        if notify and not notify.startswith('https://'):
            errors.append('PAYFAST_NOTIFY_URL must be an https:// URL')
        for name in ('PAYFAST_RETURN_URL', 'PAYFAST_CANCEL_URL'):  # unset = derived from FRONTEND_BASE_URL (guarded above)
            url = env.get(name, '')
            if url and (not url.startswith('https://') or _is_local_origin(url)):
                errors.append(f'{name} must be a public https:// URL (no localhost)')

    if env.get('PAYPAL_CLIENT_ID'):
        if env.get('PAYPAL_MODE', 'sandbox').strip().lower() not in ('live', 'sandbox'):
            errors.append("PAYPAL_MODE must be exactly 'live' or 'sandbox'")
        for name in ('PAYPAL_CLIENT_SECRET', 'PAYPAL_WEBHOOK_ID'):
            if not env.get(name):
                errors.append(f'{name} is required when PayPal is configured')

    # Refunds: the manual backend moves no money, so a production process left on it (the base default) would queue every refund
    # forever while the ledger says "owed". Unset or blank resolves to that default, so it is refused too.
    refund_backend = (env.get('REFUND_GATEWAY_BACKEND', '') or '').strip() or _DEFAULT_REFUND_BACKEND
    if refund_backend.rsplit('.', 1)[-1] == 'ManualSandboxRefundGateway' and env.get('ALLOW_MANUAL_REFUNDS_IN_PROD', '').lower() not in truthy:
        errors.append(f'REFUND_GATEWAY_BACKEND is the manual refund backend, which never returns money to students; set it to '
                      f'{_ROUTING_REFUND_BACKEND}, or set ALLOW_MANUAL_REFUNDS_IN_PROD=1 only for a deliberate staging deploy')

    if (refund_backend.rsplit('.', 1)[-1] == 'RoutingRefundGateway'
            and not (env.get('PAYPAL_CLIENT_ID') and env.get('PAYPAL_CLIENT_SECRET'))):
        _log.warning('REFUND_GATEWAY_BACKEND is the routing backend but PayPal credentials are blank: PayPal refunds will wait for a person '
                     '(manual answers) until PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET are set.')

    if not (env.get('ADMIN_ALERT_RECIPIENTS', '') or '').strip():
        _log.warning('ADMIN_ALERT_RECIPIENTS is blank: staff alerts (fulfilment failures, disputes without a verdict, '
                     'undeliverable notifications) go to every active admin user, and only to the log if there is none. '
                     'Set it to the on-call staff addresses before go-live (docs/RUNBOOK_NOTIFICATIONS.md).')

    if errors:
        raise ImproperlyConfigured('Unsafe production configuration: ' + '; '.join(errors))
