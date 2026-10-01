"""PayPal webhook verification and server-side capture lookup."""
import logging

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


class PayPalError(Exception):
    """Transport/API failure talking to PayPal (caller should return 5xx so PayPal retries)."""


def _base_url() -> str:
    return 'https://api-m.paypal.com' if settings.PAYPAL_MODE == 'live' else 'https://api-m.sandbox.paypal.com'


def get_access_token() -> str:
    token = cache.get('paypal:access_token')
    if token:
        return token
    try:
        resp = requests.post(f"{_base_url()}/v1/oauth2/token", data={'grant_type': 'client_credentials'},
                             auth=(settings.PAYPAL_CLIENT_ID, settings.PAYPAL_CLIENT_SECRET), timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise PayPalError(f"PayPal token request failed: {exc}") from exc
    cache.set('paypal:access_token', data['access_token'], max(int(data.get('expires_in', 300)) - 60, 30))
    return data['access_token']


def _auth_headers() -> dict:
    return {'Authorization': f"Bearer {get_access_token()}", 'Content-Type': 'application/json'}


def verify_webhook_signature(meta: dict, event: dict) -> bool:
    """PayPal's verify-webhook-signature API. `meta` is the Django request.META mapping."""
    def h(name):
        return meta.get(f"HTTP_PAYPAL_{name}", '')
    payload = {
        'auth_algo': h('AUTH_ALGO'), 'cert_url': h('CERT_URL'),
        'transmission_id': h('TRANSMISSION_ID'), 'transmission_sig': h('TRANSMISSION_SIG'),
        'transmission_time': h('TRANSMISSION_TIME'),
        'webhook_id': settings.PAYPAL_WEBHOOK_ID, 'webhook_event': event,
    }
    if not all(payload[k] for k in ('auth_algo', 'cert_url', 'transmission_id', 'transmission_sig',
                                    'transmission_time', 'webhook_id')):
        return False
    try:
        resp = requests.post(f"{_base_url()}/v1/notifications/verify-webhook-signature",
                             json=payload, headers=_auth_headers(), timeout=10)
        resp.raise_for_status()
        return resp.json().get('verification_status') == 'SUCCESS'
    except (requests.RequestException, ValueError) as exc:
        raise PayPalError(f"PayPal signature verification failed: {exc}") from exc


def get_capture(capture_id: str) -> dict:
    try:
        resp = requests.get(f"{_base_url()}/v2/payments/captures/{capture_id}", headers=_auth_headers(), timeout=10)
        resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise PayPalError(f"PayPal capture lookup failed: {exc}") from exc
