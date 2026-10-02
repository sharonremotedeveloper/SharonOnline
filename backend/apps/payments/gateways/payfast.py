"""PayFast ITN verification: signature, source IP, server-to-server postback."""
import hashlib
import hmac
import ipaddress
import logging
import socket
import time
from urllib.parse import parse_qsl, quote_plus

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

PAYFAST_HOSTS = ('www.payfast.co.za', 'sandbox.payfast.co.za', 'w1w.payfast.co.za', 'w2w.payfast.co.za')
_ip_cache = {'ips': set(), 'at': 0.0, 'ttl': 0}
IP_CACHE_SECONDS = 3600
IP_RETRY_SECONDS = 60  # when DNS fails, remember that briefly instead of re-resolving 4 hosts on every ITN


def parse_itn_body(raw_body: bytes) -> list:
    """Parse the form-encoded ITN keeping PayFast's field order (the signature depends on it)."""
    return parse_qsl(raw_body.decode('utf-8', errors='replace'), keep_blank_values=True)


def _enc(value: str) -> str:
    # PayFast signs PHP urlencode() output: spaces -> '+', and '~' -> '%7E' (Python's quote_plus leaves '~' alone).
    return quote_plus(value.strip()).replace('~', '%7E')


def build_param_string(pairs, passphrase: str = '') -> str:
    parts = [f"{k}={_enc(v)}" for k, v in pairs if k != 'signature']
    if passphrase:
        parts.append(f"passphrase={_enc(passphrase)}")
    return '&'.join(parts)


def verify_signature(pairs, passphrase: str) -> bool:
    received = dict(pairs).get('signature', '')
    if not received:
        return False
    expected = hashlib.md5(build_param_string(pairs, passphrase).encode('utf-8')).hexdigest()
    return hmac.compare_digest(expected, received.lower())


def get_valid_ips() -> set:
    now = time.time()
    if now - _ip_cache['at'] > _ip_cache['ttl']:
        ips = set()
        for host in PAYFAST_HOSTS:
            try:
                ips.update(socket.gethostbyname_ex(host)[2])
            except OSError:
                logger.warning("Could not resolve PayFast host %s", host)
        if ips:
            _ip_cache.update(ips=ips, at=now, ttl=IP_CACHE_SECONDS)
        else:
            # Keep serving the last known-good set; retry soon rather than on every request.
            _ip_cache.update(at=now, ttl=IP_RETRY_SECONDS)
    return _ip_cache['ips']


def _extra_networks():
    """Operator-configured CIDR ranges (PAYFAST_EXTRA_ALLOWED_CIDRS, comma-separated) from PayFast's published list."""
    nets = []
    for raw in getattr(settings, 'PAYFAST_EXTRA_ALLOWED_CIDRS', []) or []:
        try:
            nets.append(ipaddress.ip_network(raw.strip(), strict=False))
        except ValueError:
            logger.error("Ignoring invalid PAYFAST_EXTRA_ALLOWED_CIDRS entry %r", raw)
    return nets


def client_ip(request) -> str:
    proxies = getattr(settings, 'PAYFAST_TRUSTED_PROXY_COUNT', 0)
    xff = [p.strip() for p in request.META.get('HTTP_X_FORWARDED_FOR', '').split(',') if p.strip()]
    if proxies and len(xff) >= proxies:
        return xff[-proxies]
    return request.META.get('REMOTE_ADDR', '')


def source_ip_allowed(request) -> bool:
    if getattr(settings, 'PAYFAST_SKIP_IP_CHECK', False):
        return True
    ip = client_ip(request)
    if ip in get_valid_ips():
        return True
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in _extra_networks())


def _base_url() -> str:
    return 'https://sandbox.payfast.co.za' if settings.PAYFAST_SANDBOX else 'https://www.payfast.co.za'


def process_url() -> str:
    return f"{_base_url()}/eng/process"


def server_confirms(pairs) -> bool:
    """Post the received ITN back to PayFast; it must answer VALID."""
    body = build_param_string(pairs)  # postback excludes the signature
    try:
        resp = requests.post(f"{_base_url()}/eng/query/validate", data=body,
                             headers={'Content-Type': 'application/x-www-form-urlencoded'}, timeout=10)
    except requests.RequestException as exc:
        logger.error("PayFast validate postback failed: %s", exc)
        return False
    return resp.status_code == 200 and resp.text.strip() == 'VALID'


def build_checkout_fields(*, reference: str, amount, item_name: str, booking_id: str, notify_url: str) -> dict:
    """Signed fields the browser posts to PayFast's process URL."""
    fields = [
        ('merchant_id', settings.PAYFAST_MERCHANT_ID),
        ('merchant_key', settings.PAYFAST_MERCHANT_KEY),
        ('notify_url', notify_url),
        ('m_payment_id', reference),
        ('amount', f"{amount:.2f}"),
        ('item_name', item_name),
        ('custom_str1', booking_id),
    ]
    fields = [(k, v) for k, v in fields if v]
    signature = hashlib.md5(build_param_string(fields, settings.PAYFAST_PASSPHRASE).encode('utf-8')).hexdigest()
    return {**dict(fields), 'signature': signature}
