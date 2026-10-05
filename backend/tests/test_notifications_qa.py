"""Slice N1a QA round 1: producer safety (savepoints, renderer errors), no-address skip, expiry hook, boot warning, admin."""
import importlib.util
import logging
from datetime import timedelta
from pathlib import Path

import pytest
from django.contrib.admin.sites import site
from django.db import IntegrityError, connection, transaction
from django.test import RequestFactory

import factories as f
from apps.integrations.services import email as email_service
from apps.integrations.services.email import EmailResult
from apps.notifications import alerts, delivery, registry
from apps.notifications.alerts import alert_staff
from apps.notifications.models import Notification
from apps.notifications.registry import EMAIL, IN_APP, Kind, Rendered
from apps.notifications.service import notify
from config.settings.guard import validate_production_settings
from test_settings_guard import GOOD

ES = Notification.EmailState
BACKEND = Path(__file__).resolve().parent.parent


def _plain(user, payload, booking):
    return Rendered(subject='Hello', html='<p>Hello</p>', text='Hello', title='Hello', body='Hello body')


def _boom(user, payload, booking):
    raise AttributeError("'NoneType' object has no attribute 'start_time_utc' (secret detail)")


@pytest.fixture
def no_delivery(monkeypatch):
    from apps.notifications import tasks
    calls = []
    monkeypatch.setattr(tasks.deliver_notification_task, 'delay', lambda nid: calls.append(nid))
    return calls


@pytest.fixture
def sender(monkeypatch):
    calls = []

    def fake(to, subject, html, text='', **kwargs):
        calls.append(subject)
        return EmailResult('sent', provider_message_id='msg_1')

    monkeypatch.setattr(email_service, 'send_email', fake)
    return calls


def register_kind(monkeypatch, name, render=_plain, category='booking', channels=frozenset({EMAIL, IN_APP}), **extra):
    kind = Kind(name, category, channels, render, **extra)
    monkeypatch.setitem(registry._REGISTRY, name, kind)
    return kind


def make_row(user=None, *, key='qa:1', state=ES.PENDING, kind='admin_alert', **fields):
    data = dict(user=user or f.make_student(), kind=kind, idempotency_key=key, title='T', email_state=state,
                rendered_subject='S', rendered_html='<p>x</p>', rendered_text='x')
    data.update(fields)
    return Notification.objects.create(**data)


# ====================================================================== MAJOR-1: alert_staff savepoint
@pytest.mark.django_db
class TestAlertStaffSavepoint:
    def test_alert_runs_inside_its_own_savepoint(self, monkeypatch):
        f.make_admin()
        depths = []
        base = len(connection.savepoint_ids)

        def spy(user, kind, **kwargs):
            depths.append(len(connection.savepoint_ids))
            return None

        monkeypatch.setattr(alerts, 'notify', spy)
        with transaction.atomic():
            alert_staff('fulfilment_failed', key='admin:sp:1', payload={})
        assert depths and all(d >= base + 2 for d in depths)         # outer atomic + alert_staff's savepoint

    def test_a_database_error_inside_an_alert_leaves_the_callers_transaction_usable(self, monkeypatch):
        admin = f.make_admin()
        Notification.objects.create(user=admin, kind='x', idempotency_key='dup')

        def db_error(user, kind, **kwargs):
            Notification.objects.create(user=user, kind='x', idempotency_key='dup')      # real IntegrityError

        monkeypatch.setattr(alerts, 'notify', db_error)
        with transaction.atomic():
            assert alert_staff('fulfilment_failed', key='admin:sp:2', payload={}) == 0
            assert f.make_student().pk                       # the caller's transaction is still usable
        assert Notification.objects.filter(idempotency_key='dup').count() == 1

    def test_a_failing_recipient_does_not_roll_back_the_others(self, monkeypatch):
        a1, a2 = f.make_admin(), f.make_admin()
        real = alerts.notify

        def flaky(user, kind, **kwargs):
            if user.pk == a1.pk:
                raise IntegrityError('boom')
            return real(user, kind, **kwargs)

        monkeypatch.setattr(alerts, 'notify', flaky)
        assert alert_staff('fulfilment_failed', key='admin:sp:3', payload={}) == 1
        assert Notification.objects.filter(user=a2, kind='admin_alert').count() == 1


def _postgres_only():
    if connection.vendor != 'postgresql':
        pytest.skip('PostgreSQL aborted-transaction test (run in the Postgres CI job)')


@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
def test_postgres_alert_database_error_does_not_abort_the_callers_transaction(monkeypatch):
    _postgres_only()
    admin = f.make_admin()
    Notification.objects.create(user=admin, kind='x', idempotency_key='dup')

    def db_error(user, kind, **kwargs):
        Notification.objects.create(user=user, kind='x', idempotency_key='dup')

    monkeypatch.setattr(alerts, 'notify', db_error)
    with transaction.atomic():
        assert alert_staff('fulfilment_failed', key='admin:pg:1', payload={}) == 0
        assert f.make_student().pk                           # would raise InFailedSqlTransaction without the savepoint


# ====================================================================== MAJOR-2: renderer errors never reach the producer
@pytest.mark.django_db
class TestRendererErrors:
    def test_a_renderer_error_becomes_a_minimal_failed_row_and_a_staff_alert(self, monkeypatch, no_delivery, caplog):
        register_kind(monkeypatch, 'broken_kind', _boom)
        admin = f.make_admin()
        user = f.make_student()
        with caplog.at_level(logging.ERROR):
            n = notify(user, 'broken_kind', key='render:1', payload={})          # booking=None: the renderer fails
        assert n is not None
        n.refresh_from_db()
        assert (n.email_state, n.email_last_error, n.in_app) == (ES.FAILED, 'render_error', True)
        assert n.title == 'broken kind' and n.body == '' and n.rendered_html == '' and n.rendered_subject == ''
        assert no_delivery == []
        alert = Notification.objects.get(user=admin, kind='admin_alert')
        assert alert.payload['alert'] == 'notification_failed' and alert.payload['code'] == 'render_error'
        assert alert.payload['notification_id'] == str(n.pk)
        assert 'AttributeError' in caplog.text and 'broken_kind' in caplog.text and 'render:1' in caplog.text
        assert 'secret detail' not in caplog.text

    def test_the_producers_transaction_survives_a_renderer_database_error(self, monkeypatch, no_delivery):
        def db_error(user, payload, booking):
            Notification.objects.create(user=user, kind='x', idempotency_key='dup-render')
            Notification.objects.create(user=user, kind='x', idempotency_key='dup-render')

        register_kind(monkeypatch, 'db_broken_kind', db_error)
        user = f.make_student()
        with transaction.atomic():
            n = notify(user, 'db_broken_kind', key='render:2', payload={})
            assert n.email_last_error == 'render_error'
            assert f.make_student().pk
        assert not Notification.objects.filter(idempotency_key='dup-render').exists()      # rolled back with its savepoint

    def test_a_failing_staff_alert_template_does_not_recurse(self, monkeypatch, no_delivery):
        monkeypatch.setitem(registry._REGISTRY, 'admin_alert',
                            Kind('admin_alert', 'staff_alert', frozenset({EMAIL, IN_APP}), _boom))
        admin = f.make_admin()
        n = notify(admin, 'admin_alert', key='render:3', payload={'alert': 'fulfilment_failed'})
        assert n.email_last_error == 'render_error'
        assert Notification.objects.count() == 1

    def test_email_only_kind_keeps_a_hidden_failed_row(self, monkeypatch, no_delivery):
        register_kind(monkeypatch, 'broken_mail', _boom, category='payment', channels=frozenset({EMAIL}))
        n = notify(f.make_student(), 'broken_mail', key='render:4', payload={})
        assert (n.in_app, n.email_state) == (False, ES.FAILED)

    def test_unknown_kind_and_bad_payload_are_still_programming_errors(self, no_delivery):
        with pytest.raises(registry.UnknownKind):
            notify(f.make_student(), 'nope', key='render:5', payload={})


# ====================================================================== MINOR-4: no address -> skipped at creation
@pytest.mark.django_db
class TestNoAddress:
    def test_user_without_email_is_skipped_at_creation_without_alert(self, monkeypatch, no_delivery):
        register_kind(monkeypatch, 'plain_kind')
        admin = f.make_admin()
        user = f.make_student(email='')
        n = notify(user, 'plain_kind', key='addr:1', payload={})
        assert (n.email_state, n.email_last_error, n.in_app) == (ES.SKIPPED, 'no_address', True)
        assert n.rendered_html == '' and no_delivery == []
        assert not Notification.objects.filter(user=admin).exists()

    def test_whitespace_address_counts_as_missing(self, monkeypatch, no_delivery):
        register_kind(monkeypatch, 'plain_kind')
        n = notify(f.make_student(email='   '), 'plain_kind', key='addr:2', payload={})
        assert (n.email_state, n.email_last_error) == (ES.SKIPPED, 'no_address')

    def test_returns_the_existing_row_even_when_the_payload_differs(self, monkeypatch, no_delivery):
        register_kind(monkeypatch, 'plain_kind')
        user = f.make_student()
        first = notify(user, 'plain_kind', key='addr:3', payload={'step': 'one'})
        again = notify(user, 'plain_kind', key='addr:3', payload={'step': 'two'})
        assert again.pk == first.pk and again.payload == {'step': 'one'}


# ====================================================================== MINOR-3: expiry hook
@pytest.mark.django_db
class TestNotAfter:
    def _kind(self, monkeypatch):
        return register_kind(monkeypatch, 'reminder_like', not_after=lambda payload, booking: booking.start_time_utc)

    def test_expired_row_is_skipped_not_sent(self, monkeypatch, sender, frozen_clock):
        self._kind(monkeypatch)
        booking = f.make_booking(f.make_teacher_profile(), f.make_student(), start=frozen_clock.now + timedelta(hours=1))
        n = make_row(kind='reminder_like', key='exp:1', booking=booking)
        frozen_clock.advance(hours=1)                                   # exactly the start: expired (>=)
        assert delivery.deliver(n.pk) == 'skipped'
        n.refresh_from_db()
        assert (n.email_state, n.email_last_error) == (ES.SKIPPED, 'expired') and sender == []

    def test_not_yet_expired_row_is_sent(self, monkeypatch, sender, frozen_clock):
        self._kind(monkeypatch)
        booking = f.make_booking(f.make_teacher_profile(), f.make_student(), start=frozen_clock.now + timedelta(hours=1))
        n = make_row(kind='reminder_like', key='exp:2', booking=booking)
        frozen_clock.advance(minutes=59)
        assert delivery.deliver(n.pk) == 'sent'

    def test_kind_without_a_hook_never_expires(self, sender, frozen_clock):
        n = make_row(kind='admin_alert', key='exp:3')
        frozen_clock.advance(days=3)
        assert delivery.deliver(n.pk) in ('sent', 'failed')     # failed only through the 20 h rule, never 'skipped'

    def test_a_broken_hook_does_not_block_delivery(self, monkeypatch, sender, frozen_clock):
        def bad(payload, booking):
            raise RuntimeError('hook bug')

        register_kind(monkeypatch, 'bad_hook', not_after=bad)
        n = make_row(kind='bad_hook', key='exp:4')
        assert delivery.deliver(n.pk) == 'sent'

    def test_retry_after_expiry_is_skipped(self, monkeypatch, frozen_clock):
        self._kind(monkeypatch)
        booking = f.make_booking(f.make_teacher_profile(), f.make_student(), start=frozen_clock.now + timedelta(minutes=10))
        results = [EmailResult('retryable', error_code='http_503')]
        monkeypatch.setattr(email_service, 'send_email', lambda *a, **k: results.pop(0))
        n = make_row(kind='reminder_like', key='exp:5', booking=booking)
        assert delivery.deliver(n.pk) == 'retryable'
        frozen_clock.advance(minutes=11)
        assert delivery.deliver(n.pk) == 'skipped'


# ====================================================================== 20 h boundary
@pytest.mark.django_db
def test_exactly_20_hours_after_the_first_attempt_is_refused(sender, frozen_clock):
    n = make_row(state=ES.RETRYABLE, email_attempts=2, email_first_attempt_at=frozen_clock.now - timedelta(hours=20))
    assert delivery.deliver(n.pk) == 'failed'
    n.refresh_from_db()
    assert n.email_last_error == 'stale_needs_review' and sender == []


# ====================================================================== MINOR-6: boot warning and check_deploy line
class TestAlertRecipientsWarning:
    def test_production_boot_warns_when_no_recipients_are_configured(self, caplog):
        with caplog.at_level(logging.WARNING):
            validate_production_settings(dict(GOOD))
        assert 'ADMIN_ALERT_RECIPIENTS' in caplog.text

    def test_no_warning_when_configured(self, caplog):
        with caplog.at_level(logging.WARNING):
            validate_production_settings({**GOOD, 'ADMIN_ALERT_RECIPIENTS': 'ops@sharonesl.com'})
        assert 'ADMIN_ALERT_RECIPIENTS' not in caplog.text

    def test_check_deploy_reports_it_as_a_warning_line(self):
        spec = importlib.util.spec_from_file_location('check_deploy_n1a', BACKEND / 'scripts' / 'check_deploy.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert module.alert_recipient_warnings({}) and 'ADMIN_ALERT_RECIPIENTS' in module.alert_recipient_warnings({})[0]
        assert module.alert_recipient_warnings({'ADMIN_ALERT_RECIPIENTS': ' '})
        assert module.alert_recipient_warnings({'ADMIN_ALERT_RECIPIENTS': 'ops@sharonesl.com'}) == []


# ====================================================================== MINOR-7: admin does not show bodies to non-superusers
@pytest.mark.django_db
class TestAdminDisplay:
    def _fields(self, user):
        model_admin = site._registry[Notification]
        request = RequestFactory().get('/')
        request.user = user
        return model_admin, set(model_admin.get_fields(request)), set(model_admin.get_readonly_fields(request))

    def test_staff_non_superuser_sees_no_rendered_bodies(self):
        staff = f.make_admin(is_superuser=False)
        _, fields, readonly = self._fields(staff)
        for hidden in ('rendered_subject', 'rendered_text', 'rendered_html'):
            assert hidden not in fields and hidden not in readonly

    def test_superuser_sees_subject_and_text_but_not_html(self):
        _, fields, _ = self._fields(f.make_admin())
        assert {'rendered_subject', 'rendered_text'} <= fields and 'rendered_html' not in fields
