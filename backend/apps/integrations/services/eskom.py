import re
from datetime import datetime

import requests
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime


class EskomProviderError(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


class EskomQuotaError(EskomProviderError):
    pass


def _aware(value):
    parsed = value if isinstance(value, datetime) else parse_datetime(str(value or ''))
    if parsed is None:
        raise EskomProviderError('invalid_payload', 'Provider returned an invalid outage timestamp.')
    return timezone.make_aware(parsed) if timezone.is_naive(parsed) else parsed


def _stage(value):
    match = re.search(r'\d+', str(value or '0'))
    stage = int(match.group()) if match else 0
    if not 0 <= stage <= 8:
        raise EskomProviderError('invalid_payload', 'Provider returned an invalid stage.')
    return stage


class EskomSePushClient:
    """Small injectable client for the EskomSePush Business API."""

    def __init__(self, api_key=None, base_url=None, timeout=None, session=None):
        self.api_key = api_key if api_key is not None else settings.ESKOMSEPUSH_API_KEY
        self.base_url = (base_url or settings.ESKOMSEPUSH_BASE_URL).rstrip('/')
        self.timeout = timeout or settings.ESKOMSEPUSH_TIMEOUT_SECONDS
        self.session = session or requests.Session()

    def _get(self, path, **params):
        if not self.api_key:
            raise EskomProviderError('not_configured', 'EskomSePush is not configured.')
        try:
            response = self.session.get(
                f'{self.base_url}/{path.lstrip("/")}', params=params,
                headers={'token': self.api_key}, timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise EskomProviderError('timeout', str(exc)) from exc
        if response.status_code == 429:
            raise EskomQuotaError('quota', 'EskomSePush quota is exhausted.')
        if response.status_code >= 400:
            raise EskomProviderError(f'http_{response.status_code}', 'EskomSePush request failed.')
        try:
            payload = response.json()
        except ValueError as exc:
            raise EskomProviderError('invalid_payload', 'EskomSePush returned invalid JSON.') from exc
        if not isinstance(payload, dict):
            raise EskomProviderError('invalid_payload', 'EskomSePush returned an invalid object.')
        return payload

    def fetch_area_status(self, area_id):
        area = self._get('area', id=area_id)
        national = self._get('status')
        info = area.get('info') if isinstance(area.get('info'), dict) else {}
        status = national.get('status') if isinstance(national.get('status'), dict) else {}
        eskom = status.get('eskom') if isinstance(status.get('eskom'), dict) else {}
        events = []
        for event in area.get('events') or []:
            if not isinstance(event, dict):
                continue
            events.append({
                'start': _aware(event.get('start')).isoformat(),
                'end': _aware(event.get('end')).isoformat(),
                'note': str(event.get('note') or '')[:255],
            })
        return {
            'area_id': area_id,
            'area_name': str(info.get('name') or area_id)[:255],
            'stage': _stage(eskom.get('stage')),
            'outages': events,
            'retrieved_at': timezone.now(),
        }


eskom_client = EskomSePushClient()

