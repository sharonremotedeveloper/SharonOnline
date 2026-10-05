"""Slice N1a: e-mail delivery state machine (plan §3.2, docs/adr/ADR-0002-notification-delivery.md).

CAS claim pending|retryable(due) -> sending with a 15-minute lease, the persisted bytes re-sent under the notification key,
EmailResult mapping, jittered backoff honouring retry_after, attempts cap, 20 h resend refusal, staff alerts without
recursion, the 2-minute sweep.
"""
import json
import logging
import threading
from datetime import timedelta

import pytest
from django.db import connection

import factories as f
from apps.integrations.services import email as email_service
from apps.integrations.services.email import EmailResult
from apps.notifications import delivery, tasks
from apps.notifications.models import Notification
from test_send_email import FakeResponse

ES = Notification.EmailState


def make_row(user=None, *, key='key:1', state=ES.PENDING, kind='sample_lesson_notice', **fields):
    user = user or f.make_student()
    data = dict(user=user, kind=kind, idempotency_key=key, title='Title', body='Body', email_state=state,
                rendered_subject='Subject line', rendered_html='<p>Hello &lt;b&gt;</p>', rendered_text='Hello')
    data.update(fields)
    return Notification.objects.create(**data)


@pytest.fixture
def sender(monkeypatch):
    """Replace send_email; `.results` is consumed in order (default: sent)."""
    class Sender:
        def __init__(self):
            self.calls, self.results = [], []

        def __call__(self, to, subject, html, text='', **kwargs):
            self.calls.append(dict(to=to, subject=subject, html=html, text=text, **kwargs))
            return self.results.pop(0) if self.results else EmailResult('sent', provider_message_id='msg_1')

    fake = Sender()
    monkeypatch.setattr(email_service, 'send_email', fake)
    return fake


@pytest.fixture
def enqueued(monkeypatch):
    calls = []
    monkeypatch.setattr(tasks.deliver_notification_task, 'delay', lambda nid: calls.append(nid))
    return calls


# ====================================================================== claim (CAS + lease)
@pytest.mark.django_db
class TestClaim:
    def test_pending_is_claimed_once(self, frozen_clock):
        n = make_row()
        assert delivery.claim(n.pk, frozen_clock.now) == frozen_clock.now
        assert delivery.claim(n.pk, frozen_clock.now) is None
        n.refresh_from_db()
        assert (n.email_state, n.email_attempts, n.email_claimed_at) == (ES.SENDING, 1, frozen_clock.now)
        assert n.email_first_attempt_at == frozen_clock.now

    def test_lease_expires_after_15_minutes(self, frozen_clock):
        n = make_row()
        first = delivery.claim(n.pk, frozen_clock.now)
        frozen_clock.advance(minutes=14, seconds=59)
        assert delivery.claim(n.pk, frozen_clock.now) is None
        frozen_clock.advance(seconds=2)
        second = delivery.claim(n.pk, frozen_clock.now)
        assert second is not None and second != first
        n.refresh_from_db()
        assert n.email_attempts == 2 and n.email_first_attempt_at == first

    def test_retryable_only_when_due(self, frozen_clock):
        n = make_row(state=ES.RETRYABLE, email_next_attempt_at=frozen_clock.now + timedelta(seconds=30))
        assert delivery.claim(n.pk, frozen_clock.now) is None
        frozen_clock.advance(seconds=30)
        assert delivery.claim(n.pk, frozen_clock.now) is not None

    @pytest.mark.parametrize('state', [ES.SENT, ES.FAILED, ES.SKIPPED, ES.BOUNCED])
    def test_terminal_rows_are_never_claimed(self, frozen_clock, state):
        n = make_row(state=state)
        assert delivery.claim(n.pk, frozen_clock.now) is None


# ====================================================================== deliver: result mapping
@pytest.mark.django_db
class TestDeliver:
    def test_sent(self, sender, frozen_clock):
        n = make_row()
        assert delivery.deliver(n.pk) == 'sent'
        n.refresh_from_db()
        assert (n.email_state, n.provider_message_id, n.email_sent_at, n.email_last_error) == (
            ES.SENT, 'msg_1', frozen_clock.now, '')
        call = sender.calls[0]
        assert call['to'] == n.user.email and call['idempotency_key'] == 'key:1'
        assert (call['subject'], call['html'], call['text']) == ('Subject line', '<p>Hello &lt;b&gt;</p>', 'Hello')

    def test_a_sent_row_is_not_sent_again(self, sender):
        n = make_row()
        delivery.deliver(n.pk)
        assert delivery.deliver(n.pk) == 'not_claimed'
        assert len(sender.calls) == 1

    @pytest.mark.parametrize('status', ['retryable', 'in_flight'])
    def test_retryable_and_in_flight_back_off(self, sender, frozen_clock, status):
        sender.results.append(EmailResult(status, error_code='http_409' if status == 'in_flight' else 'timeout'))
        n = make_row()
        assert delivery.deliver(n.pk) == 'retryable'
        n.refresh_from_db()
        assert n.email_state == ES.RETRYABLE
        assert n.email_last_error == ('http_409' if status == 'in_flight' else 'timeout')
        wait = (n.email_next_attempt_at - frozen_clock.now).total_seconds()
        assert 48 <= wait <= 72

    def test_retry_after_is_honoured(self, sender, frozen_clock):
        sender.results.append(EmailResult('retryable', error_code='http_429', http_status=429, retry_after_seconds=900))
        n = make_row()
        delivery.deliver(n.pk)
        n.refresh_from_db()
        assert (n.email_next_attempt_at - frozen_clock.now).total_seconds() >= 900

    def test_permanent_failure_is_terminal_and_alerts_staff(self, sender):
        admin = f.make_admin()
        sender.results.append(EmailResult('failed', error_code='http_422:validation_error', http_status=422))
        n = make_row()
        assert delivery.deliver(n.pk) == 'failed'
        n.refresh_from_db()
        assert (n.email_state, n.email_last_error) == (ES.FAILED, 'http_422:validation_error')
        alert = Notification.objects.get(user=admin, kind='admin_alert')
        assert alert.payload['notification_id'] == str(n.pk) and alert.payload['alert'] == 'notification_failed'

    def test_attempts_cap_then_failed_and_alert(self, sender, settings, frozen_clock):
        settings.NOTIFICATION_MAX_ATTEMPTS = 8
        admin = f.make_admin()
        n = make_row(state=ES.RETRYABLE, email_attempts=7, email_first_attempt_at=frozen_clock.now - timedelta(hours=2))
        sender.results.append(EmailResult('retryable', error_code='http_503'))
        assert delivery.deliver(n.pk) == 'failed'
        n.refresh_from_db()
        assert (n.email_state, n.email_attempts) == (ES.FAILED, 8)
        assert n.email_last_error.startswith('attempts_exhausted')
        assert Notification.objects.filter(user=admin, kind='admin_alert').count() == 1

    def test_below_the_cap_keeps_retrying(self, sender, settings, frozen_clock):
        settings.NOTIFICATION_MAX_ATTEMPTS = 8
        n = make_row(state=ES.RETRYABLE, email_attempts=6, email_first_attempt_at=frozen_clock.now - timedelta(hours=2))
        sender.results.append(EmailResult('retryable', error_code='http_503'))
        assert delivery.deliver(n.pk) == 'retryable'

    def test_failed_admin_alert_never_alerts_again(self, sender):
        admin = f.make_admin()
        sender.results.append(EmailResult('failed', error_code='http_422'))
        n = make_row(admin, kind='admin_alert', payload={'alert': 'notification_failed'})
        assert delivery.deliver(n.pk) == 'failed'
        assert Notification.objects.filter(kind='admin_alert').count() == 1

    def test_no_resend_after_20_hours_without_review(self, sender, frozen_clock):
        admin = f.make_admin()
        n = make_row(state=ES.RETRYABLE, email_attempts=2,
                     email_first_attempt_at=frozen_clock.now - timedelta(hours=20, seconds=1))
        assert delivery.deliver(n.pk) == 'failed'
        n.refresh_from_db()
        assert (n.email_state, n.email_last_error) == (ES.FAILED, 'stale_needs_review')
        assert sender.calls == []
        assert Notification.objects.filter(user=admin, kind='admin_alert').count() == 1

    def test_just_under_20_hours_still_resends(self, sender, frozen_clock):
        n = make_row(state=ES.RETRYABLE, email_attempts=2,
                     email_first_attempt_at=frozen_clock.now - timedelta(hours=19, minutes=59))
        assert delivery.deliver(n.pk) == 'sent'

    def test_a_first_attempt_after_a_long_outage_is_allowed(self, sender, frozen_clock):
        """Never tried = the key never reached Resend: sending is safe however old the row is."""
        n = make_row()
        Notification.objects.filter(pk=n.pk).update(created_at=frozen_clock.now - timedelta(hours=30))
        assert delivery.deliver(n.pk) == 'sent'

    def test_missing_address_fails_without_calling_the_provider(self, sender):
        user = f.make_student(email='')
        n = make_row(user)
        assert delivery.deliver(n.pk) == 'failed'
        n.refresh_from_db()
        assert n.email_last_error == 'no_address' and sender.calls == []

    def test_invalid_address_fails(self):
        user = f.make_student(email='a@b.test, c@d.test')
        n = make_row(user)
        assert delivery.deliver(n.pk) == 'failed'
        n.refresh_from_db()
        assert n.email_last_error == 'invalid_address'

    def test_a_late_result_after_the_lease_was_taken_over_is_discarded(self, sender, frozen_clock, monkeypatch):
        n = make_row()

        def slow_send(to, subject, html, text='', **kwargs):
            frozen_clock.advance(minutes=16)
            assert delivery.claim(n.pk, frozen_clock.now) is not None     # another worker takes over
            return EmailResult('sent', provider_message_id='msg_late')

        monkeypatch.setattr(email_service, 'send_email', slow_send)
        assert delivery.deliver(n.pk) == 'revoked'
        n.refresh_from_db()
        assert (n.email_state, n.email_attempts, n.provider_message_id) == (ES.SENDING, 2, '')

    def test_logs_carry_ids_only(self, sender, caplog):
        sender.results.append(EmailResult('failed', error_code='http_422'))
        n = make_row()
        with caplog.at_level(logging.INFO):
            delivery.deliver(n.pk)
        assert str(n.pk) in caplog.text
        assert n.user.email not in caplog.text and 'Subject line' not in caplog.text


# ====================================================================== real sender: same bytes, same key
@pytest.mark.django_db
class TestResendIdempotency:
    def test_retry_resends_byte_identical_payload_under_the_same_key(self, resend, frozen_clock):
        n = make_row()
        resend.response = FakeResponse(503, {'name': 'service_unavailable'})
        assert delivery.deliver(n.pk) == 'retryable'
        frozen_clock.advance(hours=1)
        resend.response = FakeResponse(200, {'id': 'msg_ok'})
        assert delivery.deliver(n.pk) == 'sent'
        first, second = resend.calls
        assert json.dumps(first.json, sort_keys=True) == json.dumps(second.json, sort_keys=True)
        assert first.headers['Idempotency-Key'] == second.headers['Idempotency-Key'] == 'key:1'
        n.refresh_from_db()
        assert n.provider_message_id == 'msg_ok'

    def test_409_is_in_flight_and_retried_later(self, resend):
        n = make_row()
        resend.response = FakeResponse(409, {'name': 'concurrent_idempotent_requests'})
        assert delivery.deliver(n.pk) == 'retryable'
        n.refresh_from_db()
        assert n.email_state == ES.RETRYABLE and n.email_last_error.startswith('http_409')


# ====================================================================== backoff
class TestBackoff:
    def test_first_retry_about_a_minute_with_jitter(self, settings):
        settings.NOTIFICATION_RETRY_SECONDS = 60
        samples = {delivery.backoff_seconds(1) for _ in range(200)}
        assert min(samples) >= 48 and max(samples) <= 72 and len(samples) > 1

    def test_doubles_and_is_capped(self, settings):
        settings.NOTIFICATION_RETRY_SECONDS = 60
        settings.NOTIFICATION_RETRY_MAX_SECONDS = 3600
        assert 96 <= delivery.backoff_seconds(2) <= 144
        assert all(delivery.backoff_seconds(30) <= 3600 for _ in range(50))

    def test_retry_after_is_a_floor(self, settings):
        settings.NOTIFICATION_RETRY_SECONDS = 60
        assert delivery.backoff_seconds(1, 900) >= 900


# ====================================================================== sweep
@pytest.mark.django_db
class TestSweep:
    def test_picks_due_rows_only(self, frozen_clock, enqueued):
        now = frozen_clock.now
        old_pending = make_row(key='a')
        young_pending = make_row(key='b')
        due_retry = make_row(key='c', state=ES.RETRYABLE, email_next_attempt_at=now - timedelta(seconds=1))
        later_retry = make_row(key='d', state=ES.RETRYABLE, email_next_attempt_at=now + timedelta(minutes=5))
        stale_sending = make_row(key='e', state=ES.SENDING, email_claimed_at=now - timedelta(minutes=16))
        fresh_sending = make_row(key='g', state=ES.SENDING, email_claimed_at=now - timedelta(minutes=5))
        make_row(key='h', state=ES.SENT)
        make_row(key='i', state=ES.SKIPPED)
        Notification.objects.filter(pk=old_pending.pk).update(created_at=now - timedelta(minutes=3))
        Notification.objects.filter(pk=young_pending.pk).update(created_at=now - timedelta(seconds=30))
        assert delivery.sweep_due(now) == 3
        assert set(enqueued) == {str(old_pending.pk), str(due_retry.pk), str(stale_sending.pk)}
        assert str(later_retry.pk) not in enqueued and str(fresh_sending.pk) not in enqueued

    def test_sweep_is_bounded(self, frozen_clock, enqueued, settings):
        settings.NOTIFICATION_SWEEP_LIMIT = 2
        for i in range(5):
            make_row(key=f'k{i}', state=ES.RETRYABLE, email_next_attempt_at=frozen_clock.now)
        assert delivery.sweep_due(frozen_clock.now) == 2

    def test_sweep_task_delivers_end_to_end(self, sender, frozen_clock):
        n = make_row()
        Notification.objects.filter(pk=n.pk).update(created_at=frozen_clock.now - timedelta(minutes=5))
        result = tasks.sweep_notifications_task()
        n.refresh_from_db()
        assert result == {'enqueued': 1} and n.email_state == ES.SENT

    def test_broker_refusal_stops_the_sweep_without_raising(self, frozen_clock, monkeypatch, caplog):
        def down(nid):
            raise ConnectionError('down')
        monkeypatch.setattr(tasks.deliver_notification_task, 'delay', down)
        n = make_row(state=ES.RETRYABLE, email_next_attempt_at=frozen_clock.now)
        assert delivery.sweep_due(frozen_clock.now) == 0
        assert 'ConnectionError' in caplog.text and str(n.pk) in caplog.text


# ====================================================================== task + human resend
@pytest.mark.django_db
class TestTaskAndRequeue:
    def test_deliver_task(self, sender):
        n = make_row()
        assert tasks.deliver_notification_task(str(n.pk)) == 'sent'

    def test_deliver_task_for_a_missing_row(self, sender):
        assert tasks.deliver_notification_task('00000000-0000-0000-0000-000000000000') == 'not_claimed'

    def test_requeue_failed_resets_the_row_for_a_reviewed_resend(self, frozen_clock, enqueued):
        admin = f.make_admin()
        failed = make_row(key='f1', state=ES.FAILED, email_attempts=8, email_last_error='stale_needs_review',
                          email_first_attempt_at=frozen_clock.now - timedelta(hours=30))
        sent = make_row(key='s1', state=ES.SENT)
        requeued = delivery.requeue_failed(Notification.objects.all(), actor=admin)
        assert requeued == [failed.pk]
        failed.refresh_from_db()
        sent.refresh_from_db()
        assert (failed.email_state, failed.email_attempts, failed.email_first_attempt_at, failed.email_last_error) == (
            ES.PENDING, 0, None, '')
        assert sent.email_state == ES.SENT
        assert enqueued == [str(failed.pk)]


# ====================================================================== Postgres-only (CI job)
def _postgres_only():
    if connection.vendor != 'postgresql':
        pytest.skip('PostgreSQL concurrency test (run in the Postgres CI job)')


@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
def test_postgres_concurrent_claims_have_exactly_one_winner():
    _postgres_only()
    n = make_row()
    barrier, wins = threading.Barrier(8), []

    def worker():
        try:
            barrier.wait()
            from apps.common import clock
            wins.append(delivery.claim(n.pk, clock.now()))
        finally:
            connection.close()

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len([w for w in wins if w]) == 1
    n.refresh_from_db()
    assert n.email_attempts == 1


@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
def test_postgres_concurrent_notify_same_key_one_row(monkeypatch):
    _postgres_only()
    from apps.notifications.service import notify
    monkeypatch.setattr(tasks.deliver_notification_task, 'delay', lambda nid: None)
    user = f.make_student()
    barrier, rows = threading.Barrier(6), []

    def worker():
        try:
            barrier.wait()
            rows.append(notify(user, 'admin_alert', key='race:1', payload={'alert': 'notification_failed'}).pk)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(set(rows)) == 1 and len(rows) == 6
    assert Notification.objects.filter(idempotency_key='race:1').count() == 1
