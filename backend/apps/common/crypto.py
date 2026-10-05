"""Versioned Fernet keyring helpers for integration secrets."""

import json
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _keyring():
    value = getattr(settings, 'INTEGRATION_DATA_KEYS', {}) or {}
    if isinstance(value, str):
        value = json.loads(value)
    return {str(k): Fernet(str(v).encode('ascii')) for k, v in value.items()}


def encrypt_integration_secret(value: str) -> str:
    if not value:
        raise ValueError('Cannot encrypt an empty integration secret.')
    active = str(getattr(settings, 'INTEGRATION_DATA_ACTIVE_KEY', '') or '')
    keys = _keyring()
    if not active or active not in keys:
        raise RuntimeError('INTEGRATION_DATA_KEYS is not configured.')
    token = keys[active].encrypt(value.encode('utf-8')).decode('ascii')
    return f'{active}:{token}'


def decrypt_integration_secret(value: str) -> str:
    try:
        version, token = str(value).split(':', 1)
        return _keyring()[version].decrypt(token.encode('ascii')).decode('utf-8')
    except (ValueError, KeyError, InvalidToken, UnicodeError) as exc:
        raise ValueError('Invalid integration secret.') from exc
