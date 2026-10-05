"""Slice N1a: staff alerts (`alert_staff`, `ADMIN_ALERT_RECIPIENTS`) and the F0 `[ADMIN ALERT]` sites routed through them."""
import logging
from unittest import mock

import pytest
from django.test import TestCase

import factories as f
from apps.bookings.models import Booking
from apps.integrations.tasks import cleanup_gcal_event, cleanup_zoom_meeting, dispatch_booking_fulfillment
from apps.integrations.zoom import ZoomError, zoom_client
from apps.notifications import alerts
from apps.notifications.alerts import alert_staff, staff_recipients
from apps.notifications.models import Notification
from apps.payments.models import FulfillmentDispatch
from payment_helpers import lesson

S = Booking.Status
FD = FulfillmentDispatch.Status


def on_commit():
    return TestCase.captureOnCommitCallbacks(execute=True)


def alerts_for(user):
    return Notification.objects.filter(user=user, kind='admin_alert')


# ====================================================================== recipients
@pytest.mark.django_db
class TestRecipients:
    def test_default_is_every_active_admin(self, settings):
        settings.ADMIN_ALERT_RECIPIENTS = []
        a1, a2 = f.make_admin(), f.make_admin()
        f.make_admin(is_active=False)
        f.make_student()
        f.make_teacher_profile()
        assert {u.pk for u in staff_recipients()} == {a1.pk, a2.pk}

    def test_setting_selects_staff_accounts_by_address(self, settings):
        a1 = f.make_admin(email='ops@sharonesl.test')
        f.make_admin(email='other@sharonesl.test')
        f.make_student(email='student@sharonesl.test')
        settings.ADMIN_ALERT_RECIPIENTS = ['OPS@sharonesl.test', 'student@sharonesl.test', 'nobody@sharonesl.test']
        assert [u.pk for u in staff_recipients()] == [a1.pk]   # case-insensitive; non-staff and unknown ignored

    def test_staff_flag_without_admin_role_counts(self, settings):
        settings.ADMIN_ALERT_RECIPIENTS = ['staff@sharonesl.test']
        staff = f.make_student(email='staff@sharonesl.test', is_staff=True)
        assert [u.pk for u in staff_recipients()] == [staff.pk]


# ====================================================================== alert_staff
@pytest.mark.django_db
class TestAlertStaff:
    def test_one_notification_per_recipient_keyed_per_recipient(self, settings):
        settings.ADMIN_ALERT_RECIPIENTS = []
        a1, a2 = f.make_admin(), f.make_admin()
        assert alert_staff('fulfilment_failed', key='admin:fulfilment-failed:b1:t1',
                           payload={'booking_id': 'b1', 'step': 'zoom'}) == 2
        keys = set(Notification.objects.values_list('idempotency_key', flat=True))
        assert keys == {f'admin:fulfilment-failed:b1:t1:{a1.pk}', f'admin:fulfilment-failed:b1:t1:{a2.pk}'}
        n = alerts_for(a1).get()
        assert n.payload == {'alert': 'fulfilment_failed', 'booking_id': 'b1', 'step': 'zoom'}
        assert n.email_state == Notification.EmailState.PENDING

    def test_repeat_is_deduplicated(self):
        f.make_admin()
        alert_staff('fulfilment_failed', key='admin:x:1', payload={})
        alert_staff('fulfilment_failed', key='admin:x:1', payload={})
        assert Notification.objects.count() == 1

    def test_no_recipient_logs_and_returns_zero(self, caplog):
        with caplog.at_level(logging.ERROR):
            assert alert_staff('fulfilment_failed', key='admin:x:2', payload={'booking_id': 'b9'}) == 0
        assert '[ADMIN ALERT]' in caplog.text and 'no recipient' in caplog.text

    def test_unknown_alert_code_is_a_programming_error(self):
        f.make_admin()
        with pytest.raises(ValueError):
            alert_staff('no_such_alert', key='admin:x:3', payload={})

    def test_an_alert_never_breaks_the_caller(self, monkeypatch, caplog):
        f.make_admin()

        def broken(*args, **kwargs):
            raise RuntimeError('db hiccup with secret detail')

        monkeypatch.setattr(alerts, 'notify', broken)
        with caplog.at_level(logging.ERROR):
            assert alert_staff('fulfilment_failed', key='admin:x:4', payload={'booking_id': 'b4'}) == 0
        assert 'RuntimeError' in caplog.text and 'secret detail' not in caplog.text

    def test_admin_alert_mail_is_sent_through_the_pipeline(self, settings):
        from django.core import mail
        admin = f.make_admin()
        with on_commit():
            alert_staff('lesson_disputed_without_verdict', key='admin:d:1', payload={'booking_id': 'b5'})
        assert len(mail.outbox) == 1 and mail.outbox[0].to == [admin.email]
        assert 'b5' in mail.outbox[0].body
        assert alerts_for(admin).get().email_state == Notification.EmailState.SENT


# ====================================================================== F0 sites
@pytest.mark.django_db
class TestF0SitesAlertStaff:
    def test_fulfilment_terminal_failure(self, teacher_user, student_user, settings, caplog):
        admin = f.make_admin()
        settings.FULFILLMENT_MAX_ATTEMPTS = 1
        b = lesson(teacher_user, student_user, -1, status=S.CONFIRMED)
        with mock.patch.object(zoom_client, 'create_meeting', side_effect=ZoomError('down')), \
                caplog.at_level(logging.ERROR):
            dispatch_booking_fulfillment(str(b.id))
        assert FulfillmentDispatch.objects.get(booking=b).status == FD.FAILED
        assert f'FULFILMENT FAILED booking={b.id}' in caplog.text          # the log line stays (ids only)
        n = alerts_for(admin).get()
        assert n.payload['alert'] == 'fulfilment_failed' and n.payload['booking_id'] == str(b.id)
        assert n.idempotency_key.startswith(f'admin:fulfilment-failed:{b.id}:')

    def test_fulfilment_needs_attention_at_the_cap_before_the_lesson(self, teacher_user, student_user, settings):
        admin = f.make_admin()
        settings.FULFILLMENT_MAX_ATTEMPTS = 1
        b = lesson(teacher_user, student_user, 600, status=S.CONFIRMED)
        with mock.patch.object(zoom_client, 'create_meeting', side_effect=ZoomError('down')), \
                mock.patch.object(dispatch_booking_fulfillment, 'apply_async'):
            dispatch_booking_fulfillment(str(b.id))
        assert FulfillmentDispatch.objects.get(booking=b).status == FD.RETRYABLE
        assert alerts_for(admin).get().payload['alert'] == 'fulfilment_needs_attention'

    def test_orphaned_zoom_meeting_when_the_broker_is_down(self, monkeypatch):
        from apps.bookings.services import fulfillment
        admin = f.make_admin()

        def down(*args):
            raise ConnectionError('broker')

        monkeypatch.setattr(cleanup_zoom_meeting, 'delay', down)
        fulfillment._delete_orphan('999000111', 'b-orphan')
        n = alerts_for(admin).get()
        assert n.payload == {'alert': 'orphaned_zoom_meeting', 'meeting_id': '999000111', 'booking_id': 'b-orphan'}

    def test_orphaned_calendar_event_when_the_broker_is_down(self, teacher_user, student_user, monkeypatch):
        from apps.bookings.services import fulfillment
        admin = f.make_admin()
        b = lesson(teacher_user, student_user, 600, status=S.CONFIRMED)

        def down(*args):
            raise ConnectionError('broker')

        monkeypatch.setattr(cleanup_gcal_event, 'delay', down)
        with pytest.raises(fulfillment.ClaimRevoked):
            fulfillment._store_event(b.id, 'not-my-token', 'evt1', str(teacher_user.user_id), b.created_at)
        n = alerts_for(admin).get()
        assert n.payload['alert'] == 'orphaned_calendar_event' and n.payload['booking_id'] == str(b.id)

    def test_dispute_without_verdict(self, teacher_user, student_user, caplog):
        from apps.bookings.services.attendance_probe import dispute_without_verdict
        admin = f.make_admin()
        b = lesson(teacher_user, student_user, -12, status=S.CONFIRMED)
        with caplog.at_level(logging.ERROR):
            dispute_without_verdict(b, 'no attendance verdict before the lesson ended: no Zoom meeting provisioned')
        assert 'Lesson disputed without an attendance verdict' in caplog.text
        n = alerts_for(admin).get()
        assert n.payload == {'alert': 'lesson_disputed_without_verdict', 'booking_id': str(b.id)}
        assert n.idempotency_key == f'admin:disputed-no-verdict:{b.id}:0:{admin.pk}'
