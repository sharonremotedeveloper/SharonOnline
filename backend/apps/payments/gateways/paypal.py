"""PayPal webhook verification and server-side capture lookup."""
import json
import logging
from datetime import datetime, timedelta, timezone as dt_timezone
from urllib.parse import quote, urlparse

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

TOKEN_CACHE_KEY = 'paypal:access_token'
ALLOWED_AUTH_ALGOS = ('SHA256withRSA',)
# PayPal retries undelivered webhooks for ~3 days and may keep the original transmission time, so the age window
# must cover the retry period. Replay safety comes from idempotency, not from a tight clock check.
MAX_TRANSMISSION_AGE = timedelta(days=4)
MAX_TRANSMISSION_FUTURE = timedelta(minutes=10)


class PayPalError(Exception):
    """Transport/API failure talking to PayPal (caller should return 5xx so PayPal retries)."""


def _base_url() -> str:
    return 'https://api-m.paypal.com' if str(settings.PAYPAL_MODE).strip().lower() == 'live' else 'https://api-m.sandbox.paypal.com'


def get_access_token(force_refresh: bool = False) -> str:
    if not force_refresh:
        token = cache.get(TOKEN_CACHE_KEY)
        if token:
            return token
    try:
        resp = requests.post(f"{_base_url()}/v1/oauth2/token", data={'grant_type': 'client_credentials'},
                             auth=(settings.PAYPAL_CLIENT_ID, settings.PAYPAL_CLIENT_SECRET), timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise PayPalError(f"PayPal token request failed: {exc}") from exc
    cache.set(TOKEN_CACHE_KEY, data['access_token'], max(int(data.get('expires_in', 300)) - 60, 30))
    return data['access_token']


def _auth_headers(force_refresh: bool = False) -> dict:
    return {'Authorization': f"Bearer {get_access_token(force_refresh)}", 'Content-Type': 'application/json'}


def _call(method: str, url: str, **kwargs):
    """Authenticated PayPal call; on a 401 the cached token is discarded and the call retried once."""
    resp = None
    for attempt in (0, 1):
        resp = requests.request(method, url, headers=_auth_headers(force_refresh=bool(attempt)), timeout=10, **kwargs)
        if getattr(resp, 'status_code', None) == 401 and attempt == 0:
            cache.delete(TOKEN_CACHE_KEY)
            continue
        break
    return resp


def _trusted_cert_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname or ''
    return parsed.scheme == 'https' and (host == 'paypal.com' or host.endswith('.paypal.com'))


def _transmission_time_ok(value: str) -> bool:
    try:
        sent = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return False
    if sent.tzinfo is None:
        sent = sent.replace(tzinfo=dt_timezone.utc)
    now = datetime.now(dt_timezone.utc)
    return now - MAX_TRANSMISSION_AGE <= sent <= now + MAX_TRANSMISSION_FUTURE


def verify_webhook_signature(meta: dict, raw_body: bytes) -> bool:
    """
    PayPal's verify-webhook-signature API. `meta` is Django's request.META and `raw_body` the exact bytes received:
    PayPal's CRC is computed over the original event text, so it must be forwarded verbatim, not re-serialised.

    Returns False for anything PayPal says is invalid (including its 4xx answers); raises PayPalError only when PayPal
    itself is unreachable/failing so the caller can answer 5xx and let PayPal retry.
    """
    def h(name):
        return meta.get(f"HTTP_PAYPAL_{name}", '')

    fields = {
        'auth_algo': h('AUTH_ALGO'), 'cert_url': h('CERT_URL'),
        'transmission_id': h('TRANSMISSION_ID'), 'transmission_sig': h('TRANSMISSION_SIG'),
        'transmission_time': h('TRANSMISSION_TIME'), 'webhook_id': settings.PAYPAL_WEBHOOK_ID,
    }
    if not all(fields.values()):
        return False
    # Cheap local checks first, so unauthenticated callers cannot make us spend OAuth/API calls on obvious junk.
    if fields['auth_algo'] not in ALLOWED_AUTH_ALGOS:
        return False
    if not _trusted_cert_url(fields['cert_url']):
        return False
    if not _transmission_time_ok(fields['transmission_time']):
        return False

    try:
        event_text = raw_body.decode('utf-8')
        json.loads(event_text)  # must at least be valid JSON before it is spliced into the request
    except (UnicodeDecodeError, ValueError):
        return False
    head = json.dumps(fields)
    body = f'{head[:-1]}, "webhook_event": {event_text}}}'

    try:
        resp = _call('POST', f"{_base_url()}/v1/notifications/verify-webhook-signature", data=body.encode('utf-8'))
    except requests.RequestException as exc:
        raise PayPalError(f"PayPal signature verification failed: {exc}") from exc
    status = getattr(resp, 'status_code', 200)
    if status in (400, 422):
        return False
    try:
        resp.raise_for_status()
        return resp.json().get('verification_status') == 'SUCCESS'
    except (requests.RequestException, ValueError) as exc:
        raise PayPalError(f"PayPal signature verification failed: {exc}") from exc


def get_capture(capture_id: str) -> dict:
    try:
        resp = _call('GET', f"{_base_url()}/v2/payments/captures/{quote(str(capture_id), safe='')}")
        resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise PayPalError(f"PayPal capture lookup failed: {exc}") from exc
