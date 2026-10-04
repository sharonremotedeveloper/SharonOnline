"""Slice N1c QA conditions: permanent vs transient failures, Retry-After, key charset, console backend scope,
2xx without id, address separators, cancellation e-mail escaping."""
from types import SimpleNamespace
from unittest import mock

import pytest
from django.core import mail

from apps.bookings.models import Booking
from apps.integrations import email as legacy
from apps.integrations.email import EmailDeliveryError, EmailPermanentError
from apps.integrations.services import email as svc
from apps.integrations.services.email import InvalidEmailError, send_email
from payment_helpers import lesson
from test_send_email import ADDRESS, FakeResponse, fake_booking, resend  # noqa: F401  (resend is a fixture)


def send(**overrides):
    args = dict(to=ADDRESS, subject='Hello', html='<p>Hi</p>', text='Hi')
    args.update(overrides)
    return send_email(args.pop('to'), args.pop('subject'), args.pop('html'), args.pop('text'), **args)


# ------------------------------------------------------------------------------- 1. permanent vs transient (wrapper)
class TestPermanentVersusTransient:
    @pytest.mark.parametrize('status', [422, 403, 401, 400])
    def test_failed_raises_the_permanent_subclass_with_the_result(self, resend, status):
        resend.response = FakeResponse(status, {'name': 'validation_error'})
        with pytest.raises(EmailPermanentError) as raised:
            legacy.send_email(ADDRESS, 's', '<p>x</p>')
        assert raised.value.result.status == 'failed' and raised.value.result.http_status == status

    def test_not_configured_is_permanent(self, resend, settings):
        settings.RESEND_API_KEY = ''
        with pytest.raises(EmailPermanentError) as raised:
            legacy.send_email(ADDRESS, 's', '<p>x</p>')
        assert raised.value.result.error_code == 'not_configured'

    @pytest.mark.parametrize('status,expected', [(409, 'in_flight'), (429, 'retryable'), (500, 'retryable')])
    def test_in_flight_and_retryable_raise_the_plain_error(self, resend, status, expected):
        resend.response = FakeResponse(status, {'name': 'x'})
        with pytest.raises(EmailDeliveryError) as raised:
            legacy.send_email(ADDRESS, 's', '<p>x</p>')
        assert not isinstance(raised.value, EmailPermanentError)
        assert raised.value.result.status == expected

    def test_the_error_still_accepts_a_bare_message(self):
        assert EmailDeliveryError('provider down').result is None and str(EmailDeliveryError('provider down')) == 'provider down'

    def test_confirmation_failed_is_permanent(self, resend):
        resend.response = FakeResponse(422, {'name': 'validation_error'})
        with pytest.raises(EmailPermanentError) as raised:
            legacy.send_booking_confirmation_email(fake_booking())
        assert raised.value.result.error_code == 'http_422:validation_error'

    def test_confirmation_in_flight_is_transient(self, resend):
        resend.response = FakeResponse(409, {'name': 'concurrent_idempotent_requests'})
        with pytest.raises(EmailDeliveryError) as raised:
            legacy.send_booking_confirmation_email(fake_booking())
        assert not isinstance(raised.value, EmailPermanentError) and raised.value.result.status == 'in_flight'


# --------------------------------------------------------------------------------- 1. callers do not retry forever
def _autoretry_tasks():
    from apps.payments import tasks as payments_tasks
    from apps.users import tasks as users_tasks
    return [users_tasks.send_account_email_task, payments_tasks.send_admin_alert_email_task,
            payments_tasks.send_payment_failure_email_task, payments_tasks.send_refund_processed_email_task]


@pytest.mark.parametrize('task', _autoretry_tasks(), ids=lambda t: t.name.rsplit('.', 1)[-1])
def test_autoretry_tasks_skip_permanent_failures(task):
    assert EmailPermanentError in tuple(task.dont_autoretry_for)
    assert EmailDeliveryError in tuple(task.autoretry_for)


def _permanent(*args, **kwargs):
    raise EmailPermanentError('e-mail failed (http_422:validation_error)',
                              result=svc.EmailResult('failed', error_code='http_422:validation_error', http_status=422))


def _transient(*args, **kwargs):
    raise EmailDeliveryError('e-mail retryable (http_503)', result=svc.EmailResult('retryable', error_code='http_503'))


@pytest.mark.django_db
class TestAutoretryBehaviour:
    def test_account_mail_permanent_failure_is_not_retried_and_is_logged_with_ids(self, student_user, monkeypatch, caplog):
        from apps.users import tasks
        monkeypatch.setattr(tasks, 'send_email', _permanent)
        with mock.patch.object(tasks.send_account_email_task, 'retry', return_value=RuntimeError('retried')) as retry, \
                caplog.at_level('WARNING'):
            with pytest.raises(EmailPermanentError):
                tasks.send_account_email_task(str(student_user.id), tasks.KIND_PASSWORD_RESET)
        retry.assert_not_called()
        assert str(student_user.id) in caplog.text and 'http_422:validation_error' in caplog.text
        assert student_user.email not in caplog.text

    def test_account_mail_transient_failure_is_still_retried(self, student_user, monkeypatch):
        from apps.users import tasks
        monkeypatch.setattr(tasks, 'send_email', _transient)
        with mock.patch.object(tasks.send_account_email_task, 'retry', return_value=RuntimeError('retried')) as retry:
            with pytest.raises(RuntimeError, match='retried'):
                tasks.send_account_email_task(str(student_user.id), tasks.KIND_PASSWORD_RESET)
        retry.assert_called_once()

    def test_admin_alert_permanent_failure_is_not_retried(self, monkeypatch, caplog):
        from apps.payments import tasks
        monkeypatch.setattr(tasks, 'send_email', _permanent)
        with mock.patch.object(tasks.send_admin_alert_email_task, 'retry', return_value=RuntimeError('retried')) as retry, \
                caplog.at_level('WARNING'):
            with pytest.raises(EmailPermanentError):
                tasks.send_admin_alert_email_task('subject', 'detail')
        retry.assert_not_called()
        assert 'http_422:validation_error' in caplog.text


@pytest.mark.django_db
class TestManualRetryCallers:
    def test_support_inquiry_permanent_failure_is_not_retried(self, monkeypatch, caplog):
        from apps.users import tasks
        from apps.users.models import SupportInquiry
        inquiry = SupportInquiry.objects.create(sender_name='Aiko', sender_email='aiko@example.com', sender_type='student',
                                                subject='Help', message='A message')
        monkeypatch.setattr(tasks, 'send_email', _permanent)
        with mock.patch.object(tasks.send_support_inquiry_notification, 'retry') as retry, caplog.at_level('WARNING'):
            with pytest.raises(EmailPermanentError):
                tasks.send_support_inquiry_notification.run(str(inquiry.id))
        retry.assert_not_called()
        inquiry.refresh_from_db()
        assert inquiry.last_delivery_error.startswith('permanent')
        assert str(inquiry.id) in caplog.text and 'aiko@example.com' not in caplog.text

    def test_eskom_permanent_failure_is_not_retried(self, teacher_user, student_user, monkeypatch, caplog):
        from datetime import timedelta
        from django.utils import timezone
        from apps.integrations import tasks
        from apps.integrations.models import EskomAreaStatus, EskomNotificationAttempt
        booking = lesson(teacher_user, student_user, 120, status=Booking.Status.CONFIRMED)
        now = timezone.now()
        area = EskomAreaStatus.objects.create(area_id='qa-area', area_name='QA Area', stage=2, outages=[],
                                              provider_retrieved_at=now, fresh_until=now + timedelta(minutes=5))
        attempt = EskomNotificationAttempt.objects.create(idempotency_key='qa-attempt', booking=booking,
                                                          recipient=student_user, area_status=area)
        monkeypatch.setattr('apps.integrations.email.send_email', _permanent)
        with mock.patch.object(tasks.send_eskom_notification_task, 'retry') as retry, caplog.at_level('WARNING'):
            with pytest.raises(EmailPermanentError):
                tasks.send_eskom_notification_task.run(str(attempt.id))
        retry.assert_not_called()
        attempt.refresh_from_db()
        assert attempt.last_error.startswith('permanent') and str(attempt.id) in caplog.text

    def test_cancellation_permanent_failure_is_not_retried(self, teacher_user, student_user, monkeypatch, caplog):
        from apps.integrations import tasks
        booking = lesson(teacher_user, student_user, 120, status=Booking.Status.CONFIRMED)
        monkeypatch.setattr('apps.integrations.email.send_email', _permanent)
        with mock.patch.object(tasks.send_cancellation_emails, 'retry') as retry, caplog.at_level('WARNING'):
            with pytest.raises(EmailPermanentError):
                tasks.send_cancellation_emails.run(str(booking.id), 'student')
        retry.assert_not_called()
        assert str(booking.id) in caplog.text

    def test_cancellation_transient_failure_is_still_retried(self, teacher_user, student_user, monkeypatch):
        from apps.integrations import tasks
        booking = lesson(teacher_user, student_user, 120, status=Booking.Status.CONFIRMED)
        monkeypatch.setattr('apps.integrations.email.send_email', _transient)
        with mock.patch.object(tasks.send_cancellation_emails, 'retry', return_value=RuntimeError('retried')) as retry:
            with pytest.raises(RuntimeError, match='retried'):
                tasks.send_cancellation_emails.run(str(booking.id), 'student')
        retry.assert_called_once()


# ------------------------------------------------------------------------------------------------- 2. Retry-After
class TestRetryAfter:
    @pytest.mark.parametrize('status', [429, 503])
    def test_integer_seconds_are_parsed(self, resend, status):
        resend.response = FakeResponse(status, {'name': 'rate_limit_exceeded'}, headers={'Retry-After': '17'})
        assert send().retry_after_seconds == 17

    def test_value_is_capped(self, resend):
        resend.response = FakeResponse(429, {}, headers={'Retry-After': '999999'})
        assert send().retry_after_seconds == 3600

    @pytest.mark.parametrize('value', ['Wed, 21 Oct 2026 07:28:00 GMT', '-5', 'soon', '', '1.5'])
    def test_http_dates_and_junk_are_ignored(self, resend, value):
        resend.response = FakeResponse(429, {}, headers={'Retry-After': value})
        assert send().retry_after_seconds is None

    @pytest.mark.parametrize('status', [200, 422, 500])
    def test_only_429_and_503_carry_it(self, resend, status):
        resend.response = FakeResponse(status, {'id': 'msg_1'}, headers={'Retry-After': '5'})
        assert send().retry_after_seconds is None


# ----------------------------------------------------------------------------- 3. idempotency key charset
class TestIdempotencyKeyCharset:
    @pytest.mark.parametrize('key', ['booking-confirmed:é', 'k\x00ey', 'tab\tkey', 'emoji-\U0001F600', 'del\x7f'])
    def test_non_printable_ascii_is_rejected(self, resend, key):
        with pytest.raises(InvalidEmailError):
            send(idempotency_key=key)
        assert resend.calls == []

    def test_printable_ascii_with_spaces_and_punctuation_is_accepted(self, resend):
        send(idempotency_key='booking-confirmed:1 2:{x}~')
        assert resend.calls[0].headers['Idempotency-Key'] == 'booking-confirmed:1 2:{x}~'


# ----------------------------------------------------------------------------- 4. console backend only in local
def test_console_mail_backend_is_set_by_local_settings_only():
    from importlib import import_module
    base = import_module('config.settings.base')
    local = import_module('config.settings.local')
    assert 'EMAIL_BACKEND' not in vars(base)
    assert local.EMAIL_BACKEND == 'django.core.mail.backends.console.EmailBackend'


# ----------------------------------------------------------------------------- 5. 2xx without id, address separators
class TestNits:
    def test_2xx_without_id_logs_a_warning(self, resend, caplog):
        resend.response = FakeResponse(200, {})
        with caplog.at_level('WARNING'):
            result = send()
        assert result.ok and any(r.levelname == 'WARNING' and 'without' in r.getMessage() for r in caplog.records)
        assert ADDRESS not in caplog.text

    @pytest.mark.parametrize('to', ['a@example.com, b@example.com', 'a@example.com;b@example.com',
                                    ['ok@example.com', 'a@example.com,b@example.com']])
    def test_separators_inside_one_address_are_rejected(self, resend, to):
        with pytest.raises(InvalidEmailError):
            send(to=to)
        assert resend.calls == []

    def test_a_display_name_with_angle_brackets_is_still_fine(self, resend):
        send(to='Aiko <aiko@example.com>')
        assert resend.calls[0].json['to'] == ['Aiko <aiko@example.com>']


# ----------------------------------------------------------------------------- 6. cancellation e-mail escaping
@pytest.mark.django_db
def test_cancellation_mail_escapes_the_student_name(teacher_user, student_user, settings):
    from apps.integrations.tasks import send_cancellation_emails
    settings.EMAIL_BACKEND_MODE = 'console'
    student_user.first_name = '<script>alert(1)</script>'
    student_user.save(update_fields=['first_name'])
    booking = lesson(teacher_user, student_user, 120, status=Booking.Status.CONFIRMED)
    mail.outbox.clear()
    send_cancellation_emails.run(str(booking.id), 'student')
    message, = mail.outbox
    html = message.alternatives[0][0]
    assert '<script>' not in html and '&lt;script&gt;alert(1)&lt;/script&gt;' in html
    assert '<script>alert(1)</script>' in message.body          # plain text stays literal
