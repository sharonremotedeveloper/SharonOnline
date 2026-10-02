"""Single-purpose, expiring tokens for account e-mails. Links are built from settings.FRONTEND_BASE_URL, never from request data."""
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core import signing
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from .models import User

_VERIFY_SALT = 'sharon.users.verify-email'


def encode_uid(user) -> str:
    return urlsafe_base64_encode(force_bytes(user.pk))


def user_from_uid(uid):
    try:
        return User.objects.get(pk=force_str(urlsafe_base64_decode(uid)))
    except (TypeError, ValueError, OverflowError, User.DoesNotExist, UnicodeDecodeError):
        return None


# ---- password reset: Django's generator. The hash covers the password hash + last_login, so a token dies the moment it is
# used (or the password changes any other way). Lifetime = settings.PASSWORD_RESET_TIMEOUT.
def make_reset_token(user) -> str:
    return default_token_generator.make_token(user)


def check_reset_token(user, token) -> bool:
    return isinstance(token, str) and default_token_generator.check_token(user, token)


# ---- e-mail verification: signed {uid, email}, so changing the address invalidates links sent to the old one.
def make_verify_token(user) -> str:
    return signing.dumps({'u': str(user.pk), 'e': user.email.lower()}, salt=_VERIFY_SALT)


def user_from_verify_token(token):
    try:
        data = signing.loads(token, salt=_VERIFY_SALT, max_age=settings.EMAIL_VERIFY_MAX_AGE)
        user = User.objects.get(pk=data['u'])
    except (signing.BadSignature, User.DoesNotExist, KeyError, TypeError, ValueError):
        return None
    return user if user.email.lower() == data['e'] else None
