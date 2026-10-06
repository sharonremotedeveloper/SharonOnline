"""Standard Svix webhook verification helper (slice N3).

Verifies incoming Resend Svix webhook signatures using HMAC-SHA256,
preventing replay attacks via timestamp tolerance check.
"""
import base64
import hashlib
import hmac
import time


class WebhookVerificationError(Exception):
    """Raised when an incoming webhook fails signature or timestamp validation."""


def verify_svix_signature(payload: bytes, headers: dict, secret: str, tolerance_seconds: int = 300) -> bool:
    """
    Verify Svix webhook signature using standard library HMAC-SHA256.
    
    Required headers:
    - svix-id: unique message id
    - svix-timestamp: epoch timestamp
    - svix-signature: space-separated 'v1,<base64>' signatures
    """
    if not secret:
        raise WebhookVerificationError('Webhook secret is not configured.')

    # Check both normal and Django HTTP_ header names
    msg_id = headers.get('svix-id') or headers.get('HTTP_SVIX_ID')
    msg_timestamp = headers.get('svix-timestamp') or headers.get('HTTP_SVIX_TIMESTAMP')
    msg_signature = headers.get('svix-signature') or headers.get('HTTP_SVIX_SIGNATURE')

    if not (msg_id and msg_timestamp and msg_signature):
        raise WebhookVerificationError('Missing required Svix headers.')

    try:
        ts = int(msg_timestamp)
    except ValueError as exc:
        raise WebhookVerificationError('Invalid timestamp header.') from exc

    now = int(time.time())
    if abs(now - ts) > tolerance_seconds:
        raise WebhookVerificationError('Webhook timestamp is outside tolerance.')

    clean_secret = secret
    if clean_secret.startswith('whsec_'):
        clean_secret = clean_secret[6:]

    try:
        key = base64.b64decode(clean_secret)
    except Exception as exc:
        raise WebhookVerificationError(f'Invalid base64 webhook secret: {exc}') from exc

    to_sign = f'{msg_id}.{msg_timestamp}.'.encode('utf-8') + payload
    expected_mac = hmac.new(key, to_sign, hashlib.sha256).digest()
    expected_sig = base64.b64encode(expected_mac).decode('utf-8')

    passed = False
    for item in msg_signature.split(' '):
        parts = item.split(',', 1)
        if len(parts) == 2 and parts[0] == 'v1':
            if hmac.compare_digest(parts[1], expected_sig):
                passed = True
                break

    if not passed:
        raise WebhookVerificationError('Svix signature verification failed.')

    return True
