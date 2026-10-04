"""Slice N1c: one `send_email` that is the only code talking to Resend (docs/NOTIFICATIONS.md).

No test here reaches the network: `requests.post` inside the service module is replaced by a recorder.
"""
import base64
import importlib.util
from datetime import datetime, timedelta, timezone as dt_timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests
from django.core import mail
from django.core.exceptions import ImproperlyConfigured

from apps.integrations import email as legacy
from apps.integrations.services import email as svc
from apps.integrations.services.email import Attachment, EmailResult, InvalidEmailError, render_html, send_email
from config.settings.guard import resolve_email_backend_mode, validate_production_settings
from test_settings_guard import GOOD

BACKEND = Path(__file__).resolve().parents[1]
ADDRESS = 'student.private@example.com'


class FakeResponse:
    def __init__(self, status_code, body=None, headers=None):
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}
        self.text = repr(body)

    def json(self):
        if self._body is None:
            raise ValueError('no json')
        return self._body


@pytest.fixture
def resend(settings, monkeypatch):
    """Resend mode with a fake key and a recording `requests.post` (no network)."""
    settings.EMAIL_BACKEND_MODE = 'resend'
    settings.RESEND_API_KEY = 're_test_not_a_real_key'
    settings.DEFAULT_FROM_EMAIL = 'Sharon ESL <bookings@sharonesl.com>'
    state = SimpleNamespace(calls=[], response=FakeResponse(200, {'id': 'msg_123'}), raises=None)

    def fake_post(url, **kwargs):
        state.calls.append(SimpleNamespace(url=url, **kwargs))
        if state.raises is not None:
            raise state.raises
        return state.response

    monkeypatch.setattr(svc.requests, 'post', fake_post)
    return state


def send(**overrides):
    args = dict(to=ADDRESS, subject='Hello', html='<p>Hi</p>', text='Hi')
    args.update(overrides)
    return send_email(args.pop('to'), args.pop('subject'), args.pop('html'), args.pop('text'), **args)


# ------------------------------------------------------------------------------------------------------------- success
class TestSuccess:
    def test_2xx_is_sent_with_the_provider_message_id(self, resend):
        result = send()
        assert isinstance(result, EmailResult)
        assert (result.status, result.provider_message_id, result.error_code) == ('sent', 'msg_123', '')
        assert result.ok

    def test_request_shape_from_to_subject_bodies_and_timeout(self, resend, settings):
        send()
        call, = resend.calls
        assert call.url == 'https://api.resend.com/emails'
        assert call.json['to'] == [ADDRESS] and call.json['from'] == settings.DEFAULT_FROM_EMAIL
        assert (call.json['subject'], call.json['html'], call.json['text']) == ('Hello', '<p>Hi</p>', 'Hi')
        assert call.headers['Authorization'] == 'Bearer re_test_not_a_real_key'
        assert call.timeout and call.timeout > 0

    def test_idempotency_key_is_sent_as_header(self, resend):
        send(idempotency_key='booking-confirmed:abc:0:student')
        assert resend.calls[0].headers['Idempotency-Key'] == 'booking-confirmed:abc:0:student'

    def test_no_idempotency_header_without_a_key(self, resend):
        send()
        assert 'Idempotency-Key' not in resend.calls[0].headers

    def test_attachments_are_base64_with_filename_and_content_type(self, resend):
        raw = b'BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n'
        send(attachments=[Attachment('lesson.ics', raw, 'text/calendar')])
        att, = resend.calls[0].json['attachments']
        assert base64.b64decode(att['content']) == raw
        assert (att['filename'], att['content_type']) == ('lesson.ics', 'text/calendar')

    def test_reply_to_and_tags(self, resend):
        send(reply_to='support@sharonesl.com', tags={'kind': 'booking_confirmed'})
        body = resend.calls[0].json
        assert body['reply_to'] == ['support@sharonesl.com']
        assert body['tags'] == [{'name': 'kind', 'value': 'booking_confirmed'}]

    def test_optional_fields_are_omitted_when_not_given(self, resend):
        send(text='')
        body = resend.calls[0].json
        assert not {'text', 'reply_to', 'tags', 'attachments'} & set(body)


# ------------------------------------------------------------------------------------------------------- error mapping
class TestErrorMapping:
    def test_409_is_in_flight(self, resend):
        resend.response = FakeResponse(409, {'name': 'concurrent_idempotent_requests', 'message': 'x'})
        result = send(idempotency_key='k1')
        assert result.status == 'in_flight' and not result.ok
        assert '409' in result.error_code

    @pytest.mark.parametrize('status', [429, 500, 502, 503, 504])
    def test_rate_limit_and_server_errors_are_retryable(self, resend, status):
        resend.response = FakeResponse(status, {'name': 'application_error', 'message': 'x'})
        result = send()
        assert result.status == 'retryable' and str(status) in result.error_code

    @pytest.mark.parametrize('exc,code', [
        (requests.Timeout('read timed out'), 'timeout'),
        (requests.ConnectionError('refused'), 'connection_error'),
    ])
    def test_timeouts_and_connection_errors_are_retryable(self, resend, exc, code):
        resend.raises = exc
        result = send()
        assert (result.status, result.error_code) == ('retryable', code)

    @pytest.mark.parametrize('status,name', [(422, 'validation_error'), (400, 'validation_error'),
                                             (401, 'missing_api_key'), (403, 'invalid_api_key')])
    def test_other_4xx_fail_permanently_with_a_short_code(self, resend, status, name):
        resend.response = FakeResponse(status, {'name': name, 'message': 'details'})
        result = send()
        assert result.status == 'failed'
        assert result.error_code == f'http_{status}:{name}'

    def test_provider_error_name_is_only_kept_when_it_is_a_plain_identifier(self, resend):
        resend.response = FakeResponse(422, {'name': f'<{ADDRESS}> bad', 'message': 'x'})
        assert send().error_code == 'http_422'

    def test_2xx_without_json_is_still_sent(self, resend):
        resend.response = FakeResponse(200, None)
        result = send()
        assert (result.status, result.provider_message_id) == ('sent', '')

    def test_missing_key_in_resend_mode_fails_without_calling_the_provider(self, resend, settings):
        settings.RESEND_API_KEY = ''
        result = send()
        assert (result.status, result.error_code) == ('failed', 'not_configured')
        assert resend.calls == []


# ------------------------------------------------------------------------------------------------------------ logging
class TestLogsCarryIdsOnly:
    def test_failure_logs_have_no_address_or_provider_body(self, resend, caplog):
        resend.response = FakeResponse(422, {'name': 'validation_error', 'message': f'Invalid `to` {ADDRESS} SECRETBODY'})
        with caplog.at_level('DEBUG'):
            send(subject='Your reset link SECRETSUBJECT')
        assert caplog.records, 'a failed send must be logged'
        assert ADDRESS not in caplog.text and 'SECRETBODY' not in caplog.text and 'SECRETSUBJECT' not in caplog.text

    def test_exception_text_is_not_logged(self, resend, caplog):
        resend.raises = requests.ConnectionError(f'cannot reach host for {ADDRESS} SECRETEXC')
        with caplog.at_level('DEBUG'):
            send()
        assert 'ConnectionError' in caplog.text
        assert ADDRESS not in caplog.text and 'SECRETEXC' not in caplog.text

    def test_success_logs_the_provider_id_only(self, resend, caplog):
        with caplog.at_level('DEBUG'):
            send(subject='SECRETSUBJECT')
        assert 'msg_123' in caplog.text
        assert ADDRESS not in caplog.text and 'SECRETSUBJECT' not in caplog.text


# ------------------------------------------------------------------------------------------------- header injection
class TestHeaderInjection:
    @pytest.mark.parametrize('field,value', [
        ('subject', 'Hi\r\nBcc: victim@example.com'),
        ('subject', 'Hi\nX: y'),
        ('to', 'a@example.com\r\nBcc: b@example.com'),
        ('reply_to', 'a@example.com\nBcc: b@example.com'),
        ('idempotency_key', 'key\r\nX-Evil: 1'),
    ])
    def test_cr_lf_is_rejected_before_any_send(self, resend, field, value):
        with pytest.raises(InvalidEmailError):
            send(**{field: value})
        assert resend.calls == []

    def test_cr_lf_rejected_in_console_mode_too(self, settings):
        settings.EMAIL_BACKEND_MODE = 'console'
        with pytest.raises(InvalidEmailError):
            send(subject='a\r\nb')
        assert mail.outbox == []

    def test_empty_recipient_rejected(self, resend):
        with pytest.raises(InvalidEmailError):
            send(to='')

    def test_overlong_idempotency_key_rejected(self, resend):
        with pytest.raises(InvalidEmailError):
            send(idempotency_key='k' * 257)


# ------------------------------------------------------------------------------------------------------- console mode
class TestConsoleMode:
    def test_tests_run_in_console_mode_by_default(self, settings):
        assert settings.EMAIL_BACKEND_MODE == 'console'

    def test_console_mode_uses_the_django_mail_backend_and_never_calls_resend(self, settings, monkeypatch):
        settings.EMAIL_BACKEND_MODE = 'console'
        monkeypatch.setattr(svc.requests, 'post', lambda *a, **k: pytest.fail('console mode must not call Resend'))
        result = send(attachments=[Attachment('lesson.ics', b'ICS', 'text/calendar')], idempotency_key='k')
        assert result.status == 'sent' and result.provider_message_id.startswith('console:')
        message, = mail.outbox
        assert message.to == [ADDRESS] and message.subject == 'Hello' and message.body == 'Hi'
        assert message.alternatives[0][0] == '<p>Hi</p>'
        filename, content, mimetype = message.attachments[0]
        assert (filename, mimetype) == ('lesson.ics', 'text/calendar') and content in ('ICS', b'ICS')

    def test_unknown_mode_is_a_configuration_error(self, settings):
        settings.EMAIL_BACKEND_MODE = 'smtp'
        with pytest.raises(ImproperlyConfigured):
            send()


# ----------------------------------------------------------------------------------------------------------- escaping
class TestEscapingHelper:
    def test_hostile_values_are_escaped(self):
        html = render_html('<p>Hi {name}, your tutor is {tutor}</p>', name='<script>alert(1)</script>', tutor='"T" & co')
        assert '<script>' not in html and '&lt;script&gt;alert(1)&lt;/script&gt;' in html
        assert '&quot;T&quot; &amp; co' in html
        assert html.startswith('<p>Hi ')

    def test_result_is_a_string_marked_safe(self):
        # Already escaped, so Django templates must not escape it a second time; JSON / TextField treat it as str.
        from django.utils.safestring import SafeString
        assert isinstance(render_html('<b>{x}</b>', x='1'), SafeString)


# ------------------------------------------------------------------------------------------- production boot guard
class TestProductionGuard:
    @pytest.mark.parametrize('env,mode', [
        ({}, 'console'),
        ({'RESEND_API_KEY': 're_dev_placeholder'}, 'console'),
        ({'RESEND_API_KEY': 're_live_x'}, 'resend'),
        ({'RESEND_API_KEY': 're_live_x', 'EMAIL_BACKEND_MODE': 'console'}, 'console'),
        ({'EMAIL_BACKEND_MODE': ' Resend '}, 'resend'),
    ])
    def test_mode_resolution(self, env, mode):
        assert resolve_email_backend_mode(env) == mode

    @pytest.mark.parametrize('mode', ['console', 'smtp', 'locmem'])
    def test_production_refuses_anything_but_resend(self, mode):
        with pytest.raises(ImproperlyConfigured, match='EMAIL_BACKEND_MODE'):
            validate_production_settings({**GOOD, 'EMAIL_BACKEND_MODE': mode})

    def test_production_accepts_explicit_resend(self):
        validate_production_settings({**GOOD, 'EMAIL_BACKEND_MODE': 'resend'})

    def test_missing_key_in_production_still_refused(self):
        with pytest.raises(ImproperlyConfigured, match='RESEND_API_KEY'):
            validate_production_settings({**GOOD, 'RESEND_API_KEY': ''})

    def test_check_deploy_refuses_console_mode(self):
        spec = importlib.util.spec_from_file_location('check_deploy_n1c', BACKEND / 'scripts' / 'check_deploy.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert module.email_mode_problems('console')
        assert module.email_mode_problems('')
        assert module.email_mode_problems('resend') == []
        assert module.throwaway_environment()['EMAIL_BACKEND_MODE'] == 'resend'

    def test_env_example_lists_the_new_settings(self):
        example = (BACKEND.parent / '.env.example').read_text(encoding='utf-8')
        for name in ('EMAIL_BACKEND_MODE=', 'RESEND_TIMEOUT_SECONDS=', 'RESEND_API_KEY=', 'DEFAULT_FROM_EMAIL='):
            assert name in example


# ---------------------------------------------------------------------------------------- only one module talks to Resend
def test_only_the_email_service_contains_the_resend_endpoint():
    hits = sorted(str(p.relative_to(BACKEND)).replace('\\', '/') for p in (BACKEND / 'apps').rglob('*.py')
                  if 'api.resend.com' in p.read_text(encoding='utf-8'))
    assert hits == ['apps/integrations/services/email.py']


# ------------------------------------------------------------------------------------------------- legacy wrapper
class TestLegacyWrapper:
    def test_sent_returns_quietly(self, resend):
        assert legacy.send_email(ADDRESS, 's', '<p>x</p>', 't') is None
        assert resend.calls[0].json['to'] == [ADDRESS]

    @pytest.mark.parametrize('status', [409, 429, 500, 422, 401])
    def test_anything_but_sent_raises_for_the_celery_retry(self, resend, status):
        resend.response = FakeResponse(status, {'name': 'x', 'message': 'y'})
        with pytest.raises(legacy.EmailDeliveryError):
            legacy.send_email(ADDRESS, 's', '<p>x</p>')


# ------------------------------------------------------------------------------------------------ booking confirmation
def fake_booking(**overrides):
    start = datetime(2026, 11, 2, 9, 0, tzinfo=dt_timezone.utc)
    values = dict(
        id='7f9c1b9e-0000-4000-8000-000000000001', reschedule_count=0,
        student=SimpleNamespace(first_name='<script>alert(1)</script>', username='stu', email=ADDRESS),
        teacher=SimpleNamespace(user=SimpleNamespace(first_name='Thandi & "Co"', username='tutor')),
        start_time_utc=start, end_time_utc=start + timedelta(minutes=25),
        zoom_join_url='https://zoom.us/j/123?pwd=a&b=c', zoom_password='pw',
    )
    values.update(overrides)
    return SimpleNamespace(**values)


class TestBookingConfirmation:
    def test_sent_through_send_email_with_ics_and_generation_key(self, resend):
        booking = fake_booking()
        result = legacy.send_booking_confirmation_email(booking)
        assert result.status == 'sent'
        call, = resend.calls
        assert call.headers['Idempotency-Key'] == f'booking-confirmed:{booking.id}:0:student'
        assert call.json['to'] == [ADDRESS]
        att, = call.json['attachments']
        assert att['filename'] == 'lesson-invite.ics' and att['content_type'].startswith('text/calendar')
        assert b'BEGIN:VCALENDAR' in base64.b64decode(att['content'])

    def test_a_reschedule_changes_the_key(self, resend):
        legacy.send_booking_confirmation_email(fake_booking(reschedule_count=2))
        assert resend.calls[0].headers['Idempotency-Key'].endswith(':2:student')

    def test_names_and_links_are_escaped(self, resend):
        legacy.send_booking_confirmation_email(fake_booking())
        html = resend.calls[0].json['html']
        assert '<script>' not in html and '&lt;script&gt;' in html
        assert 'Thandi &amp; &quot;Co&quot;' in html
        assert 'href="https://zoom.us/j/123?pwd=a&amp;b=c"' in html
        assert resend.calls[0].json['text']

    @pytest.mark.parametrize('status', [409, 429, 500, 422])
    def test_anything_but_sent_raises_so_fulfilment_retries(self, resend, status):
        resend.response = FakeResponse(status, {'name': 'x'})
        with pytest.raises(legacy.EmailDeliveryError):
            legacy.send_booking_confirmation_email(fake_booking())

    def test_console_mode_delivers_the_invite_locally(self, settings):
        settings.EMAIL_BACKEND_MODE = 'console'
        legacy.send_booking_confirmation_email(fake_booking())
        message, = mail.outbox
        assert message.attachments[0][0] == 'lesson-invite.ics'
