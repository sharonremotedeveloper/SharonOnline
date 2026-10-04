"""
Slice F0 (docs/PHASE_11_12_EXECUTION_PLAN.md section 2): three money-affecting defects.

A. A reschedule left the lesson without a Zoom room (the completed fulfilment row was skipped) and the T+10 job then scored the
   tutor as a no-show. Now the reschedule resets the dispatch and re-provisions; a lesson without a meeting id is never a no-show.
B. A Zoom error during the T+10 probe counted as "tutor absent". Now the probe is tri-state; `unknown` defers, and an unresolved
   lesson goes to DISPUTED at the end of its window. The HTTP probe runs outside every row lock.
C. Fulfilment races: compare-and-swap claim, status re-check under the row lock, update_fields saves, per-step states,
   terminal FAILED after N attempts, orphaned-meeting cleanup.
"""
import logging
import threading
from datetime import time, timedelta
from unittest import mock

import pytest
import requests
from django.db import DatabaseError, connection
from django.test import TestCase
from django.utils import timezone

from apps.admin_api.models import DisputeCase
from apps.bookings.models import AttendanceAudit, Booking, BookingStatusChange
from apps.bookings.tasks import audit_attendance_and_noshows_task
from apps.integrations.tasks import (
    cleanup_gcal_event, cleanup_zoom_meeting, dispatch_booking_fulfillment, retry_fulfillment_dispatches_task,
)
from apps.integrations.zoom import ZoomError, zoom_client
from apps.payments.models import CreditBundle, FulfillmentDispatch, RefundRequest
from apps.payments.services.webhook_handler import dispatch_fulfillment
from apps.teachers.models import TeacherAvailability, TeacherStrike
from payment_helpers import captured, lesson
from test_reschedule import open_slots, resched

S = Booking.Status
FD = FulfillmentDispatch.Status
H = 60
MEETING = '55500011122'
NEW_MEETING = {'meeting_id': '77700011122', 'join_url': 'https://zoom.us/j/777', 'start_url': 'https://zoom.us/s/777',
               'password': 'pw7'}


def fulfillment():
    from apps.bookings.services import fulfillment as module
    return module


def probe_module():
    from apps.bookings.services import attendance_probe as module
    return module


def on_commit():
    return TestCase.captureOnCommitCallbacks(execute=True)


def at_t10(teacher, student, *, meeting=MEETING, minutes_in=12):
    """A paid, confirmed lesson that started `minutes_in` minutes ago and nobody has joined."""
    b = lesson(teacher, student, -minutes_in, status=S.CONFIRMED)
    Booking.objects.filter(pk=b.pk).update(zoom_meeting_id=meeting)
    b.refresh_from_db()
    return b


def no_penalty(booking):
    """Nothing a tutor no-show would have done happened."""
    assert not TeacherStrike.objects.filter(booking=booking).exists()
    assert not RefundRequest.objects.filter(booking=booking).exists()
    assert not CreditBundle.objects.filter(user=booking.student).exists()
    assert not BookingStatusChange.objects.filter(booking=booking, to_status=S.TEACHER_NO_SHOW).exists()


@pytest.fixture
def tutor(teacher_user):
    TeacherAvailability.objects.all().delete()
    for dow in range(7):
        TeacherAvailability.objects.create(teacher=teacher_user, day_of_week=dow, start_time=time(8, 0),
                                           end_time=time(11, 0), is_active=True)
    return teacher_user


@pytest.fixture
def side_tasks():
    with mock.patch.object(cleanup_zoom_meeting, 'delay') as zoom_cleanup, \
            mock.patch.object(cleanup_gcal_event, 'delay') as gcal_cleanup:
        yield zoom_cleanup, gcal_cleanup


def confirmed(teacher, student, start_in_min=30 * H):
    return lesson(teacher, student, start_in_min, status=S.CONFIRMED)


# ====================================================================== A. reschedule -> new Zoom room
@pytest.mark.django_db
class TestRescheduleReprovisions:
    def test_a_rescheduled_lesson_gets_a_new_meeting_after_commit(self, tutor, student_user, side_tasks):
        zoom_cleanup, _ = side_tasks
        b = captured(tutor, student_user, 30 * H)
        Booking.objects.filter(pk=b.pk).update(zoom_meeting_id='111', zoom_join_url='https://zoom.us/j/111')
        FulfillmentDispatch.objects.update_or_create(booking=b, defaults=dict(
            status=FD.SUCCEEDED, attempts=1, zoom_completed=True, calendar_completed=True, email_completed=True))
        with mock.patch.object(zoom_client, 'create_meeting', return_value=NEW_MEETING) as create, on_commit():
            assert resched(student_user, b, open_slots(tutor)[5]).status_code == 200
        b.refresh_from_db()
        create.assert_called_once()
        assert b.zoom_meeting_id == NEW_MEETING['meeting_id']
        assert b.zoom_join_url == NEW_MEETING['join_url']
        zoom_cleanup.assert_called_once_with('111')                    # the old room is deleted, never orphaned
        assert FulfillmentDispatch.objects.get(booking=b).status == FD.SUCCEEDED

    def test_the_dispatch_is_reset_inside_the_reschedule_transaction(self, tutor, student_user, side_tasks):
        b = captured(tutor, student_user, 30 * H)
        FulfillmentDispatch.objects.update_or_create(booking=b, defaults=dict(
            status=FD.SUCCEEDED, attempts=3, zoom_completed=True, calendar_completed=True, email_completed=True,
            last_error='old'))
        with mock.patch.object(dispatch_booking_fulfillment, 'delay'):
            assert resched(student_user, b, open_slots(tutor)[5]).status_code == 200
        d = FulfillmentDispatch.objects.get(booking=b)
        assert (d.status, d.attempts, d.last_error) == (FD.QUEUED, 0, '')
        assert not (d.zoom_completed or d.calendar_completed or d.email_completed)
        P = FulfillmentDispatch.StepState.PENDING
        assert (d.zoom_state, d.calendar_state, d.email_state) == (P, P, P)

    def test_a_reschedule_without_a_previous_dispatch_row_creates_one(self, tutor, student_user, side_tasks):
        b = captured(tutor, student_user, 30 * H)
        FulfillmentDispatch.objects.filter(booking=b).delete()
        with mock.patch.object(dispatch_booking_fulfillment, 'delay'):
            assert resched(student_user, b, open_slots(tutor)[5]).status_code == 200
        assert FulfillmentDispatch.objects.get(booking=b).status == FD.QUEUED

    def test_the_reschedule_save_only_writes_its_own_columns(self, tutor, student_user, side_tasks):
        b = captured(tutor, student_user, 30 * H)
        with mock.patch.object(dispatch_booking_fulfillment, 'delay'), \
                mock.patch.object(Booking, 'save', autospec=True, side_effect=Booking.save) as save:
            assert resched(student_user, b, open_slots(tutor)[5]).status_code == 200
        assert all(call.kwargs.get('update_fields') for call in save.call_args_list)


@pytest.mark.django_db
class TestNoMeetingIsNeverANoShow:
    def test_t10_without_a_meeting_id_goes_to_disputed_not_teacher_no_show(self, teacher_user, student_user):
        b = at_t10(teacher_user, student_user, meeting='')
        with mock.patch.object(zoom_client, 'get_meeting_status') as probe:
            res = audit_attendance_and_noshows_task()
        probe.assert_not_called()
        b.refresh_from_db()
        assert b.status == S.DISPUTED
        assert res['teacher_no_shows'] == 0
        no_penalty(b)
        assert DisputeCase.objects.filter(booking=b, status=DisputeCase.Status.OPEN).exists()
        change = BookingStatusChange.objects.get(booking=b, to_status=S.DISPUTED)
        assert 'no zoom meeting' in change.reason.lower()

    def test_a_no_meeting_dispute_is_idempotent(self, teacher_user, student_user):
        b = at_t10(teacher_user, student_user, meeting='')
        audit_attendance_and_noshows_task()
        audit_attendance_and_noshows_task()
        assert DisputeCase.objects.filter(booking=b).count() == 1
        assert BookingStatusChange.objects.filter(booking=b, to_status=S.DISPUTED).count() == 1

    def test_a_lesson_that_ends_without_a_meeting_is_disputed_without_penalty(self, teacher_user, student_user):
        b = lesson(teacher_user, student_user, -30, status=S.CONFIRMED)        # ended 5 minutes ago, never adjudicated
        audit_attendance_and_noshows_task()
        b.refresh_from_db()
        assert b.status == S.DISPUTED
        no_penalty(b)
        assert DisputeCase.objects.filter(booking=b).exists()


# ====================================================================== B. tri-state probe
class TestProbeMapping:
    @pytest.mark.parametrize('payload,expected', [
        ({'status': 'started'}, 'started'),
        ({'status': 'waiting'}, 'not_started'),
        ({'status': 'error'}, 'unknown'),
        ({'status': 'finished'}, 'unknown'),
        ({'status': None}, 'unknown'),
        ({}, 'unknown'),
        (None, 'unknown'),
        ('started', 'unknown'),
    ])
    def test_status_mapping(self, payload, expected):
        with mock.patch.object(zoom_client, 'get_meeting_status', return_value=payload):
            assert probe_module().probe_meeting(MEETING) == expected

    @pytest.mark.parametrize('exc', [requests.Timeout('t'), requests.ConnectionError('c'), ZoomError('401'), ValueError('x')])
    def test_any_failure_is_unknown(self, exc):
        with mock.patch.object(zoom_client, 'get_meeting_status', side_effect=exc):
            assert probe_module().probe_meeting(MEETING) == 'unknown'

    def test_the_probe_log_carries_ids_only(self, caplog):
        with mock.patch.object(zoom_client, 'get_meeting_status', side_effect=ZoomError('token SECRET-123 rejected')), \
                caplog.at_level(logging.WARNING):
            probe_module().probe_meeting(MEETING)
        assert 'SECRET-123' not in caplog.text and MEETING in caplog.text


@pytest.mark.django_db
class TestProbeUnknownDefers:
    @pytest.mark.parametrize('kwargs', [
        {'side_effect': requests.Timeout('slow')},
        {'side_effect': ZoomError('HTTP 401')},
        {'return_value': {'status': 'error', 'participant_count': 0}},
    ])
    def test_a_probe_failure_is_never_a_no_show(self, teacher_user, student_user, kwargs):
        b = at_t10(teacher_user, student_user)
        with mock.patch.object(zoom_client, 'get_meeting_status', **kwargs):
            res = audit_attendance_and_noshows_task()
        b.refresh_from_db()
        assert b.status == S.CONFIRMED                  # deferred to the next run
        assert res['teacher_no_shows'] == 0
        no_penalty(b)

    def test_unknown_then_not_started_is_a_no_show_on_a_later_run(self, teacher_user, student_user):
        b = at_t10(teacher_user, student_user)
        with mock.patch.object(zoom_client, 'get_meeting_status', side_effect=requests.Timeout('slow')):
            audit_attendance_and_noshows_task()
        with mock.patch.object(zoom_client, 'get_meeting_status', return_value={'status': 'waiting'}):
            audit_attendance_and_noshows_task()
        b.refresh_from_db()
        assert b.status == S.TEACHER_NO_SHOW
        assert TeacherStrike.objects.filter(booking=b).count() == 1

    def test_unknown_until_the_lesson_ends_goes_to_disputed(self, teacher_user, student_user):
        b = at_t10(teacher_user, student_user)
        with mock.patch.object(zoom_client, 'get_meeting_status', side_effect=requests.Timeout('slow')):
            audit_attendance_and_noshows_task()
            start = timezone.now() - timedelta(minutes=30)
            Booking.objects.filter(pk=b.pk).update(start_time_utc=start, end_time_utc=start + timedelta(minutes=25))
            audit_attendance_and_noshows_task()
        b.refresh_from_db()
        assert b.status == S.DISPUTED
        no_penalty(b)
        assert DisputeCase.objects.filter(booking=b, status=DisputeCase.Status.OPEN).exists()
        reason = BookingStatusChange.objects.get(booking=b, to_status=S.DISPUTED).reason.lower()
        assert 'verdict' in reason

    def test_not_started_is_still_a_no_show(self, teacher_user, student_user):
        b = at_t10(teacher_user, student_user)
        with mock.patch.object(zoom_client, 'get_meeting_status', return_value={'status': 'waiting'}):
            res = audit_attendance_and_noshows_task()
        b.refresh_from_db()
        assert b.status == S.TEACHER_NO_SHOW and res['teacher_no_shows'] == 1

    def test_started_still_prevents_the_no_show(self, teacher_user, student_user):
        b = at_t10(teacher_user, student_user)
        AttendanceAudit.objects.create(booking=b, participant_email=student_user.email, zoom_session_id='s1',
                                       classification=AttendanceAudit.Classification.STUDENT,
                                       join_time_utc=b.start_time_utc)
        with mock.patch.object(zoom_client, 'get_meeting_status', return_value={'status': 'started'}):
            audit_attendance_and_noshows_task()
        b.refresh_from_db()
        assert b.status == S.IN_PROGRESS
        no_penalty(b)

    def test_a_meeting_replaced_during_the_probe_is_re_probed_not_judged(self, teacher_user, student_user):
        b = at_t10(teacher_user, student_user)

        def replace_meeting(meeting_id):
            Booking.objects.filter(pk=b.pk).update(zoom_meeting_id='OTHER-MEETING')
            return {'status': 'waiting'}

        with mock.patch.object(zoom_client, 'get_meeting_status', side_effect=replace_meeting):
            audit_attendance_and_noshows_task()
        b.refresh_from_db()
        assert b.status == S.CONFIRMED
        no_penalty(b)

    def test_a_status_change_during_the_probe_is_respected(self, teacher_user, student_user):
        b = at_t10(teacher_user, student_user)

        def tutor_cancelled(meeting_id):
            Booking.objects.filter(pk=b.pk).update(status=S.CANCELLED_BY_TEACHER)
            return {'status': 'waiting'}

        with mock.patch.object(zoom_client, 'get_meeting_status', side_effect=tutor_cancelled):
            audit_attendance_and_noshows_task()
        b.refresh_from_db()
        assert b.status == S.CANCELLED_BY_TEACHER
        assert not TeacherStrike.objects.filter(booking=b).exists()

    def test_the_probe_budget_bounds_the_run(self, teacher_user, student_user, settings):
        settings.ATTENDANCE_PROBE_BUDGET_SECONDS = 0
        b = at_t10(teacher_user, student_user)
        with mock.patch.object(zoom_client, 'get_meeting_status', return_value={'status': 'waiting'}) as probe:
            audit_attendance_and_noshows_task()
        probe.assert_not_called()
        b.refresh_from_db()
        assert b.status == S.CONFIRMED


@pytest.fixture
def price_catalog(db):
    """Transactional tests run after another transactional test may find the migration-seeded catalog flushed."""
    from decimal import Decimal
    from apps.payments.models import LessonPrice
    for currency, amount in (('USD', '9.00'), ('EUR', '8.50'), ('ZAR', '162.00'), ('JPY', '1350.00')):
        LessonPrice.objects.get_or_create(currency=currency, defaults={'amount': Decimal(amount)})


@pytest.mark.django_db(transaction=True)
def test_the_http_probe_runs_outside_any_transaction(price_catalog, teacher_user, student_user):
    b = at_t10(teacher_user, student_user)
    seen = []

    def probe(meeting_id):
        seen.append(connection.in_atomic_block)
        return {'status': 'waiting'}

    with mock.patch.object(zoom_client, 'get_meeting_status', side_effect=probe):
        audit_attendance_and_noshows_task()
    assert seen == [False]
    b.refresh_from_db()
    assert b.status == S.TEACHER_NO_SHOW


# ====================================================================== C. fulfilment races
@pytest.mark.django_db
class TestClaim:
    def test_only_one_claim_wins(self, teacher_user, student_user):
        b = confirmed(teacher_user, student_user)
        FulfillmentDispatch.objects.create(booking=b, status=FD.QUEUED)
        first = fulfillment().claim_dispatch(b.id)
        second = fulfillment().claim_dispatch(b.id)
        assert first and second is None
        d = FulfillmentDispatch.objects.get(booking=b)
        assert (d.status, d.attempts, d.claim_token) == (FD.RUNNING, 1, first)

    @pytest.mark.parametrize('status', [FD.PENDING, FD.QUEUED, FD.RETRYABLE])
    def test_claimable_statuses(self, teacher_user, student_user, status):
        b = confirmed(teacher_user, student_user)
        FulfillmentDispatch.objects.create(booking=b, status=status)
        assert fulfillment().claim_dispatch(b.id)

    @pytest.mark.parametrize('status', [FD.SUCCEEDED, FD.FAILED, FD.RUNNING])
    def test_unclaimable_statuses(self, teacher_user, student_user, status):
        b = confirmed(teacher_user, student_user)
        FulfillmentDispatch.objects.create(booking=b, status=status, claimed_at=timezone.now())
        assert fulfillment().claim_dispatch(b.id) is None

    def test_a_stale_running_claim_is_reclaimable_after_the_lease(self, teacher_user, student_user, settings):
        settings.FULFILLMENT_LEASE_SECONDS = 600
        b = confirmed(teacher_user, student_user)
        FulfillmentDispatch.objects.create(booking=b, status=FD.RUNNING, claim_token='old',
                                           claimed_at=timezone.now() - timedelta(seconds=599))
        assert fulfillment().claim_dispatch(b.id) is None
        FulfillmentDispatch.objects.filter(booking=b).update(claimed_at=timezone.now() - timedelta(seconds=601))
        token = fulfillment().claim_dispatch(b.id)
        assert token and token != 'old'

    def test_a_concurrent_run_exits_without_touching_zoom(self, teacher_user, student_user):
        b = confirmed(teacher_user, student_user)
        FulfillmentDispatch.objects.create(booking=b, status=FD.RUNNING, claim_token='other', claimed_at=timezone.now())
        with mock.patch.object(zoom_client, 'create_meeting') as create:
            assert dispatch_booking_fulfillment(str(b.id)) is False
        create.assert_not_called()


@pytest.mark.django_db
class TestFulfilmentRun:
    def test_happy_path_records_per_step_states(self, teacher_user, student_user):
        b = confirmed(teacher_user, student_user)
        with mock.patch.object(zoom_client, 'create_meeting', return_value=NEW_MEETING):
            assert dispatch_booking_fulfillment(str(b.id)) is True
        d = FulfillmentDispatch.objects.get(booking=b)
        St = FulfillmentDispatch.StepState
        assert (d.status, d.zoom_state, d.calendar_state, d.email_state) == (FD.SUCCEEDED, St.DONE, St.SKIPPED, St.DONE)
        assert d.claim_token == ''
        b.refresh_from_db()
        assert b.zoom_meeting_id == NEW_MEETING['meeting_id']

    def test_no_google_token_is_skipped_not_done(self, teacher_user, student_user):
        b = confirmed(teacher_user, student_user)
        with mock.patch.object(zoom_client, 'create_meeting', return_value=NEW_MEETING), \
                mock.patch('apps.integrations.google_calendar.requests.post') as google:
            dispatch_booking_fulfillment(str(b.id))
        google.assert_not_called()
        assert FulfillmentDispatch.objects.get(booking=b).calendar_state == FulfillmentDispatch.StepState.SKIPPED

    def test_a_calendar_sync_that_returns_nothing_is_a_failure(self, teacher_user, student_user):
        teacher_user.user.google_calendar_token = {'access_token': 'tok'}
        teacher_user.user.save(update_fields=['google_calendar_token'])
        b = confirmed(teacher_user, student_user)
        with mock.patch.object(zoom_client, 'create_meeting', return_value=NEW_MEETING), \
                mock.patch('apps.bookings.services.fulfillment.sync_booking_to_teacher_gcal', return_value=''):
            assert dispatch_booking_fulfillment(str(b.id)) is False
        d = FulfillmentDispatch.objects.get(booking=b)
        assert (d.status, d.calendar_state) == (FD.RETRYABLE, FulfillmentDispatch.StepState.FAILED)
        assert d.next_retry_at is not None

    def test_a_calendar_event_id_is_done(self, teacher_user, student_user):
        teacher_user.user.google_calendar_token = {'access_token': 'tok'}
        teacher_user.user.save(update_fields=['google_calendar_token'])
        b = confirmed(teacher_user, student_user)
        with mock.patch.object(zoom_client, 'create_meeting', return_value=NEW_MEETING), \
                mock.patch('apps.bookings.services.fulfillment.sync_booking_to_teacher_gcal', return_value='evt-9'):
            assert dispatch_booking_fulfillment(str(b.id)) is True
        assert FulfillmentDispatch.objects.get(booking=b).calendar_state == FulfillmentDispatch.StepState.DONE

    def test_an_email_that_was_not_sent_is_a_failure(self, teacher_user, student_user):
        b = confirmed(teacher_user, student_user)
        with mock.patch.object(zoom_client, 'create_meeting', return_value=NEW_MEETING), \
                mock.patch('apps.bookings.services.fulfillment.send_booking_confirmation_email', return_value=False):
            assert dispatch_booking_fulfillment(str(b.id)) is False
        d = FulfillmentDispatch.objects.get(booking=b)
        assert (d.status, d.email_state) == (FD.RETRYABLE, FulfillmentDispatch.StepState.FAILED)

    def test_a_retry_does_not_repeat_finished_steps(self, teacher_user, student_user):
        b = confirmed(teacher_user, student_user)
        with mock.patch.object(zoom_client, 'create_meeting', return_value=NEW_MEETING) as create, \
                mock.patch('apps.bookings.services.fulfillment.send_booking_confirmation_email',
                           side_effect=[False, True]) as mail:
            dispatch_booking_fulfillment(str(b.id))
            assert dispatch_booking_fulfillment(str(b.id)) is True
        assert create.call_count == 1 and mail.call_count == 2

    def test_a_cancelled_booking_is_not_provisioned(self, teacher_user, student_user):
        b = confirmed(teacher_user, student_user)
        Booking.objects.filter(pk=b.pk).update(status=S.CANCELLED_BY_STUDENT)
        with mock.patch.object(zoom_client, 'create_meeting') as create:
            assert dispatch_booking_fulfillment(str(b.id)) is False
        create.assert_not_called()
        assert FulfillmentDispatch.objects.get(booking=b).status == FD.ABANDONED

    def test_a_meeting_created_for_a_booking_cancelled_meanwhile_is_deleted(self, teacher_user, student_user, side_tasks):
        zoom_cleanup, _ = side_tasks
        b = confirmed(teacher_user, student_user)

        def create_while_student_cancels(**kwargs):
            Booking.objects.filter(pk=b.pk).update(status=S.CANCELLED_BY_STUDENT)
            return NEW_MEETING

        with mock.patch.object(zoom_client, 'create_meeting', side_effect=create_while_student_cancels):
            assert dispatch_booking_fulfillment(str(b.id)) is False
        b.refresh_from_db()
        assert b.status == S.CANCELLED_BY_STUDENT             # the stale instance never overwrote the cancellation
        assert b.zoom_meeting_id == ''
        zoom_cleanup.assert_called_once_with(NEW_MEETING['meeting_id'])
        assert FulfillmentDispatch.objects.get(booking=b).status == FD.ABANDONED

    def test_the_meeting_save_does_not_overwrite_concurrent_changes(self, teacher_user, student_user):
        b = confirmed(teacher_user, student_user)

        def create_while_reminder_flagged(**kwargs):
            Booking.objects.filter(pk=b.pk).update(reminder_24h_sent=True, student_review='kept')
            return NEW_MEETING

        with mock.patch.object(zoom_client, 'create_meeting', side_effect=create_while_reminder_flagged):
            assert dispatch_booking_fulfillment(str(b.id)) is True
        b.refresh_from_db()
        assert b.reminder_24h_sent is True and b.student_review == 'kept'
        assert b.zoom_meeting_id == NEW_MEETING['meeting_id']

    def test_a_meeting_whose_save_failed_is_deleted(self, teacher_user, student_user, side_tasks):
        zoom_cleanup, _ = side_tasks
        b = confirmed(teacher_user, student_user)
        with mock.patch.object(zoom_client, 'create_meeting', return_value=NEW_MEETING), \
                mock.patch.object(Booking, 'save', side_effect=DatabaseError('lost')):
            assert dispatch_booking_fulfillment(str(b.id)) is False
        zoom_cleanup.assert_called_once_with(NEW_MEETING['meeting_id'])
        d = FulfillmentDispatch.objects.get(booking=b)
        assert (d.status, d.zoom_state) == (FD.RETRYABLE, FulfillmentDispatch.StepState.FAILED)

    def test_a_run_whose_claim_was_reset_by_a_reschedule_keeps_nothing(self, teacher_user, student_user, side_tasks):
        zoom_cleanup, _ = side_tasks
        b = confirmed(teacher_user, student_user)

        def create_while_rescheduled(**kwargs):
            fulfillment().reset_for_reprovision(Booking.objects.get(pk=b.pk))
            return NEW_MEETING

        with mock.patch.object(zoom_client, 'create_meeting', side_effect=create_while_rescheduled):
            assert dispatch_booking_fulfillment(str(b.id)) is False
        b.refresh_from_db()
        assert b.zoom_meeting_id == ''
        zoom_cleanup.assert_called_once_with(NEW_MEETING['meeting_id'])
        assert FulfillmentDispatch.objects.get(booking=b).status == FD.QUEUED       # the new generation still runs

    def test_an_existing_meeting_is_reused_not_duplicated(self, teacher_user, student_user):
        b = confirmed(teacher_user, student_user)
        Booking.objects.filter(pk=b.pk).update(zoom_meeting_id=MEETING)
        with mock.patch.object(zoom_client, 'create_meeting') as create:
            assert dispatch_booking_fulfillment(str(b.id)) is True
        create.assert_not_called()

    def test_last_error_names_the_step_and_error_type_only(self, teacher_user, student_user):
        b = confirmed(teacher_user, student_user)
        with mock.patch.object(zoom_client, 'create_meeting', side_effect=ZoomError('student@test.com secret')):
            dispatch_booking_fulfillment(str(b.id))
        d = FulfillmentDispatch.objects.get(booking=b)
        assert d.last_error == 'zoom: ZoomError'

    def test_terminal_failed_after_max_attempts_with_an_alert(self, teacher_user, student_user, settings, caplog):
        settings.FULFILLMENT_MAX_ATTEMPTS = 2
        b = confirmed(teacher_user, student_user)
        with mock.patch.object(zoom_client, 'create_meeting', side_effect=ZoomError('down')), \
                caplog.at_level(logging.ERROR):
            dispatch_booking_fulfillment(str(b.id))
            assert FulfillmentDispatch.objects.get(booking=b).status == FD.RETRYABLE
            dispatch_booking_fulfillment(str(b.id))
        d = FulfillmentDispatch.objects.get(booking=b)
        assert (d.status, d.attempts, d.next_retry_at) == (FD.FAILED, 2, None)
        assert f'FULFILMENT FAILED booking={b.id}' in caplog.text
        assert 'down' not in caplog.text

    def test_a_failed_dispatch_is_not_requeued_or_reclaimed(self, teacher_user, student_user):
        b = confirmed(teacher_user, student_user)
        FulfillmentDispatch.objects.create(booking=b, status=FD.FAILED, attempts=5)
        with mock.patch.object(dispatch_booking_fulfillment, 'delay') as delay:
            dispatch_fulfillment(str(b.id))
        delay.assert_not_called()
        assert FulfillmentDispatch.objects.get(booking=b).status == FD.FAILED

    def test_dispatch_does_not_requeue_a_running_claim(self, teacher_user, student_user):
        b = confirmed(teacher_user, student_user)
        FulfillmentDispatch.objects.create(booking=b, status=FD.RUNNING, claim_token='t', claimed_at=timezone.now())
        with mock.patch.object(dispatch_booking_fulfillment, 'delay') as delay:
            dispatch_fulfillment(str(b.id))
        delay.assert_not_called()
        assert FulfillmentDispatch.objects.get(booking=b).status == FD.RUNNING

    def test_the_sweep_reclaims_a_stale_running_dispatch(self, teacher_user, student_user, settings):
        settings.FULFILLMENT_LEASE_SECONDS = 600
        b = confirmed(teacher_user, student_user)
        FulfillmentDispatch.objects.create(booking=b, status=FD.RUNNING, claim_token='dead-worker',
                                           claimed_at=timezone.now() - timedelta(minutes=11))
        with mock.patch.object(zoom_client, 'create_meeting', return_value=NEW_MEETING):
            assert retry_fulfillment_dispatches_task()['redispatched_count'] == 1
        assert FulfillmentDispatch.objects.get(booking=b).status == FD.SUCCEEDED

    def test_the_sweep_leaves_a_live_running_dispatch_alone(self, teacher_user, student_user):
        b = confirmed(teacher_user, student_user)
        FulfillmentDispatch.objects.create(booking=b, status=FD.RUNNING, claim_token='busy', claimed_at=timezone.now())
        assert retry_fulfillment_dispatches_task()['redispatched_count'] == 0


@pytest.mark.django_db
class TestMutationGuards:
    """Tests added after the F0 mutation run (docs/mutation/F0.md) to pin lines no behaviour test exercised."""

    def test_a_claim_taken_over_by_another_worker_keeps_nothing(self, teacher_user, student_user, side_tasks):
        zoom_cleanup, _ = side_tasks
        b = confirmed(teacher_user, student_user)

        def create_while_reclaimed(**kwargs):        # lease expired, another worker now holds RUNNING with its own token
            FulfillmentDispatch.objects.filter(booking=b).update(claim_token='other-worker')
            return NEW_MEETING

        with mock.patch.object(zoom_client, 'create_meeting', side_effect=create_while_reclaimed):
            assert dispatch_booking_fulfillment(str(b.id)) is False
        b.refresh_from_db()
        assert b.zoom_meeting_id == ''
        zoom_cleanup.assert_called_once_with(NEW_MEETING['meeting_id'])
        assert FulfillmentDispatch.objects.get(booking=b).claim_token == 'other-worker'

    def test_the_meeting_is_saved_with_update_fields(self, teacher_user, student_user):
        b = confirmed(teacher_user, student_user)
        with mock.patch.object(zoom_client, 'create_meeting', return_value=NEW_MEETING), \
                mock.patch.object(Booking, 'save', autospec=True, side_effect=Booking.save) as save:
            assert dispatch_booking_fulfillment(str(b.id)) is True
        assert save.call_args_list and all(c.kwargs.get('update_fields') for c in save.call_args_list)

    def test_a_room_stored_meanwhile_wins_and_ours_is_deleted(self, teacher_user, student_user, side_tasks):
        zoom_cleanup, _ = side_tasks
        b = confirmed(teacher_user, student_user)

        def create_while_room_appears(**kwargs):
            Booking.objects.filter(pk=b.pk).update(zoom_meeting_id='EXISTING')
            return NEW_MEETING

        with mock.patch.object(zoom_client, 'create_meeting', side_effect=create_while_room_appears):
            assert dispatch_booking_fulfillment(str(b.id)) is True
        b.refresh_from_db()
        assert b.zoom_meeting_id == 'EXISTING'
        zoom_cleanup.assert_called_once_with(NEW_MEETING['meeting_id'])

    def test_a_retry_does_not_resync_a_finished_calendar_step(self, teacher_user, student_user):
        teacher_user.user.google_calendar_token = {'access_token': 'tok'}
        teacher_user.user.save(update_fields=['google_calendar_token'])
        b = confirmed(teacher_user, student_user)
        with mock.patch.object(zoom_client, 'create_meeting', return_value=NEW_MEETING), \
                mock.patch('apps.bookings.services.fulfillment.sync_booking_to_teacher_gcal', return_value='evt') as sync, \
                mock.patch('apps.bookings.services.fulfillment.send_booking_confirmation_email', side_effect=[False, True]):
            dispatch_booking_fulfillment(str(b.id))
            assert dispatch_booking_fulfillment(str(b.id)) is True
        assert sync.call_count == 1

    def test_adjudication_rechecks_the_status_under_the_lock(self, teacher_user, student_user):
        """Race between the candidate query and the row lock: a lesson cancelled in between is left alone."""
        b = at_t10(teacher_user, student_user)
        Booking.objects.filter(pk=b.pk).update(status=S.CANCELLED_BY_TEACHER)
        module = probe_module()
        results = {'teacher_no_shows': 0, 'student_no_shows': 0}
        with mock.patch.object(module, '_t10_candidates', lambda now: Booking.objects.filter(pk=b.pk)):
            module.adjudicate_t10(timezone.now(), {b.id: (MEETING, module.NOT_STARTED)}, results)
        b.refresh_from_db()
        assert b.status == S.CANCELLED_BY_TEACHER and results['teacher_no_shows'] == 0
        assert not TeacherStrike.objects.filter(booking=b).exists()

    def test_an_in_progress_lesson_is_not_probed(self, teacher_user, student_user):
        b = at_t10(teacher_user, student_user)
        Booking.objects.filter(pk=b.pk).update(status=S.IN_PROGRESS)
        with mock.patch.object(zoom_client, 'get_meeting_status') as probe:
            probe_module().probe_t10_candidates(timezone.now())
        probe.assert_not_called()


def _email_error(status=None, retry_after=None):
    """Shaped like N1c's EmailDeliveryError(.result=EmailResult) / EmailPermanentError, built from today's class."""
    from types import SimpleNamespace
    from apps.integrations.email import EmailDeliveryError
    exc = EmailDeliveryError('provider said no to student@test.com')
    if status is not None:
        exc.result = SimpleNamespace(status=status, retry_after_seconds=retry_after)
    return exc


@pytest.mark.django_db
class TestEmailFailureContract:
    """QA merge requirement (N1c integration): e-mail failures never mark the step done, never re-provision Zoom,
    and a permanent failure is terminal (no endless 5-minute re-queue)."""

    def test_permanent_email_failure_is_terminal_and_alerted(self, teacher_user, student_user, caplog):
        b = confirmed(teacher_user, student_user)
        with mock.patch.object(zoom_client, 'create_meeting', return_value=NEW_MEETING) as create, \
                mock.patch('apps.bookings.services.fulfillment.send_booking_confirmation_email',
                           side_effect=_email_error('failed')) as mail, caplog.at_level(logging.ERROR):
            assert dispatch_booking_fulfillment(str(b.id)) is False
            d = FulfillmentDispatch.objects.get(booking=b)
            St = FulfillmentDispatch.StepState
            assert (d.status, d.zoom_state, d.email_state, d.next_retry_at) == (FD.FAILED, St.DONE, St.FAILED, None)
            assert d.attempts == 1 and d.last_error == 'email: EmailDeliveryError'
            assert f'FULFILMENT FAILED booking={b.id}' in caplog.text and 'student@test.com' not in caplog.text
            assert retry_fulfillment_dispatches_task()['redispatched_count'] == 0
            dispatch_fulfillment(str(b.id))                          # a duplicate webhook does not revive it either
        assert FulfillmentDispatch.objects.get(booking=b).status == FD.FAILED
        assert create.call_count == 1 and mail.call_count == 1

    def test_transient_email_failure_retries_without_reprovisioning_zoom(self, teacher_user, student_user):
        b = confirmed(teacher_user, student_user)
        with mock.patch.object(zoom_client, 'create_meeting', return_value=NEW_MEETING) as create, \
                mock.patch('apps.bookings.services.fulfillment.send_booking_confirmation_email',
                           side_effect=[_email_error('retryable'), True]) as mail:
            assert dispatch_booking_fulfillment(str(b.id)) is False
            d = FulfillmentDispatch.objects.get(booking=b)
            assert (d.status, d.email_state) == (FD.RETRYABLE, FulfillmentDispatch.StepState.FAILED)
            assert not d.email_completed
            FulfillmentDispatch.objects.filter(booking=b).update(next_retry_at=timezone.now() - timedelta(seconds=1))
            assert retry_fulfillment_dispatches_task()['redispatched_count'] == 1
        d = FulfillmentDispatch.objects.get(booking=b)
        assert (d.status, d.email_state) == (FD.SUCCEEDED, FulfillmentDispatch.StepState.DONE)
        assert create.call_count == 1 and mail.call_count == 2

    def test_retry_after_is_honoured(self, teacher_user, student_user, settings):
        settings.FULFILLMENT_RETRY_SECONDS = 60
        b = confirmed(teacher_user, student_user)
        before = timezone.now()
        with mock.patch.object(zoom_client, 'create_meeting', return_value=NEW_MEETING), \
                mock.patch('apps.bookings.services.fulfillment.send_booking_confirmation_email',
                           side_effect=_email_error('in_flight', retry_after=900)):
            dispatch_booking_fulfillment(str(b.id))
        d = FulfillmentDispatch.objects.get(booking=b)
        assert d.status == FD.RETRYABLE
        assert before + timedelta(seconds=899) <= d.next_retry_at <= timezone.now() + timedelta(seconds=901)

    def test_a_transient_error_without_a_result_uses_the_default_delay(self, teacher_user, student_user, settings):
        settings.FULFILLMENT_RETRY_SECONDS = 60
        b = confirmed(teacher_user, student_user)
        with mock.patch.object(zoom_client, 'create_meeting', return_value=NEW_MEETING), \
                mock.patch('apps.bookings.services.fulfillment.send_booking_confirmation_email',
                           side_effect=_email_error()):
            dispatch_booking_fulfillment(str(b.id))
        d = FulfillmentDispatch.objects.get(booking=b)
        assert d.status == FD.RETRYABLE
        assert d.next_retry_at <= timezone.now() + timedelta(seconds=61)

    def test_transient_failures_end_terminal_at_the_cap(self, teacher_user, student_user, settings):
        settings.FULFILLMENT_MAX_ATTEMPTS = 2
        b = confirmed(teacher_user, student_user)
        with mock.patch.object(zoom_client, 'create_meeting', return_value=NEW_MEETING) as create, \
                mock.patch('apps.bookings.services.fulfillment.send_booking_confirmation_email',
                           side_effect=_email_error('retryable')):
            dispatch_booking_fulfillment(str(b.id))
            dispatch_booking_fulfillment(str(b.id))
            assert retry_fulfillment_dispatches_task()['redispatched_count'] == 0
        assert FulfillmentDispatch.objects.get(booking=b).status == FD.FAILED
        assert create.call_count == 1


@pytest.mark.django_db
def test_migration_backfills_step_states_from_the_legacy_flags(teacher_user, student_user):
    from importlib import import_module
    from django.apps import apps as registry
    migration = import_module('apps.payments.migrations.0022_fulfillment_dispatch_claim_and_step_states')
    done = FulfillmentDispatch.objects.create(booking=confirmed(teacher_user, student_user), zoom_completed=True,
                                              email_completed=True)
    fresh = FulfillmentDispatch.objects.create(booking=confirmed(teacher_user, student_user, 31 * H))
    migration.backfill_step_states(registry, None)
    done.refresh_from_db()
    fresh.refresh_from_db()
    St = FulfillmentDispatch.StepState
    assert (done.zoom_state, done.calendar_state, done.email_state) == (St.DONE, St.PENDING, St.DONE)
    assert (fresh.zoom_state, fresh.calendar_state, fresh.email_state) == (St.PENDING, St.PENDING, St.PENDING)


# ====================================================================== Postgres-only (CI job)
def _postgres_only():
    if connection.vendor != 'postgresql':
        pytest.skip('PostgreSQL concurrency test (run in the Postgres CI job)')


@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
def test_postgres_concurrent_claims_have_exactly_one_winner(price_catalog, teacher_user, student_user):
    _postgres_only()
    b = confirmed(teacher_user, student_user)
    FulfillmentDispatch.objects.create(booking=b, status=FD.QUEUED)
    barrier, tokens = threading.Barrier(8), []

    def worker():
        try:
            barrier.wait()
            tokens.append(fulfillment().claim_dispatch(b.id))
        finally:
            connection.close()

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len([t for t in tokens if t]) == 1
    assert FulfillmentDispatch.objects.get(booking=b).attempts == 1


@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
def test_postgres_new_row_locks_run(price_catalog, teacher_user, student_user):
    """The new select_for_update sites (fulfilment save, T+10 adjudication, no-meeting dispute) are valid SQL on Postgres."""
    _postgres_only()
    b = confirmed(teacher_user, student_user)
    with mock.patch.object(zoom_client, 'create_meeting', return_value=NEW_MEETING), \
            mock.patch.object(cleanup_zoom_meeting, 'delay'):
        assert dispatch_booking_fulfillment(str(b.id)) is True
    no_room = at_t10(teacher_user, student_user, meeting='', minutes_in=12)
    probed = lesson(teacher_user, student_user, -13, status=S.CONFIRMED)
    Booking.objects.filter(pk=probed.pk).update(zoom_meeting_id=MEETING)
    with mock.patch.object(zoom_client, 'get_meeting_status', return_value={'status': 'waiting'}):
        audit_attendance_and_noshows_task()
    assert Booking.objects.get(pk=no_room.pk).status == S.DISPUTED
    assert Booking.objects.get(pk=probed.pk).status == S.TEACHER_NO_SHOW
