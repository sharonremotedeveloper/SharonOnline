import json

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class PayoutDataError(Exception):
    pass


def _keyring():
    keys = getattr(settings, 'PAYOUT_DATA_KEYS', {})
    active = getattr(settings, 'PAYOUT_DATA_ACTIVE_KEY', '')
    if not isinstance(keys, dict) or not active or active not in keys:
        raise ImproperlyConfigured('PAYOUT_DATA_KEYS must contain PAYOUT_DATA_ACTIVE_KEY before payout data can be stored.')
    return active, keys


def encrypt_payout_payload(payload: dict) -> tuple[str, str]:
    active, keys = _keyring()
    try:
        token = Fernet(keys[active].encode('ascii')).encrypt(
            json.dumps(payload, separators=(',', ':'), sort_keys=True).encode('utf-8')
        )
    except (ValueError, UnicodeError) as exc:
        raise ImproperlyConfigured('The active payout data key is not a valid Fernet key.') from exc
    return token.decode('ascii'), active


def decrypt_payout_payload(ciphertext: str, key_version: str) -> dict:
    _, keys = _keyring()
    key = keys.get(key_version)
    if key is None:
        raise PayoutDataError(f'Payout data key version {key_version!r} is unavailable.')
    try:
        data = Fernet(key.encode('ascii')).decrypt(ciphertext.encode('ascii'))
        payload = json.loads(data.decode('utf-8'))
    except (InvalidToken, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise PayoutDataError('Payout account data could not be decrypted.') from exc
    if not isinstance(payload, dict):
        raise PayoutDataError('Payout account payload is invalid.')
    return payload
