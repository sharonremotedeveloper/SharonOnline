import logging
from urllib.parse import urlencode

from celery import shared_task
from django.conf import settings
from django.utils.html import escape

from apps.integrations.email import EmailDeliveryError, send_email
from .models import User
from .tokens import encode_uid, make_reset_token, make_verify_token

logger = logging.getLogger(__name__)

KIND_PASSWORD_RESET = 'password_reset'
KIND_VERIFY_EMAIL = 'verify_email'


def _link(path: str, **params) -> str:
    return f"{settings.FRONTEND_BASE_URL.rstrip('/')}{path}?{urlencode(params)}"


def _button(url: str, label: str) -> str:
    return (f'<p><a href="{escape(url)}" style="background-color:#0D4440;color:#fff;padding:10px 20px;'
            f'text-decoration:none;border-radius:6px;">{escape(label)}</a></p>'
            f'<p style="font-size:12px;color:#666">Or paste this link into your browser:<br>{escape(url)}</p>')


def build_message(user: User, kind: str):
    """(subject, html, text) for one account e-mail. The token is minted here, at send time, so it never sits in the broker."""
    name = escape(user.first_name or user.username)
    if kind == KIND_PASSWORD_RESET:
        url = _link('/reset-password', uid=encode_uid(user), token=make_reset_token(user))
        minutes = settings.PASSWORD_RESET_TIMEOUT // 60
        return (
            'Reset your Sharon Online password',
            f'<h2>Reset your password</h2><p>Hi {name},</p><p>We received a request to reset your password. '
            f'This link works once and expires in {minutes} minutes.</p>{_button(url, "Choose a new password")}'
            '<p>If you did not ask for this, you can ignore this e-mail - your password has not changed.</p>',
            f'Reset your Sharon Online password (valid once, {minutes} minutes):\n{url}\n\nIf you did not ask for this, ignore this e-mail.',
        )
    if kind == KIND_VERIFY_EMAIL:
        url = _link('/verify-email', token=make_verify_token(user))
        return (
            'Confirm your e-mail for Sharon Online',
            f'<h2>Confirm your e-mail</h2><p>Hi {name},</p><p>Please confirm this address belongs to you.</p>'
            f'{_button(url, "Confirm e-mail")}<p>If you did not create an account, ignore this e-mail.</p>',
            f'Confirm your e-mail for Sharon Online:\n{url}\n\nIf you did not create an account, ignore this e-mail.',
        )
    raise ValueError(f'unknown account e-mail kind: {kind}')


@shared_task(bind=True, autoretry_for=(EmailDeliveryError,), retry_backoff=30, retry_backoff_max=900, max_retries=5)
def send_account_email_task(self, user_id: str, kind: str):
    user = User.objects.filter(pk=user_id, is_active=True).first()
    if user is None or not user.email:
        return
    if kind == KIND_VERIFY_EMAIL and user.email_verified:
        return
    subject, html, text = build_message(user, kind)
    send_email(user.email, subject, html, text)
