"""
Slice F0, review round 1 (lead's adversarial review), on Daily.co (D5): M1 calendar step unfenced, M2 probe-only presence
is no evidence of student absence, M3 lost queue messages, M4 retry cadence + admin re-queue, m1 retry_after bypass,
m5 explicit e-mail success, m7 resolved DisputeCase reopened. Daily is the `fake_daily` fixture, Google HTTP is mocked at
`requests` (no network).
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
from apps.payments.models import FulfillmentDispatch
from apps.payments.services.webhook_handler import dispatch_fulfillment
from apps.teachers.models import TeacherStrike
from payment_helpers import lesson
from test_f0_fulfilment_probe import at_t10, confirmed, open_room, student_joined

S = Booking.Status
FD = FulfillmentDispatch.Status
St = FulfillmentDispatch.StepState


def resp(status, payload=None):
    r = mock.Mock(status_code=status, text='RAW-PROVIDER-BODY secret@x.test')
    r.json.return_value = payload if payload is not None else {}
    return r


def due(booking):
    FulfillmentDispatch.objects.filter(booking=booking).update(next_retry_at=timezone.now() - timedelta(seconds=1))


# ====================================================================== M1: calendar step fenced like the room step
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
        with mock.patch('apps.bookings.services.fulfillment.sync_booking_to_teacher_gcal', return_value='evt-1'):
            assert dispatch_booking_fulfillment(str(b.id)) is True
        b.refresh_from_db()
        assert b.teacher_gcal_event_id == 'evt-1'

    def test_the_event_id_is_saved_with_update_fields(self, gcal_tutor, student_user):
        b = confirmed(gcal_tutor, student_user)
        with mock.patch('apps.bookings.services.fulfillment.sync_booking_to_teacher_gcal', return_value='evt-1'), \
                mock.patch.object(Booking, 'save', autospec=True, side_effect=Booking.save) as save:
            assert dispatch_booking_fulfillment(str(b.id)) is True
        assert save.call_args_list and all(c.kwargs.get('update_fields') for c in save.call_args_list)

    @pytest.mark.parametrize('race', ['cancel', 'reschedule'])
    def test_an_event_created_for_a_lesson_that_changed_meanwhile_is_deleted(self, gcal_tutor, student_user, race):
        from apps.bookings.services.fulfillment import reset_for_reprovision
        b = confirmed(gcal_tutor, student_user)

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
def test_probe_only_presence_never_scores_a_student_no_show(teacher_user, student_user, fake_daily):
    b = at_t10(teacher_user, student_user)
    student_joined(b)                                  # the student's webhook arrived; the tutor's was lost
    open_room(fake_daily, b, b.teacher.user_id, b.student_id)
    audit_attendance_and_noshows_task()
    b.refresh_from_db()
    assert b.status == S.IN_PROGRESS
    assert not TeacherStrike.objects.filter(booking=b).exists()


# ====================================================================== M3: lost queue messages
@pytest.mark.django_db
class TestStaleQueued:
    @pytest.mark.parametrize('status', [FD.QUEUED, FD.PENDING])
    def test_a_stale_queued_dispatch_is_re_dispatched(self, teacher_user, student_user, status, settings, fake_daily):
        settings.FULFILLMENT_QUEUED_STALE_SECONDS = 120
        b = confirmed(teacher_user, student_user)
        FulfillmentDispatch.objects.create(booking=b, status=status)
        FulfillmentDispatch.objects.filter(booking=b).update(updated_at=timezone.now() - timedelta(seconds=121))
        assert retry_fulfillment_dispatches_task()['redispatched_count'] == 1
        assert FulfillmentDispatch.objects.get(booking=b).status == FD.SUCCEEDED

    def test_a_fresh_queued_dispatch_is_left_to_its_message(self, teacher_user, student_user):
        b = confirmed(teacher_user, student_user)
        FulfillmentDispatch.objects.create(booking=b, status=FD.QUEUED)
        assert retry_fulfillment_dispatches_task()['redispatched_count'] == 0


# ====================================================================== M4: retry cadence, terminal policy, admin re-queue
@pytest.mark.django_db
class TestRetryCadence:
    def test_a_retryable_failure_schedules_the_next_attempt_with_backoff(self, teacher_user, student_user, settings, fake_daily):
        settings.FULFILLMENT_RETRY_SECONDS = 30
        b = confirmed(teacher_user, student_user)
        fake_daily.fail_next('room_create', 500)
        before = timezone.now()
        with mock.patch.object(dispatch_booking_fulfillment, 'apply_async') as schedule:
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
                                                                             settings, caplog, fake_daily):
        settings.FULFILLMENT_MAX_ATTEMPTS = 1
        b = confirmed(teacher_user, student_user)
        fake_daily.fail_next('room_create', 500)
        with caplog.at_level(logging.ERROR):
            dispatch_booking_fulfillment(str(b.id))
        assert FulfillmentDispatch.objects.get(booking=b).status == FD.RETRYABLE
        assert f'FULFILMENT NEEDS ATTENTION booking={b.id}' in caplog.text

    def test_after_max_attempts_a_started_lesson_is_terminal(self, teacher_user, student_user, settings, fake_daily):
        settings.FULFILLMENT_MAX_ATTEMPTS = 1
        b = confirmed(teacher_user, student_user, start_in_min=-1)
        fake_daily.fail_next('room_create', 500)
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
        FulfillmentDispatch.objects.create(booking=b, status=FD.FAILED, attempts=7, room_state=St.FAILED)
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

    def test_a_requeued_retryable_row_is_still_fenced(self, teacher_user, student_user, fake_daily):
        b = confirmed(teacher_user, student_user)
        FulfillmentDispatch.objects.create(booking=b, status=FD.RETRYABLE,
                                           next_retry_at=timezone.now() + timedelta(minutes=15))
        dispatch_fulfillment(str(b.id))                           # eager: the queued task runs now and must wait
        assert fake_daily.requests == []


# ====================================================================== m5: explicit e-mail success
@pytest.mark.django_db
class TestEmailSuccessIsExplicit:
    @pytest.mark.parametrize('returned,ok', [
        (True, True), (SimpleNamespace(status='sent'), True),
        (None, False), (False, False), ('sent', False), (SimpleNamespace(status='retryable'), False), (1, False),
    ])
    def test_only_true_or_a_sent_result_counts(self, teacher_user, student_user, returned, ok):
        b = confirmed(teacher_user, student_user)
        with mock.patch('apps.bookings.services.fulfillment.send_booking_confirmation_email', return_value=returned):
            assert dispatch_booking_fulfillment(str(b.id)) is ok
        assert (FulfillmentDispatch.objects.get(booking=b).email_state == St.DONE) is ok


# ====================================================================== m7: a resolved dispute case is reopened
@pytest.mark.django_db
def test_a_resolved_dispute_case_is_reopened_for_a_new_verdictless_dispute(teacher_user, student_user):
    b = lesson(teacher_user, student_user, -30, status=S.CONFIRMED)        # ended 5 minutes ago, never adjudicated
    case = DisputeCase.objects.create(booking=b, student=student_user, teacher=teacher_user, student_statement='old',
                                      status=DisputeCase.Status.RESOLVED, resolution='release_tutor',
                                      resolved_at=timezone.now(), admin_notes='earlier decision')
    audit_attendance_and_noshows_task()
    case.refresh_from_db()
    assert case.status == DisputeCase.Status.OPEN and case.resolution is None and case.resolved_at is None
    assert 'earlier decision' in case.admin_notes and 'room evidence' in case.admin_notes.lower()
