"""
Slice F0, review round 1 (lead's adversarial review): B1 OAuth failure scored as a no-show, M1 calendar step unfenced,
M2 probe-only presence is no evidence of student absence, M3 lost queue messages, M4 retry cadence + admin re-queue,
m1 retry_after bypass, m3 past-instance check, m5 explicit e-mail success, m7 resolved DisputeCase reopened.
Zoom / Google HTTP is mocked at `requests` (no network).
"""
import logging
from datetime import timedelta
from types import SimpleNamespace
from unittest import mock

import pytest
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory
from django.utils import timezone

from apps.admin_api.models import DisputeCase
from apps.bookings.models import Booking
from apps.bookings.tasks import audit_attendance_and_noshows_task
from apps.integrations.tasks import (
    cleanup_gcal_event, dispatch_booking_fulfillment, retry_fulfillment_dispatches_task,
)
from apps.integrations.zoom import ZoomError, zoom_client
from apps.payments.models import FulfillmentDispatch
from apps.payments.services.webhook_handler import dispatch_fulfillment
from apps.teachers.models import TeacherStrike
from test_f0_fulfilment_probe import MEETING, NEW_MEETING, at_t10, confirmed, no_penalty

S = Booking.Status
FD = FulfillmentDispatch.Status
St = FulfillmentDispatch.StepState


def resp(status, payload=None):
    r = mock.Mock(status_code=status, text='RAW-PROVIDER-BODY secret@x.test')
    r.json.return_value = payload if payload is not None else {}
    return r


@pytest.fixture
def zoom_configured(monkeypatch, settings):
    """Real-looking credentials: the client must talk to (mocked) Zoom and may never simulate. Since Z1 the client reads
    them from Django settings and retries 429 / 5xx with back-off; the waits are skipped here."""
    for name in ('ZOOM_ACCOUNT_ID', 'ZOOM_CLIENT_ID', 'ZOOM_CLIENT_SECRET'):
        setattr(settings, name, f'cfg-{name.lower()}')
    monkeypatch.setattr('apps.integrations.zoom._sleep', lambda seconds: None)


def token_ok():
    return resp(200, {'access_token': 'tok', 'expires_in': 3600})


def due(booking):
    FulfillmentDispatch.objects.filter(booking=booking).update(next_retry_at=timezone.now() - timedelta(seconds=1))


# ====================================================================== B1: OAuth failure is never "tutor absent"
@pytest.mark.django_db
class TestOAuthFailureIsUnknown:
    @pytest.mark.parametrize('token_status', [401, 429, 500])
    def test_token_failure_defers_the_verdict(self, zoom_configured, teacher_user, student_user, token_status):
        b = at_t10(teacher_user, student_user)
        with mock.patch('apps.integrations.zoom.requests.post', return_value=resp(token_status)), \
                mock.patch('apps.integrations.zoom.requests.get') as get:
            res = audit_attendance_and_noshows_task()
        get.assert_not_called()
        b.refresh_from_db()
        assert b.status == S.CONFIRMED and res['teacher_no_shows'] == 0
        no_penalty(b)

    def test_a_200_without_a_status_is_unknown(self, zoom_configured, teacher_user, student_user):
        b = at_t10(teacher_user, student_user)
        with mock.patch('apps.integrations.zoom.requests.post', return_value=token_ok()), \
                mock.patch('apps.integrations.zoom.requests.get', return_value=resp(200, {'id': 1})):
            audit_attendance_and_noshows_task()
        b.refresh_from_db()
        assert b.status == S.CONFIRMED
        no_penalty(b)

    def test_a_200_token_response_without_a_token_is_a_failure(self, zoom_configured):
        with mock.patch('apps.integrations.zoom.requests.post', return_value=resp(200, {})):
            with pytest.raises(ZoomError):
                zoom_client.get_meeting_status(MEETING)

    def test_create_meeting_never_fabricates_a_room_on_token_failure(self, zoom_configured, teacher_user, student_user):
        b = confirmed(teacher_user, student_user)
        with mock.patch('apps.integrations.zoom.requests.post', return_value=resp(401)):
            with pytest.raises(ZoomError):
                zoom_client.create_meeting('t', '2026-10-05T09:00:00Z')
            assert dispatch_booking_fulfillment(str(b.id)) is False
        b.refresh_from_db()
        assert b.zoom_meeting_id == ''
        d = FulfillmentDispatch.objects.get(booking=b)
        assert (d.zoom_state, d.last_error) == (St.FAILED, 'zoom: ZoomError')

    def test_delete_meeting_raises_on_token_failure(self, zoom_configured):
        with mock.patch('apps.integrations.zoom.requests.post', return_value=resp(500)), \
                mock.patch('apps.integrations.zoom.requests.delete') as delete:
            with pytest.raises(ZoomError):
                zoom_client.delete_meeting(MEETING)
        delete.assert_not_called()

    def test_the_client_reports_a_missing_status_as_none(self, zoom_configured):
        """Pins the client contract itself (the past-instance check would otherwise mask a 'waiting' default)."""
        with mock.patch('apps.integrations.zoom.requests.post', return_value=token_ok()), \
                mock.patch('apps.integrations.zoom.requests.get', return_value=resp(200, {'id': 1})):
            assert zoom_client.get_meeting_status(MEETING)['status'] is None

    @pytest.mark.parametrize('status', [401, 404, 429, 500])
    def test_the_client_raises_on_a_status_error(self, zoom_configured, status):
        with mock.patch('apps.integrations.zoom.requests.post', return_value=token_ok()), \
                mock.patch('apps.integrations.zoom.requests.get', return_value=resp(status)):
            with pytest.raises(ZoomError):
                zoom_client.get_meeting_status(MEETING)

    def test_the_token_failure_log_has_no_provider_body(self, zoom_configured, caplog):
        with mock.patch('apps.integrations.zoom.requests.post', return_value=resp(401)), caplog.at_level(logging.DEBUG):
            with pytest.raises(ZoomError) as err:
                zoom_client.get_access_token()
        assert 'RAW-PROVIDER-BODY' not in caplog.text and 'secret@x.test' not in caplog.text
        assert 'RAW-PROVIDER-BODY' not in str(err.value)

    def test_without_credentials_simulation_needs_the_explicit_setting(self, settings):
        settings.ZOOM_SIMULATE_WITHOUT_CREDENTIALS = False
        with mock.patch('apps.integrations.zoom.requests.post') as post:
            for call in (lambda: zoom_client.create_meeting('t', '2026-10-05T09:00:00Z'),
                         lambda: zoom_client.get_meeting_status(MEETING), lambda: zoom_client.delete_meeting(MEETING),
                         lambda: zoom_client.get_past_instances(MEETING)):
                with pytest.raises(ZoomError):
                    call()
        post.assert_not_called()

    def test_local_simulation_still_works_without_credentials(self, simulated_zoom):
        room = zoom_client.create_meeting('t', '2026-10-05T09:00:00Z')
        assert room['meeting_id'] and room['join_url'].startswith('https://zoom.us/j/')
        assert zoom_client.get_past_instances(MEETING) == []

    def test_production_settings_never_simulate(self):
        from importlib import import_module
        assert import_module('config.settings.base').ZOOM_SIMULATE_WITHOUT_CREDENTIALS is False


# ====================================================================== m3: a finished meeting reverts to 'waiting'
@pytest.mark.django_db
class TestPastInstances:
    def get_by_url(self, status_payload, past):
        def get(url, **kwargs):
            if '/past_meetings/' in url:
                return past
            return resp(200, status_payload)
        return get

    def test_waiting_with_a_past_instance_is_unknown(self, zoom_configured):
        from apps.bookings.services.attendance_probe import probe_meeting
        get = self.get_by_url({'status': 'waiting'}, resp(200, {'meetings': [{'uuid': 'abc', 'start_time': 'x'}]}))
        with mock.patch('apps.integrations.zoom.requests.post', return_value=token_ok()), \
                mock.patch('apps.integrations.zoom.requests.get', side_effect=get):
            assert probe_meeting(MEETING) == 'unknown'

    def test_waiting_without_past_instances_is_not_started(self, zoom_configured):
        from apps.bookings.services.attendance_probe import probe_meeting
        get = self.get_by_url({'status': 'waiting'}, resp(200, {'meetings': []}))
        with mock.patch('apps.integrations.zoom.requests.post', return_value=token_ok()), \
                mock.patch('apps.integrations.zoom.requests.get', side_effect=get):
            assert probe_meeting(MEETING) == 'not_started'

    @pytest.mark.parametrize('past', [resp(404), resp(500), resp(200, {'meetings': 'garbage'})])
    def test_an_unclear_past_instance_answer_is_unknown(self, zoom_configured, past):
        from apps.bookings.services.attendance_probe import probe_meeting
        with mock.patch('apps.integrations.zoom.requests.post', return_value=token_ok()), \
                mock.patch('apps.integrations.zoom.requests.get', side_effect=self.get_by_url({'status': 'waiting'}, past)):
            assert probe_meeting(MEETING) == 'unknown'


# ====================================================================== M1: calendar step fenced like the Zoom step
@pytest.fixture
def gcal_tutor(teacher_user):
    teacher_user.user.google_calendar_token = {'access_token': 'tok'}
    teacher_user.user.save(update_fields=['google_calendar_token'])
    return teacher_user


@pytest.mark.django_db
class TestCalendarFence:
    def test_the_sync_returns_the_event_id_without_saving(self, gcal_tutor, student_user):
        from apps.integrations.google_calendar import sync_booking_to_teacher_gcal
        b = confirmed(gcal_tutor, student_user)
        with mock.patch('apps.integrations.google_calendar.requests.post', return_value=resp(200, {'id': 'evt-1'})), \
                mock.patch.object(Booking, 'save') as save:
            assert sync_booking_to_teacher_gcal(b) == 'evt-1'
        save.assert_not_called()

    def test_the_event_id_is_stored_under_the_lock(self, gcal_tutor, student_user):
        b = confirmed(gcal_tutor, student_user)
        with mock.patch.object(zoom_client, 'create_meeting', return_value=NEW_MEETING), \
                mock.patch('apps.bookings.services.fulfillment.sync_booking_to_teacher_gcal', return_value='evt-1'):
            assert dispatch_booking_fulfillment(str(b.id)) is True
        b.refresh_from_db()
        assert b.teacher_gcal_event_id == 'evt-1'

    def test_the_event_id_is_saved_with_update_fields(self, gcal_tutor, student_user):
        b = confirmed(gcal_tutor, student_user)
        Booking.objects.filter(pk=b.pk).update(zoom_meeting_id=MEETING)
        with mock.patch('apps.bookings.services.fulfillment.sync_booking_to_teacher_gcal', return_value='evt-1'), \
                mock.patch.object(Booking, 'save', autospec=True, side_effect=Booking.save) as save:
            assert dispatch_booking_fulfillment(str(b.id)) is True
        assert save.call_args_list and all(c.kwargs.get('update_fields') for c in save.call_args_list)

    @pytest.mark.parametrize('race', ['cancel', 'reschedule'])
    def test_an_event_created_for_a_lesson_that_changed_meanwhile_is_deleted(self, gcal_tutor, student_user, race):
        from apps.bookings.services.fulfillment import reset_for_reprovision
        b = confirmed(gcal_tutor, student_user)
        Booking.objects.filter(pk=b.pk).update(zoom_meeting_id=MEETING)

        def sync_while_changed(booking):
            if race == 'cancel':
                Booking.objects.filter(pk=b.pk).update(status=S.CANCELLED_BY_STUDENT)
            else:
                reset_for_reprovision(Booking.objects.get(pk=b.pk))
            return 'evt-race'

        with mock.patch('apps.bookings.services.fulfillment.sync_booking_to_teacher_gcal', side_effect=sync_while_changed), \
                mock.patch.object(cleanup_gcal_event, 'delay') as gcal_cleanup:
            assert dispatch_booking_fulfillment(str(b.id)) is False
        b.refresh_from_db()
        assert b.teacher_gcal_event_id == ''
        gcal_cleanup.assert_called_once_with(str(gcal_tutor.user_id), 'evt-race')

    def test_an_event_already_stored_wins_and_ours_is_deleted(self, gcal_tutor, student_user):
        b = confirmed(gcal_tutor, student_user)
        Booking.objects.filter(pk=b.pk).update(zoom_meeting_id=MEETING)

        def sync_while_event_appears(booking):
            Booking.objects.filter(pk=b.pk).update(teacher_gcal_event_id='evt-old')
            return 'evt-new'

        with mock.patch('apps.bookings.services.fulfillment.sync_booking_to_teacher_gcal', side_effect=sync_while_event_appears), \
                mock.patch.object(cleanup_gcal_event, 'delay') as gcal_cleanup:
            assert dispatch_booking_fulfillment(str(b.id)) is True
        b.refresh_from_db()
        assert b.teacher_gcal_event_id == 'evt-old'
        gcal_cleanup.assert_called_once_with(str(gcal_tutor.user_id), 'evt-new')


# ====================================================================== M2: probe-only presence
@pytest.mark.django_db
def test_probe_only_presence_never_scores_a_student_no_show(teacher_user, student_user):
    b = at_t10(teacher_user, student_user)          # no attendance rows at all: the webhooks may have been lost
    with mock.patch.object(zoom_client, 'get_meeting_status', return_value={'status': 'started'}):
        audit_attendance_and_noshows_task()
    b.refresh_from_db()
    assert b.status == S.IN_PROGRESS
    assert not TeacherStrike.objects.filter(booking=b).exists()


# ====================================================================== M3: lost queue messages
@pytest.mark.django_db
class TestStaleQueued:
    @pytest.mark.parametrize('status', [FD.QUEUED, FD.PENDING])
    def test_a_stale_queued_dispatch_is_re_dispatched(self, teacher_user, student_user, status, settings):
        settings.FULFILLMENT_QUEUED_STALE_SECONDS = 120
        b = confirmed(teacher_user, student_user)
        FulfillmentDispatch.objects.create(booking=b, status=status)
        FulfillmentDispatch.objects.filter(booking=b).update(updated_at=timezone.now() - timedelta(seconds=121))
        with mock.patch.object(zoom_client, 'create_meeting', return_value=NEW_MEETING):
            assert retry_fulfillment_dispatches_task()['redispatched_count'] == 1
        assert FulfillmentDispatch.objects.get(booking=b).status == FD.SUCCEEDED

    def test_a_fresh_queued_dispatch_is_left_to_its_message(self, teacher_user, student_user):
        b = confirmed(teacher_user, student_user)
        FulfillmentDispatch.objects.create(booking=b, status=FD.QUEUED)
        assert retry_fulfillment_dispatches_task()['redispatched_count'] == 0


# ====================================================================== M4: retry cadence, terminal policy, admin re-queue
@pytest.mark.django_db
class TestRetryCadence:
    def test_a_retryable_failure_schedules_the_next_attempt_with_backoff(self, teacher_user, student_user, settings):
        settings.FULFILLMENT_RETRY_SECONDS = 30
        b = confirmed(teacher_user, student_user)
        before = timezone.now()
        with mock.patch.object(zoom_client, 'create_meeting', side_effect=ZoomError('down')), \
                mock.patch.object(dispatch_booking_fulfillment, 'apply_async') as schedule:
            dispatch_booking_fulfillment(str(b.id))
        d = FulfillmentDispatch.objects.get(booking=b)
        countdown = schedule.call_args.kwargs['countdown']
        assert schedule.call_args.kwargs['args'] == [str(b.id)]
        assert 24 <= countdown <= 37                                      # 30 s +-20 % jitter (+1 s margin)
        assert before + timedelta(seconds=23) <= d.next_retry_at <= timezone.now() + timedelta(seconds=37)

    def test_the_backoff_grows_with_attempts_and_is_capped(self):
        from apps.bookings.services.fulfillment import retry_delay_seconds
        with mock.patch('apps.bookings.services.fulfillment.random.uniform', return_value=1.0):
            assert [retry_delay_seconds(n, None) for n in (1, 2, 3)] == [30, 60, 120]
            assert retry_delay_seconds(30, None) == 1800
            assert retry_delay_seconds(1, 900) == 900

    def test_after_max_attempts_a_future_lesson_keeps_retrying_with_an_alert(self, teacher_user, student_user,
                                                                             settings, caplog):
        settings.FULFILLMENT_MAX_ATTEMPTS = 1
        b = confirmed(teacher_user, student_user)
        with mock.patch.object(zoom_client, 'create_meeting', side_effect=ZoomError('down')), \
                caplog.at_level(logging.ERROR):
            dispatch_booking_fulfillment(str(b.id))
        assert FulfillmentDispatch.objects.get(booking=b).status == FD.RETRYABLE
        assert f'FULFILMENT NEEDS ATTENTION booking={b.id}' in caplog.text

    def test_after_max_attempts_a_started_lesson_is_terminal(self, teacher_user, student_user, settings):
        settings.FULFILLMENT_MAX_ATTEMPTS = 1
        b = confirmed(teacher_user, student_user, start_in_min=-1)
        with mock.patch.object(zoom_client, 'create_meeting', side_effect=ZoomError('down')):
            dispatch_booking_fulfillment(str(b.id))
        assert FulfillmentDispatch.objects.get(booking=b).status == FD.FAILED


@pytest.mark.django_db
class TestAdminRequeue:
    def run_action(self, user, queryset):
        from apps.payments.admin import FulfillmentDispatchAdmin
        request = RequestFactory().post('/')
        request.user = user
        request._messages = mock.MagicMock()
        FulfillmentDispatchAdmin(FulfillmentDispatch, AdminSite()).requeue_failed(request, queryset)

    def test_staff_requeue_a_failed_dispatch(self, admin_user, teacher_user, student_user, caplog):
        admin_user.is_superuser = True
        admin_user.save(update_fields=['is_superuser'])
        b = confirmed(teacher_user, student_user)
        FulfillmentDispatch.objects.create(booking=b, status=FD.FAILED, attempts=7, zoom_state=St.FAILED)
        ok = confirmed(teacher_user, student_user, 31 * 60)
        FulfillmentDispatch.objects.create(booking=ok, status=FD.SUCCEEDED, attempts=1)
        with mock.patch.object(dispatch_booking_fulfillment, 'delay') as delay, caplog.at_level(logging.WARNING):
            self.run_action(admin_user, FulfillmentDispatch.objects.all())
        d = FulfillmentDispatch.objects.get(booking=b)
        assert (d.status, d.attempts) == (FD.QUEUED, 0)
        assert FulfillmentDispatch.objects.get(booking=ok).status == FD.SUCCEEDED
        delay.assert_called_once_with(str(b.id))
        assert f'booking={b.id}' in caplog.text and f'actor={admin_user.id}' in caplog.text

    def test_a_non_admin_cannot_requeue(self, student_user, teacher_user):
        from django.core.exceptions import PermissionDenied
        b = confirmed(teacher_user, student_user)
        FulfillmentDispatch.objects.create(booking=b, status=FD.FAILED)
        with pytest.raises(PermissionDenied):
            self.run_action(student_user, FulfillmentDispatch.objects.all())
        assert FulfillmentDispatch.objects.get(booking=b).status == FD.FAILED


# ====================================================================== m1: retry_after cannot be bypassed
@pytest.mark.django_db
class TestRetryAfterFence:
    def test_requeue_keeps_the_retry_time_of_a_retryable_row(self, teacher_user, student_user):
        b = confirmed(teacher_user, student_user)
        later = timezone.now() + timedelta(minutes=15)
        FulfillmentDispatch.objects.create(booking=b, status=FD.RETRYABLE, next_retry_at=later)
        with mock.patch.object(dispatch_booking_fulfillment, 'delay'):
            dispatch_fulfillment(str(b.id))                       # e.g. a replayed payment webhook
        assert FulfillmentDispatch.objects.get(booking=b).next_retry_at == later

    def test_a_retryable_row_is_claimed_only_when_due(self, teacher_user, student_user):
        from apps.bookings.services.fulfillment import claim_dispatch
        b = confirmed(teacher_user, student_user)
        FulfillmentDispatch.objects.create(booking=b, status=FD.RETRYABLE,
                                           next_retry_at=timezone.now() + timedelta(minutes=15))
        assert claim_dispatch(b.id) is None
        due(b)
        assert claim_dispatch(b.id)

    def test_a_requeued_retryable_row_is_still_fenced(self, teacher_user, student_user):
        b = confirmed(teacher_user, student_user)
        FulfillmentDispatch.objects.create(booking=b, status=FD.RETRYABLE,
                                           next_retry_at=timezone.now() + timedelta(minutes=15))
        with mock.patch.object(zoom_client, 'create_meeting') as create:
            dispatch_fulfillment(str(b.id))                       # eager: the queued task runs now and must wait
        create.assert_not_called()


# ====================================================================== m5: explicit e-mail success
@pytest.mark.django_db
class TestEmailSuccessIsExplicit:
    @pytest.mark.parametrize('returned,ok', [
        (True, True), (SimpleNamespace(status='sent'), True),
        (None, False), (False, False), ('sent', False), (SimpleNamespace(status='retryable'), False), (1, False),
    ])
    def test_only_true_or_a_sent_result_counts(self, teacher_user, student_user, returned, ok):
        b = confirmed(teacher_user, student_user)
        with mock.patch.object(zoom_client, 'create_meeting', return_value=NEW_MEETING), \
                mock.patch('apps.bookings.services.fulfillment.send_booking_confirmation_email', return_value=returned):
            assert dispatch_booking_fulfillment(str(b.id)) is ok
        assert (FulfillmentDispatch.objects.get(booking=b).email_state == St.DONE) is ok


# ====================================================================== m7: a resolved dispute case is reopened
@pytest.mark.django_db
def test_a_resolved_dispute_case_is_reopened_for_a_new_verdictless_dispute(teacher_user, student_user):
    b = at_t10(teacher_user, student_user, meeting='')
    case = DisputeCase.objects.create(booking=b, student=student_user, teacher=teacher_user, student_statement='old',
                                      status=DisputeCase.Status.RESOLVED, resolution='release_tutor',
                                      resolved_at=timezone.now(), admin_notes='earlier decision')
    audit_attendance_and_noshows_task()
    case.refresh_from_db()
    assert case.status == DisputeCase.Status.OPEN and case.resolution is None and case.resolved_at is None
    assert 'earlier decision' in case.admin_notes and 'no zoom meeting' in case.admin_notes.lower()
