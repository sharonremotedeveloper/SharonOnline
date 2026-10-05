"""Slice N1a: retention of the notification table (plan §3.2: read in-app 180 days, e-mail-only 90 days)."""
from datetime import timedelta

import pytest
from django.core.cache import cache

import factories as f
from apps.notifications import retention, tasks
from apps.notifications.models import Notification

ES = Notification.EmailState


def row(key, *, now, age_days, in_app=True, read_days_ago=None, state=ES.SENT):
    n = Notification.objects.create(user=f.make_student(), kind='sample_lesson_notice', idempotency_key=key,
                                    in_app=in_app, email_state=state)
    read_at = now - timedelta(days=read_days_ago) if read_days_ago is not None else None
    Notification.objects.filter(pk=n.pk).update(created_at=now - timedelta(days=age_days), read_at=read_at)
    return n


@pytest.mark.django_db
class TestPurge:
    def test_read_in_app_items_after_180_days(self, frozen_clock):
        now = frozen_clock.now
        old_read = row('a', now=now, age_days=400, read_days_ago=181)
        recent_read = row('b', now=now, age_days=400, read_days_ago=179)
        old_unread = row('c', now=now, age_days=400)
        result = retention.purge(now)
        remaining = set(Notification.objects.values_list('pk', flat=True))
        assert old_read.pk not in remaining and {recent_read.pk, old_unread.pk} <= remaining
        assert result['in_app_read'] == 1

    def test_email_only_rows_after_90_days_when_finished(self, frozen_clock):
        now = frozen_clock.now
        old_sent = row('a', now=now, age_days=91, in_app=False)
        old_failed = row('b', now=now, age_days=91, in_app=False, state=ES.FAILED)
        young = row('c', now=now, age_days=89, in_app=False)
        unfinished = row('d', now=now, age_days=91, in_app=False, state=ES.RETRYABLE)
        result = retention.purge(now)
        remaining = set(Notification.objects.values_list('pk', flat=True))
        assert old_sent.pk not in remaining and old_failed.pk not in remaining
        assert {young.pk, unfinished.pk} <= remaining
        assert result['email_only'] == 2

    def test_deletes_in_batches(self, frozen_clock, monkeypatch):
        monkeypatch.setattr(retention, 'BATCH_SIZE', 2)
        for i in range(5):
            row(f'k{i}', now=frozen_clock.now, age_days=200, in_app=False)
        assert retention.purge(frozen_clock.now)['email_only'] == 5
        assert not Notification.objects.exists()

    def test_idempotent(self, frozen_clock):
        row('a', now=frozen_clock.now, age_days=200, in_app=False)
        retention.purge(frozen_clock.now)
        assert retention.purge(frozen_clock.now) == {'in_app_read': 0, 'email_only': 0}

    def test_task_runs_under_a_distributed_lock(self, frozen_clock):
        row('a', now=frozen_clock.now, age_days=200, in_app=False)
        cache.add('lock:beat:purge_notifications', 'peer', timeout=60)
        assert tasks.purge_notifications_task()['status'] == 'skipped'
        assert Notification.objects.count() == 1
        cache.delete('lock:beat:purge_notifications')
        assert tasks.purge_notifications_task() == {'in_app_read': 0, 'email_only': 1}
