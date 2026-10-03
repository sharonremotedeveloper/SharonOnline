"""PayPal webhook verification and server-side capture lookup."""
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as dt_timezone
from urllib.parse import quote, urlparse

import requests
from django.conf import settings
from django.core.cache import cache

from apps.payments.services.pricing import quantize_money

logger = logging.getLogger(__name__)

TOKEN_CACHE_KEY = 'paypal:access_token'
ALLOWED_AUTH_ALGOS = ('SHA256withRSA',)
# PayPal retries undelivered webhooks for ~3 days and may keep the original transmission time, so the age window
# must cover the retry period. Replay safety comes from idempotency, not from a tight clock check.
MAX_TRANSMISSION_AGE = timedelta(days=4)
MAX_TRANSMISSION_FUTURE = timedelta(minutes=10)


class PayPalError(Exception):
    """Transport/API failure talking to PayPal (caller should return 5xx so PayPal retries)."""


class PayPalRejected(PayPalError):
    """PayPal answered with a 4xx: the request itself was refused. `name`/`issue` are PayPal's error name and first issue."""

    def __init__(self, message: str, *, name: str = '', issue: str = '', status_code: int = 0):
        super().__init__(message)
        self.name = name
        self.issue = issue
        self.status_code = status_code


class PayPalDeclined(PayPalRejected):
    """The buyer's funding instrument was declined at capture; the buyer may retry with another one."""


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


def _call(method: str, url: str, headers: dict | None = None, **kwargs):
    """Authenticated PayPal call; on a 401 the cached token is discarded and the call retried once.

    `headers` are merged over the auth headers (e.g. PayPal-Request-Id) and re-sent unchanged on the retry.
    """
    resp = None
    for attempt in (0, 1):
        merged = {**_auth_headers(force_refresh=bool(attempt)), **(headers or {})}
        resp = requests.request(method, url, headers=merged, timeout=10, **kwargs)
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


def get_refund(refund_id: str) -> dict:
    """GET /v2/payments/refunds/{id}: the authoritative state and amount of a refund (never trust the webhook body)."""
    try:
        resp = _call('GET', f"{_base_url()}/v2/payments/refunds/{quote(str(refund_id), safe='')}")
        resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise PayPalError(f"PayPal refund lookup failed: {exc}") from exc


def get_dispute(dispute_id: str) -> dict:
    """GET /v1/customer/disputes/{id}: the authoritative dispute record (status, outcome, disputed transactions)."""
    try:
        resp = _call('GET', f"{_base_url()}/v1/customer/disputes/{quote(str(dispute_id), safe='')}")
        resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise PayPalError(f"PayPal dispute lookup failed: {exc}") from exc


# --- Orders v2 ---------------------------------------------------------------------------------------------------

def _error_details(resp) -> tuple[str, str]:
    try:
        body = resp.json()
    except ValueError:
        return '', ''
    if not isinstance(body, dict):
        return '', ''
    details = body.get('details') or []
    issue = details[0].get('issue', '') if details and isinstance(details[0], dict) else ''
    return str(body.get('name', '')), str(issue)


def _order_json(resp, what: str) -> dict:
    """JSON of a successful answer; 4xx -> PayPalRejected (401/408/429 stay retryable PayPalError); else PayPalError."""
    status = getattr(resp, 'status_code', 200)
    if 400 <= status < 500 and status not in (401, 408, 429):
        name, issue = _error_details(resp)
        raise PayPalRejected(f"PayPal {what} rejected ({status} {name} {issue})".strip(), name=name, issue=issue, status_code=status)
    try:
        resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise PayPalError(f"PayPal {what} failed: {exc}") from exc


def _send(method: str, url: str, what: str, **kwargs):
    try:
        return _call(method, url, **kwargs)
    except requests.RequestException as exc:
        raise PayPalError(f"PayPal {what} failed: {exc}") from exc


def create_order(*, reference: str, amount, currency: str, description: str, request_id: str) -> dict:
    """
    POST /v2/checkout/orders (intent CAPTURE). `reference` goes into custom_id so the verified capture can be tied back
    to our PaymentTransaction. The amount is an exact string in the currency's minor unit (JPY: no decimals).
    `request_id` makes a retried call idempotent on PayPal's side.
    """
    currency = currency.upper()
    value = format(quantize_money(amount, currency), 'f')
    body = {
        'intent': 'CAPTURE',
        'purchase_units': [{
            'reference_id': reference,
            'custom_id': reference,
            'description': description,
            'amount': {'currency_code': currency, 'value': value},
        }],
    }
    if getattr(settings, 'PAYPAL_REQUIRE_IMMEDIATE_PAYMENT', False):
        body['payment_source'] = {'paypal': {'experience_context': {'payment_method_preference': 'IMMEDIATE_PAYMENT_REQUIRED'}}}
    resp = _send('POST', f"{_base_url()}/v2/checkout/orders", 'order creation',
                 json=body, headers={'PayPal-Request-Id': request_id})
    return _order_json(resp, 'order creation')


def get_order(order_id: str) -> dict:
    resp = _send('GET', f"{_base_url()}/v2/checkout/orders/{quote(str(order_id), safe='')}", 'order lookup')
    return _order_json(resp, 'order lookup')


def capture_order(order_id: str, *, request_id: str) -> dict:
    """
    POST /v2/checkout/orders/{id}/capture. ORDER_ALREADY_CAPTURED is success (returns the fetched order);
    INSTRUMENT_DECLINED raises PayPalDeclined so the caller can let the buyer retry.
    """
    url = f"{_base_url()}/v2/checkout/orders/{quote(str(order_id), safe='')}/capture"
    resp = _send('POST', url, 'order capture', headers={'PayPal-Request-Id': request_id})
    try:
        return _order_json(resp, 'order capture')
    except PayPalRejected as exc:
        if exc.issue == 'ORDER_ALREADY_CAPTURED':
            return get_order(order_id)
        if exc.issue == 'INSTRUMENT_DECLINED':
            raise PayPalDeclined(str(exc), name=exc.name, issue=exc.issue, status_code=exc.status_code) from exc
        raise


# Our own PayPal Business account settings hold the payment (receiving preferences / currency handling): not the buyer.
MERCHANT_SIDE_PENDING_REASONS = frozenset({
    'RECEIVING_PREFERENCE_MANDATES_MANUAL_ACTION', 'INTERNATIONAL_WITHDRAWAL',
})
# Buyer-side: PayPal is reviewing the payment, or the buyer's bank has not delivered the funds yet. Either can still fail.
RISK_BASED_PENDING_REASONS = frozenset({'PENDING_REVIEW', 'TRANSACTION_APPROVED_AWAITING_FUNDING'})


@dataclass(frozen=True)
class CaptureOutcome:
    state: str  # 'completed' | 'pending' | 'declined' | 'failed'
    reason: str = ''
    merchant_side: bool = False
    risk_based: bool = False


def extract_capture(order_json) -> dict | None:
    """The first capture of the first purchase unit, or None if the order has none."""
    try:
        return order_json['purchase_units'][0]['payments']['captures'][0]
    except (KeyError, IndexError, TypeError):
        return None


def classify_capture(capture) -> CaptureOutcome:
    """Map a PayPal capture to an outcome. Anything unrecognised is 'pending' (never 'completed')."""
    capture = capture if isinstance(capture, dict) else {}
    status = capture.get('status')
    details = capture.get('status_details')
    reason = str(details.get('reason', '')) if isinstance(details, dict) else ''
    if status == 'COMPLETED':
        return CaptureOutcome('completed')
    if status in ('DECLINED', 'DENIED'):
        return CaptureOutcome('declined', reason)
    if status == 'FAILED':
        return CaptureOutcome('failed', reason)
    if status == 'PENDING':
        return CaptureOutcome('pending', reason, reason in MERCHANT_SIDE_PENDING_REASONS, reason in RISK_BASED_PENDING_REASONS)
    return CaptureOutcome('pending', reason)
