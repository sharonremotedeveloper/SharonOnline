from django.db import transaction
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from .tasks import KIND_PASSWORD_RESET, KIND_VERIFY_EMAIL, send_account_email_task, send_support_inquiry_notification


def queue_account_email(user, kind: str) -> None:
    """Send after the surrounding transaction commits: no race with a rollback, no e-mail for a user that never existed."""
    user_id = str(user.pk)
    transaction.on_commit(lambda: send_account_email_task.delay(user_id, kind))


def queue_verification_email(user) -> None:
    queue_account_email(user, KIND_VERIFY_EMAIL)


def queue_password_reset_email(user) -> None:
    queue_account_email(user, KIND_PASSWORD_RESET)


def queue_support_inquiry(inquiry) -> None:
    inquiry_id = str(inquiry.pk)
    transaction.on_commit(lambda: send_support_inquiry_notification.delay(inquiry_id))


def revoke_all_sessions(user) -> int:
    """Blacklist every outstanding refresh token: a password change must end all logins (access tokens lapse within 15 min)."""
    revoked = 0
    for outstanding in OutstandingToken.objects.filter(user=user):
        _, created = BlacklistedToken.objects.get_or_create(token=outstanding)
        revoked += int(created)
    return revoked
