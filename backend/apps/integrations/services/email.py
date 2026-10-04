"""The one place that sends transactional e-mail (slice N1c; contract in docs/NOTIFICATIONS.md).

`send_email()` never raises for a provider problem: it returns an `EmailResult` whose `status` tells the caller what to do
(`sent`, `retryable` = try again later, `in_flight` = Resend is still holding this idempotency key, `failed` = permanent).
It raises only for a programming error: a header-injection attempt, an empty recipient or a bad idempotency key
(`InvalidEmailError`), or an unknown `EMAIL_BACKEND_MODE` (`ImproperlyConfigured`). In console mode (never production) the
Django mail backend's own exceptions propagate unchanged (e.g. `ConnectionRefusedError` if no console/locmem backend is set).

Logs carry ids, status codes and error types only: never addresses, subjects, bodies, provider messages or exception text.
"""
import base64
import logging
import re
import uuid
from dataclasses import dataclass
from typing import Iterable, Mapping, Optional, Sequence, Union

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMultiAlternatives
from django.utils.html import format_html

logger = logging.getLogger(__name__)

RESEND_EMAILS_URL = 'https://api.resend.com/emails'
SENT, RETRYABLE, FAILED, IN_FLIGHT = 'sent', 'retryable', 'failed', 'in_flight'
MODE_RESEND, MODE_CONSOLE = 'resend', 'console'
MAX_IDEMPOTENCY_KEY_LENGTH = 256          # Resend's documented limit
MAX_RETRY_AFTER_SECONDS = 3600
_LINE_BREAK = re.compile(r'[\r\n]')
_ADDRESS_SEPARATOR = re.compile(r'[,;]')                         # one list item = one address
_PRINTABLE_ASCII = re.compile(r'[\x20-\x7e]+')
_SAFE_PROVIDER_NAME = re.compile(r'[a-z][a-z0-9_]{0,63}')       # used with fullmatch (no trailing-newline loophole)
_SAFE_MESSAGE_ID = re.compile(r'[A-Za-z0-9_.:-]{1,128}')


class InvalidEmailError(ValueError):
    """The caller passed something that must never reach a mail header (CR/LF, empty recipient, bad key)."""


@dataclass(frozen=True)
class Attachment:
    filename: str
    content: bytes
    content_type: str = 'application/octet-stream'


@dataclass(frozen=True)
class EmailResult:
    status: str                               # sent | retryable | failed | in_flight
    provider_message_id: str = ''
    error_code: str = ''                      # short and PII-free, e.g. 'http_422:validation_error', 'timeout'
    http_status: Optional[int] = None
    retry_after_seconds: Optional[int] = None  # from Retry-After on 429/503 (integer seconds, capped); else None

    @property
    def ok(self) -> bool:
        return self.status == SENT


def render_html(template: str, **values) -> str:
    """Fill `{name}` placeholders in a trusted HTML template; every value is HTML-escaped (hostile names stay text).

    Returns a `SafeString` (a `str`): already escaped, so a Django template will not escape it twice.
    """
    return format_html(template, **values)


def send_email(to: Union[str, Sequence[str]], subject: str, html: str, text: str = '', *,
               idempotency_key: Optional[str] = None, attachments: Iterable[Attachment] = (),
               tags: Optional[Mapping[str, str]] = None, reply_to: Optional[str] = None) -> EmailResult:
    recipients = _validated(to, subject, reply_to, idempotency_key)
    attachments = tuple(attachments)
    mode = settings.EMAIL_BACKEND_MODE
    if mode == MODE_CONSOLE:
        return _send_console(recipients, subject, html, text, attachments, reply_to)
    if mode != MODE_RESEND:
        raise ImproperlyConfigured(f"EMAIL_BACKEND_MODE must be '{MODE_RESEND}' or '{MODE_CONSOLE}'")
    api_key = settings.RESEND_API_KEY
    if not api_key:
        logger.error('email.failed error_code=not_configured (EMAIL_BACKEND_MODE=resend without RESEND_API_KEY)')
        return EmailResult(FAILED, error_code='not_configured')
    payload = _payload(recipients, subject, html, text, attachments, tags, reply_to)
    headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
    if idempotency_key:
        headers['Idempotency-Key'] = idempotency_key
    return _post(payload, headers, has_key=bool(idempotency_key))


def _validated(to, subject, reply_to, idempotency_key) -> list:
    recipients = [to] if isinstance(to, str) else list(to)
    if not recipients or any(not isinstance(r, str) or not r.strip() for r in recipients):
        raise InvalidEmailError('a recipient address is required')
    if any(_ADDRESS_SEPARATOR.search(r) for r in (*recipients, reply_to or '')):
        raise InvalidEmailError('pass several recipients as a list, never as one comma/semicolon-separated string')
    for value in (*recipients, subject, reply_to or '', idempotency_key or ''):
        if _LINE_BREAK.search(value):
            raise InvalidEmailError('line breaks are not allowed in e-mail headers')
    if idempotency_key is not None and not (0 < len(idempotency_key) <= MAX_IDEMPOTENCY_KEY_LENGTH):
        raise InvalidEmailError(f'idempotency_key must be 1..{MAX_IDEMPOTENCY_KEY_LENGTH} characters')
    if idempotency_key is not None and not _PRINTABLE_ASCII.fullmatch(idempotency_key):
        raise InvalidEmailError('idempotency_key must be printable ASCII (it is sent as an HTTP header)')
    return [r.strip() for r in recipients]


def _payload(recipients, subject, html, text, attachments, tags, reply_to) -> dict:
    payload = {'from': settings.DEFAULT_FROM_EMAIL, 'to': recipients, 'subject': subject, 'html': html}
    if text:
        payload['text'] = text
    if reply_to:
        payload['reply_to'] = [reply_to]
    if tags:
        payload['tags'] = [{'name': str(name), 'value': str(value)} for name, value in tags.items()]
    if attachments:
        payload['attachments'] = [{'filename': a.filename, 'content': base64.b64encode(a.content).decode('ascii'),
                                   'content_type': a.content_type} for a in attachments]
    return payload


def _post(payload: dict, headers: dict, *, has_key: bool) -> EmailResult:
    try:
        response = requests.post(RESEND_EMAILS_URL, json=payload, headers=headers,
                                 timeout=settings.RESEND_TIMEOUT_SECONDS)
    except requests.Timeout as exc:
        return _logged(EmailResult(RETRYABLE, error_code='timeout'), exc_type=type(exc).__name__)
    except requests.ConnectionError as exc:
        return _logged(EmailResult(RETRYABLE, error_code='connection_error'), exc_type=type(exc).__name__)
    except requests.RequestException as exc:
        return _logged(EmailResult(RETRYABLE, error_code='request_error'), exc_type=type(exc).__name__)
    return _logged(_classify(response), idempotent=has_key)


def _classify(response) -> EmailResult:
    status_code = response.status_code
    body = _json_or_empty(response)
    if 200 <= status_code < 300:
        message_id = str(body.get('id') or '')
        return EmailResult(SENT, provider_message_id=message_id if _SAFE_MESSAGE_ID.fullmatch(message_id) else '',
                           http_status=status_code)
    name = str(body.get('name') or '')
    code = f'http_{status_code}:{name}' if _SAFE_PROVIDER_NAME.fullmatch(name) else f'http_{status_code}'
    if status_code == 409:                     # same key, different payload or a concurrent request: retry later
        return EmailResult(IN_FLIGHT, error_code=code, http_status=status_code)
    if status_code == 429 or status_code >= 500:
        retry_after = _retry_after(response) if status_code in (429, 503) else None
        return EmailResult(RETRYABLE, error_code=code, http_status=status_code, retry_after_seconds=retry_after)
    return EmailResult(FAILED, error_code=code, http_status=status_code)


def _retry_after(response) -> Optional[int]:
    """Retry-After as integer seconds, capped; an HTTP-date or anything else is ignored (the caller's backoff applies)."""
    value = response.headers.get('Retry-After') if isinstance(response.headers, Mapping) else None
    if not isinstance(value, str) or not value.strip().isdigit():
        return None
    return min(int(value.strip()), MAX_RETRY_AFTER_SECONDS)


def _json_or_empty(response) -> dict:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _logged(result: EmailResult, *, exc_type: str = '', idempotent: bool = False) -> EmailResult:
    if result.ok and not result.provider_message_id:
        logger.warning('email.sent without a provider id http_status=%s idempotent=%s', result.http_status, idempotent)
    elif result.ok:
        logger.info('email.sent provider_id=%s idempotent=%s', result.provider_message_id, idempotent)
    else:
        logger.warning('email.%s error_code=%s http_status=%s exc_type=%s', result.status, result.error_code,
                       result.http_status, exc_type or '-')
    return result


def _send_console(recipients, subject, html, text, attachments, reply_to) -> EmailResult:
    """Outside production only (the boot guard refuses this mode): hand the message to Django's mail backend.

    `EMAIL_BACKEND` is the console backend only in `settings/local.py` (tests: locmem). Backend errors are not caught.
    """
    message = EmailMultiAlternatives(subject=subject, body=text, from_email=settings.DEFAULT_FROM_EMAIL,
                                     to=recipients, reply_to=[reply_to] if reply_to else None)
    message.attach_alternative(html, 'text/html')
    for attachment in attachments:
        message.attach(attachment.filename, attachment.content, attachment.content_type)
    message.send(fail_silently=False)
    message_id = f'console:{uuid.uuid4().hex}'
    logger.info('email.console provider_id=%s', message_id)
    return EmailResult(SENT, provider_message_id=message_id)
