"""Retention of the notification table (slice N1a, plan §3.2).

* Read in-app items: deleted 180 days after they were read. Unread items stay (DSR / erasure rules are task 14.3).
* E-mail-only rows (`in_app=False`): deleted 90 days after creation once their e-mail is finished
  (sent / failed / skipped / bounced); rows still pending, retryable or sending are never deleted.

The plan's "anonymised key row for 25 h" protects Resend's 24 h idempotency window. Every row deleted here is at least
90 days old, so its key left Resend's window long ago and a tombstone would protect nothing: plain batched deletion is
the documented equivalent (docs/NOTIFICATIONS.md §2.5).
"""
from datetime import timedelta

from django.db.models import Q

from apps.notifications.models import Notification

ES = Notification.EmailState
IN_APP_READ_DAYS = 180
EMAIL_ONLY_DAYS = 90
BATCH_SIZE = 1000
FINISHED = (ES.SENT, ES.FAILED, ES.SKIPPED, ES.BOUNCED)


def purge(now) -> dict:
    read_q = Q(in_app=True, read_at__isnull=False, read_at__lt=now - timedelta(days=IN_APP_READ_DAYS))
    email_only_q = Q(in_app=False, created_at__lt=now - timedelta(days=EMAIL_ONLY_DAYS), email_state__in=FINISHED)
    return {'in_app_read': _delete_in_batches(read_q), 'email_only': _delete_in_batches(email_only_q)}


def _delete_in_batches(condition) -> int:
    total = 0
    while True:
        ids = list(Notification.objects.filter(condition).values_list('pk', flat=True)[:BATCH_SIZE])
        if not ids:
            return total
        Notification.objects.filter(pk__in=ids).delete()
        total += len(ids)
