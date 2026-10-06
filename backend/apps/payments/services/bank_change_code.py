"""
E-mailed one-time code that guards creating or changing a tutor's payout bank details (ADR-0003 precondition).

A stolen login is not enough to redirect a tutor's money: the code goes to the account's e-mail address, expires after
10 minutes, allows 5 wrong guesses, only its keyed hash is stored, and it is consumed by the save it authorises.
Not routed through `notify()`: like the password-reset mail it carries a live secret, which notification payloads must not.
"""
import hashlib
import hmac
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F

from apps.common import clock
from apps.integrations.services.email import SENT, render_html, send_email
from apps.payments.models import BankChangeChallenge

CODE_TTL = timedelta(minutes=10)
MAX_ATTEMPTS = 5


class CodeNotSent(RuntimeError):
    """The e-mail provider did not take the message; no usable code exists."""


def _digest(challenge_id, code: str) -> str:
    key = settings.SECRET_KEY.encode('utf-8')
    return hmac.new(key, f'{challenge_id}:{code}'.encode('utf-8'), hashlib.sha256).hexdigest()


def issue_code(user) -> str:
    """Create a fresh challenge (older unused ones stop working), e-mail the code and return it (tests read it here)."""
    now = clock.now()
    code = f'{secrets.randbelow(1_000_000):06d}'
    with transaction.atomic():
        BankChangeChallenge.objects.filter(user=user, used_at__isnull=True).update(used_at=now)
        challenge = BankChangeChallenge.objects.create(user=user, code_hash='', expires_at=now + CODE_TTL)
        challenge.code_hash = _digest(challenge.id, code)
        challenge.save(update_fields=['code_hash'])
    text = (f'Your Sharon ESL verification code is {code}.\n\nIt lets you save your payout bank details and expires in '
            f'10 minutes. If you did not ask for it, do not share it and change your password.')
    html = render_html('<p>Your Sharon ESL verification code is <strong>{code}</strong>.</p>'
                       '<p>It lets you save your payout bank details and expires in 10 minutes. If you did not ask for '
                       'it, do not share it and change your password.</p>', code=code)
    result = send_email(user.email, 'Your Sharon ESL verification code', html, text, idempotency_key=f'bank-code:{challenge.id}')
    if result.status != SENT:
        BankChangeChallenge.objects.filter(pk=challenge.pk).update(used_at=now)
        raise CodeNotSent('The verification e-mail could not be sent.')
    return code


def _active(user):
    now = clock.now()
    return (BankChangeChallenge.objects.select_for_update(of=('self',))
            .filter(user=user, used_at__isnull=True, expires_at__gt=now, attempts__lt=MAX_ATTEMPTS)
            .order_by('-created_at').first())


def check_code(user, code: str) -> bool:
    """True when `code` matches the newest live challenge. A wrong guess uses up one of its attempts."""
    with transaction.atomic():
        challenge = _active(user)
        if challenge is None:
            return False
        if hmac.compare_digest(challenge.code_hash, _digest(challenge.id, str(code))):
            return True
        BankChangeChallenge.objects.filter(pk=challenge.pk).update(attempts=F('attempts') + 1)
        return False


def consume_code(user) -> None:
    """Called by the save that the code authorised: the code cannot be used twice."""
    with transaction.atomic():
        challenge = _active(user)
        if challenge is not None:
            BankChangeChallenge.objects.filter(pk=challenge.pk).update(used_at=clock.now())
