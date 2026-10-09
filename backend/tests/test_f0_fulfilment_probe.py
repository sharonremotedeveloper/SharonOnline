"""
Slice F0 (docs/PHASE_11_12_EXECUTION_PLAN.md section 2), on the Daily.co classroom (D5): money-affecting defects.

A. A reschedule left the lesson without a usable room (the completed fulfilment row was skipped) and the T+10 job then scored
   the tutor as a no-show. Now the reschedule resets the dispatch, and re-provisioning moves the room's open window.
B. A provider error during the T+10 probe counted as "tutor absent". Now the probe is tri-state; `unknown` defers, and an
   unresolved lesson goes to DISPUTED at the end of its window. A no-show also needs the student's own join (V4 contract).
   The HTTP probe runs outside every row lock.
C. Fulfilment races: compare-and-swap claim, status re-check under the row lock, update_fields saves, per-step states,
   terminal FAILED after N attempts.
"""
import logging
import threading
from datetime import time, timedelta
from unittest import mock

import pytest
import requests
from django.db import connection
from django.test import TestCase
from django.utils import timezone

from apps.admin_api.models import DisputeCase
from apps.bookings.models import AttendanceAudit, Booking, BookingStatusChange
from apps.bookings.tasks import audit_attendance_and_noshows_task
from apps.integrations.services.daily import DailyClient
from apps.integrations.tasks import (
    cleanup_gcal_event, dispatch_booking_fulfillment, retry_fulfillment_dispatches_task,
)
from apps.payments.models import CreditBundle, FulfillmentDispatch, RefundRequest
from apps.payments.services.webhook_handler import dispatch_fulfillment
from apps.teachers.models import TeacherAvailability, TeacherStrike
from payment_helpers import captured, lesson
from test_reschedule import open_slots, resched

S = Booking.Status
FD = FulfillmentDispatch.Status
St = FulfillmentDispatch.StepState
H = 60


def fulfillment():
    from apps.bookings.services import fulfillment as module
    return module


def probe_module():
    from apps.bookings.services import attendance_probe as module
    return module


def on_commit():
    return TestCase.captureOnCommitCallbacks(execute=True)


def room_name(booking):
    return f'lesson-{booking.id}'


def at_t10(teacher, student, *, minutes_in=12):
    """A paid, confirmed lesson that started `minutes_in` minutes ago and nobody has joined."""
    return lesson(teacher, student, -minutes_in, status=S.CONFIRMED)


def student_joined(booking, session='s1'):
    """The student's own join: the evidence that the room was open (V4 contract)."""
    return AttendanceAudit.objects.create(
        booking=booking, participant_email=booking.student.email, session_id=session,
        classification=AttendanceAudit.Classification.STUDENT, join_time_utc=booking.start_time_utc)


def open_room(fake_daily, booking, *present_user_ids):
    """The lesson's Daily room exists and these users are in it right now."""
    fake_daily.rooms[room_name(booking)] = {'name': room_name(booking), 'config': {}}
    fake_daily.set_presence(room_name(booking), present_user_ids)


def presence_calls(fake_daily):
    return [r for r in fake_daily.requests if r.url.endswith('/presence')]


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
    with mock.patch.object(cleanup_gcal_event, 'delay') as gcal_cleanup:
        yield gcal_cleanup


def confirmed(teacher, student, start_in_min=30 * H):
    return lesson(teacher, student, start_in_min, status=S.CONFIRMED)


def make_due(booking):
    """Fast-forward a RETRYABLE dispatch to its retry time (a retry is refused before then: review m1)."""
    FulfillmentDispatch.objects.filter(booking=booking).update(next_retry_at=timezone.now() - timedelta(seconds=1))


# ====================================================================== A. reschedule -> the room moves with the lesson
@pytest.mark.django_db
class TestRescheduleReprovisions:
    def test_a_rescheduled_lesson_moves_its_room_window_after_commit(self, tutor, student_user, side_tasks, fake_daily, settings):
        b = captured(tutor, student_user, 30 * H)
        fake_daily.rooms[room_name(b)] = {'name': room_name(b), 'config': {'nbf': 1, 'exp': 2}}      # the old slot's window
        FulfillmentDispatch.objects.update_or_create(booking=b, defaults=dict(
            status=FD.SUCCEEDED, attempts=1, room_completed=True, calendar_completed=True, email_completed=True))
        new = open_slots(tutor)[5]
        with on_commit():
            assert resched(student_user, b, new).status_code == 200
        end_window = int((new + timedelta(minutes=25 + settings.DAILY_ROOM_VALID_AFTER_END_MINUTES)).timestamp())
        assert fake_daily.updated == [room_name(b)] and fake_daily.created == []     # same room, never deleted or duplicated
        assert fake_daily.rooms[room_name(b)]['config']['exp'] == end_window
        assert FulfillmentDispatch.objects.get(booking=b).status == FD.SUCCEEDED

    def test_the_dispatch_is_reset_inside_the_reschedule_transaction(self, tutor, student_user, side_tasks):
        b = captured(tutor, student_user, 30 * H)
        FulfillmentDispatch.objects.update_or_create(booking=b, defaults=dict(
            status=FD.SUCCEEDED, attempts=3, room_completed=True, calendar_completed=True, email_completed=True,
            last_error='old'))
        with mock.patch.object(dispatch_booking_fulfillment, 'delay'):
            assert resched(student_user, b, open_slots(tutor)[5]).status_code == 200
        d = FulfillmentDispatch.objects.get(booking=b)
        assert (d.status, d.attempts, d.last_error) == (FD.QUEUED, 0, '')
        assert not (d.room_completed or d.calendar_completed or d.email_completed)
        assert (d.room_state, d.calendar_state, d.email_state) == (St.PENDING, St.PENDING, St.PENDING)

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
class TestNoEvidenceIsNeverANoShow:
    def test_t10_with_nobody_in_the_room_defers_and_never_scores(self, teacher_user, student_user, fake_daily):
        b = at_t10(teacher_user, student_user)
        res = audit_attendance_and_noshows_task()
        b.refresh_from_db()
        assert b.status == S.CONFIRMED                            # no student join = no evidence the room was open
        assert res['teacher_no_shows'] == 0
        assert not presence_calls(fake_daily)                     # and nothing to probe yet
        no_penalty(b)

    def test_a_lesson_that_ends_without_a_verdict_is_disputed_without_penalty(self, teacher_user, student_user):
        b = lesson(teacher_user, student_user, -30, status=S.CONFIRMED)        # ended 5 minutes ago, never adjudicated
        audit_attendance_and_noshows_task()
        b.refresh_from_db()
        assert b.status == S.DISPUTED
        no_penalty(b)
        assert DisputeCase.objects.filter(booking=b, status=DisputeCase.Status.OPEN).exists()
        assert 'verdict' in BookingStatusChange.objects.get(booking=b, to_status=S.DISPUTED).reason.lower()

    def test_a_no_verdict_dispute_is_idempotent(self, teacher_user, student_user):
        b = lesson(teacher_user, student_user, -30, status=S.CONFIRMED)
        audit_attendance_and_noshows_task()
        audit_attendance_and_noshows_task()
        assert DisputeCase.objects.filter(booking=b).count() == 1
        assert BookingStatusChange.objects.filter(booking=b, to_status=S.DISPUTED).count() == 1


# ====================================================================== B. tri-state probe
@pytest.mark.django_db
class TestProbeMapping:
    def test_the_tutor_in_the_roster_is_started(self, teacher_user, student_user, fake_daily):
        b = at_t10(teacher_user, student_user)
        open_room(fake_daily, b, b.teacher.user_id)
        assert probe_module().probe_room(b) == 'started'

    @pytest.mark.parametrize('who', ['nobody', 'only_the_student'])
    def test_a_readable_roster_without_the_tutor_is_not_started(self, teacher_user, student_user, fake_daily, who):
        b = at_t10(teacher_user, student_user)
        open_room(fake_daily, b, *([b.student_id] if who == 'only_the_student' else []))
        assert probe_module().probe_room(b) == 'not_started'

    def test_a_missing_room_is_unknown(self, teacher_user, student_user, fake_daily):
        assert probe_module().probe_room(at_t10(teacher_user, student_user)) == 'unknown'

    @pytest.mark.parametrize('status', [429, 500, 503])
    def test_a_provider_error_is_unknown(self, teacher_user, student_user, fake_daily, status):
        b = at_t10(teacher_user, student_user)
        open_room(fake_daily, b)
        fake_daily.fail_next('presence', status)
        assert probe_module().probe_room(b) == 'unknown'

    def test_unconfigured_daily_is_unknown(self, teacher_user, student_user, settings):
        settings.DAILY_DOMAIN, settings.DAILY_API_KEY, settings.DAILY_SIMULATE_WITHOUT_CREDENTIALS = '', '', False
        assert probe_module().probe_room(at_t10(teacher_user, student_user)) == 'unknown'

    def test_a_simulated_roster_is_never_evidence(self, teacher_user, student_user):
        # Default test settings simulate Daily (no key): an empty fake roster must not read as "tutor absent".
        assert probe_module().probe_room(at_t10(teacher_user, student_user)) == 'unknown'

    @pytest.mark.parametrize('exc', [requests.Timeout('t'), requests.ConnectionError('c'), ValueError('x')])
    def test_any_failure_is_unknown(self, teacher_user, student_user, exc):
        b = at_t10(teacher_user, student_user)
        with mock.patch.object(DailyClient, 'get_room_presence', side_effect=exc):
            assert probe_module()._safe_probe(b) == 'unknown'

    def test_the_probe_log_carries_ids_only(self, teacher_user, student_user, caplog):
        b = at_t10(teacher_user, student_user)
        with mock.patch.object(DailyClient, 'get_room_presence', side_effect=RuntimeError('token SECRET-123 rejected')), \
                caplog.at_level(logging.WARNING):
            probe_module()._safe_probe(b)
        assert 'SECRET-123' not in caplog.text and str(b.id) in caplog.text


@pytest.mark.django_db
class TestProbeUnknownDefers:
    @pytest.mark.parametrize('failure', [500, 429, 'no_room'])
    def test_a_probe_failure_is_never_a_no_show(self, teacher_user, student_user, fake_daily, failure):
        b = at_t10(teacher_user, student_user)
        student_joined(b)
        if failure != 'no_room':
            open_room(fake_daily, b)
            fake_daily.fail_next('presence', failure)
        res = audit_attendance_and_noshows_task()
        b.refresh_from_db()
        assert b.status == S.CONFIRMED                  # deferred to the next run
        assert res['teacher_no_shows'] == 0 and res['probe_deferred'] == 1
        no_penalty(b)

    def test_unknown_then_not_started_is_a_no_show_on_a_later_run(self, teacher_user, student_user, fake_daily):
        b = at_t10(teacher_user, student_user)
        student_joined(b)
        open_room(fake_daily, b)
        fake_daily.fail_next('presence', 500)
        audit_attendance_and_noshows_task()
        audit_attendance_and_noshows_task()
        b.refresh_from_db()
        assert b.status == S.TEACHER_NO_SHOW
        assert TeacherStrike.objects.filter(booking=b).count() == 1

    def test_unknown_until_the_lesson_ends_goes_to_disputed(self, teacher_user, student_user, fake_daily):
        b = at_t10(teacher_user, student_user)
        student_joined(b)
        open_room(fake_daily, b)
        fake_daily.fail_next('presence', 500)
        audit_attendance_and_noshows_task()
        start = timezone.now() - timedelta(minutes=30)
        Booking.objects.filter(pk=b.pk).update(start_time_utc=start, end_time_utc=start + timedelta(minutes=25))
        audit_attendance_and_noshows_task()
        b.refresh_from_db()
        assert b.status == S.DISPUTED
        no_penalty(b)
        assert DisputeCase.objects.filter(booking=b, status=DisputeCase.Status.OPEN).exists()
        assert 'verdict' in BookingStatusChange.objects.get(booking=b, to_status=S.DISPUTED).reason.lower()

    def test_not_started_with_the_student_present_is_a_no_show(self, teacher_user, student_user, fake_daily):
        b = at_t10(teacher_user, student_user)
        student_joined(b)
        open_room(fake_daily, b, b.student_id)
        res = audit_attendance_and_noshows_task()
        b.refresh_from_db()
        assert b.status == S.TEACHER_NO_SHOW and res['teacher_no_shows'] == 1

    def test_started_prevents_the_no_show_and_starts_the_lesson(self, teacher_user, student_user, fake_daily):
        b = at_t10(teacher_user, student_user)
        student_joined(b)
        open_room(fake_daily, b, b.teacher.user_id, b.student_id)
        audit_attendance_and_noshows_task()
        b.refresh_from_db()
        assert b.status == S.IN_PROGRESS
        no_penalty(b)
        assert AttendanceAudit.objects.filter(booking=b, session_id='active_room_probe', identity='probe').exists()

    def test_a_status_change_during_the_probe_is_respected(self, teacher_user, student_user):
        b = at_t10(teacher_user, student_user)
        student_joined(b)

        def tutor_cancelled(self, room):
            Booking.objects.filter(pk=b.pk).update(status=S.CANCELLED_BY_TEACHER)
            return ('ok', [])

        with mock.patch.object(DailyClient, 'get_room_presence', tutor_cancelled), \
                mock.patch('apps.bookings.services.attendance_probe.is_daily_configured', return_value=True):
            audit_attendance_and_noshows_task()
        b.refresh_from_db()
        assert b.status == S.CANCELLED_BY_TEACHER
        assert not TeacherStrike.objects.filter(booking=b).exists()

    def test_the_probe_budget_bounds_the_run(self, teacher_user, student_user, settings, fake_daily):
        settings.ATTENDANCE_PROBE_BUDGET_SECONDS = 0
        b = at_t10(teacher_user, student_user)
        student_joined(b)
        open_room(fake_daily, b)
        audit_attendance_and_noshows_task()
        assert not presence_calls(fake_daily)
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
    student_joined(b)
    seen = []

    def probe(self, room):
        seen.append(connection.in_atomic_block)
        return ('ok', [])

    with mock.patch.object(DailyClient, 'get_room_presence', probe), \
            mock.patch('apps.bookings.services.attendance_probe.is_daily_configured', return_value=True):
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

    def test_a_concurrent_run_exits_without_touching_daily(self, teacher_user, student_user, fake_daily):
        b = confirmed(teacher_user, student_user)
        FulfillmentDispatch.objects.create(booking=b, status=FD.RUNNING, claim_token='other', claimed_at=timezone.now())
        assert dispatch_booking_fulfillment(str(b.id)) is False
        assert fake_daily.requests == []


@pytest.mark.django_db
class TestFulfilmentRun:
    def test_happy_path_records_per_step_states(self, teacher_user, student_user, fake_daily):
        b = confirmed(teacher_user, student_user)
        assert dispatch_booking_fulfillment(str(b.id)) is True
        d = FulfillmentDispatch.objects.get(booking=b)
        assert (d.status, d.room_state, d.calendar_state, d.email_state) == (FD.SUCCEEDED, St.DONE, St.SKIPPED, St.DONE)
        assert d.claim_token == ''
        assert fake_daily.created == [room_name(b)]
        config = fake_daily.rooms[room_name(b)]['config']
        assert config['nbf'] == int((b.start_time_utc - timedelta(minutes=15)).timestamp())
        assert config['exp'] == int((b.end_time_utc + timedelta(minutes=30)).timestamp())

    def test_no_google_token_is_skipped_not_done(self, teacher_user, student_user):
        b = confirmed(teacher_user, student_user)
        with mock.patch('apps.integrations.google_calendar.requests.post') as google:
            dispatch_booking_fulfillment(str(b.id))
        google.assert_not_called()
        assert FulfillmentDispatch.objects.get(booking=b).calendar_state == St.SKIPPED

    def test_a_calendar_sync_that_returns_nothing_is_a_failure(self, teacher_user, student_user):
        teacher_user.user.google_calendar_token = {'access_token': 'tok'}
        teacher_user.user.save(update_fields=['google_calendar_token'])
        b = confirmed(teacher_user, student_user)
        with mock.patch('apps.bookings.services.fulfillment.sync_booking_to_teacher_gcal', return_value=''):
            assert dispatch_booking_fulfillment(str(b.id)) is False
        d = FulfillmentDispatch.objects.get(booking=b)
        assert (d.status, d.calendar_state) == (FD.RETRYABLE, St.FAILED)
        assert d.next_retry_at is not None

    def test_a_calendar_event_id_is_done(self, teacher_user, student_user):
        teacher_user.user.google_calendar_token = {'access_token': 'tok'}
        teacher_user.user.save(update_fields=['google_calendar_token'])
        b = confirmed(teacher_user, student_user)
        with mock.patch('apps.bookings.services.fulfillment.sync_booking_to_teacher_gcal', return_value='evt-9'):
            assert dispatch_booking_fulfillment(str(b.id)) is True
        assert FulfillmentDispatch.objects.get(booking=b).calendar_state == St.DONE

    def test_an_email_that_was_not_sent_is_a_failure(self, teacher_user, student_user):
        b = confirmed(teacher_user, student_user)
        with mock.patch('apps.bookings.services.fulfillment.send_booking_confirmation_email', return_value=False):
            assert dispatch_booking_fulfillment(str(b.id)) is False
        d = FulfillmentDispatch.objects.get(booking=b)
        assert (d.status, d.email_state) == (FD.RETRYABLE, St.FAILED)

    def test_a_retry_does_not_repeat_finished_steps(self, teacher_user, student_user, fake_daily):
        b = confirmed(teacher_user, student_user)
        with mock.patch('apps.bookings.services.fulfillment.send_booking_confirmation_email',
                        side_effect=[False, True]) as mail:
            dispatch_booking_fulfillment(str(b.id))
            make_due(b)
            assert dispatch_booking_fulfillment(str(b.id)) is True
        assert fake_daily.created == [room_name(b)] and mail.call_count == 2
        assert len(fake_daily.requests) == 2                  # the first run's lookup + create; the retry never asked again

    def test_a_cancelled_booking_is_not_provisioned(self, teacher_user, student_user, fake_daily):
        b = confirmed(teacher_user, student_user)
        Booking.objects.filter(pk=b.pk).update(status=S.CANCELLED_BY_STUDENT)
        assert dispatch_booking_fulfillment(str(b.id)) is False
        assert fake_daily.requests == []
        assert FulfillmentDispatch.objects.get(booking=b).status == FD.ABANDONED

    def test_a_lesson_cancelled_while_the_room_is_built_stays_cancelled(self, teacher_user, student_user):
        b = confirmed(teacher_user, student_user)

        def ensure_while_student_cancels(self, room, nbf, exp):
            Booking.objects.filter(pk=b.pk).update(status=S.CANCELLED_BY_STUDENT)
            return {'name': room}

        with mock.patch.object(DailyClient, 'ensure_room', ensure_while_student_cancels):
            assert dispatch_booking_fulfillment(str(b.id)) is False
        b.refresh_from_db()
        assert b.status == S.CANCELLED_BY_STUDENT             # a stale instance never overwrote the cancellation
        assert FulfillmentDispatch.objects.get(booking=b).status == FD.ABANDONED

    def test_the_room_step_writes_nothing_to_the_booking(self, teacher_user, student_user):
        b = confirmed(teacher_user, student_user)
        with mock.patch.object(Booking, 'save', autospec=True, side_effect=Booking.save) as save:
            assert dispatch_booking_fulfillment(str(b.id)) is True
        save.assert_not_called()

    def test_a_run_whose_claim_was_reset_by_a_reschedule_keeps_nothing(self, teacher_user, student_user):
        b = confirmed(teacher_user, student_user)

        def ensure_while_rescheduled(self, room, nbf, exp):
            fulfillment().reset_for_reprovision(Booking.objects.get(pk=b.pk))
            return {'name': room}

        with mock.patch.object(DailyClient, 'ensure_room', ensure_while_rescheduled):
            assert dispatch_booking_fulfillment(str(b.id)) is False
        d = FulfillmentDispatch.objects.get(booking=b)
        assert d.status == FD.QUEUED and d.room_state == St.PENDING       # the new generation still runs

    def test_an_existing_room_is_reused_and_its_window_synced(self, teacher_user, student_user, fake_daily):
        b = confirmed(teacher_user, student_user)
        fake_daily.rooms[room_name(b)] = {'name': room_name(b), 'config': {'nbf': 1, 'exp': 2}}
        assert dispatch_booking_fulfillment(str(b.id)) is True
        assert fake_daily.created == [] and fake_daily.updated == [room_name(b)]

    def test_unconfigured_daily_fails_loudly_instead_of_inventing_a_room(self, teacher_user, student_user, settings):
        settings.DAILY_DOMAIN, settings.DAILY_API_KEY, settings.DAILY_SIMULATE_WITHOUT_CREDENTIALS = '', '', False
        b = confirmed(teacher_user, student_user)
        assert dispatch_booking_fulfillment(str(b.id)) is False
        d = FulfillmentDispatch.objects.get(booking=b)
        assert (d.status, d.room_state, d.last_error) == (FD.RETRYABLE, St.FAILED, 'room: DailyConfigError')

    def test_last_error_names_the_step_and_error_type_only(self, teacher_user, student_user, fake_daily):
        b = confirmed(teacher_user, student_user)
        fake_daily.fail_next('room_create', 500, {'error': 'student@test.com secret'})
        dispatch_booking_fulfillment(str(b.id))
        d = FulfillmentDispatch.objects.get(booking=b)
        assert d.last_error == 'room: DailyApiError'

    def test_terminal_failed_after_max_attempts_with_an_alert(self, teacher_user, student_user, settings, caplog, fake_daily):
        settings.FULFILLMENT_MAX_ATTEMPTS = 2
        b = confirmed(teacher_user, student_user, start_in_min=-1)     # terminal only once the lesson has started (review M4)
        fake_daily.fail_next('room_create', 500)
        fake_daily.fail_next('room_create', 500)
        with caplog.at_level(logging.ERROR):
            dispatch_booking_fulfillment(str(b.id))
            assert FulfillmentDispatch.objects.get(booking=b).status == FD.RETRYABLE
            make_due(b)
            dispatch_booking_fulfillment(str(b.id))
        d = FulfillmentDispatch.objects.get(booking=b)
        assert (d.status, d.attempts, d.next_retry_at) == (FD.FAILED, 2, None)
        assert f'FULFILMENT FAILED booking={b.id}' in caplog.text
        assert 'student@test.com' not in caplog.text

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

    def test_the_sweep_reclaims_a_stale_running_dispatch(self, teacher_user, student_user, settings, fake_daily):
        settings.FULFILLMENT_LEASE_SECONDS = 600
        b = confirmed(teacher_user, student_user)
        FulfillmentDispatch.objects.create(booking=b, status=FD.RUNNING, claim_token='dead-worker',
                                           claimed_at=timezone.now() - timedelta(minutes=11))
        assert retry_fulfillment_dispatches_task()['redispatched_count'] == 1
        assert FulfillmentDispatch.objects.get(booking=b).status == FD.SUCCEEDED
        assert fake_daily.created == [room_name(b)]

    def test_the_sweep_leaves_a_live_running_dispatch_alone(self, teacher_user, student_user):
        b = confirmed(teacher_user, student_user)
        FulfillmentDispatch.objects.create(booking=b, status=FD.RUNNING, claim_token='busy', claimed_at=timezone.now())
        assert retry_fulfillment_dispatches_task()['redispatched_count'] == 0


@pytest.mark.django_db
class TestMutationGuards:
    """Tests added after the F0 mutation run (docs/mutation/F0.md) to pin lines no behaviour test exercised."""

    def test_a_claim_taken_over_by_another_worker_keeps_nothing(self, teacher_user, student_user):
        b = confirmed(teacher_user, student_user)

        def ensure_while_reclaimed(self, room, nbf, exp):        # lease expired, another worker now holds RUNNING with its own token
            FulfillmentDispatch.objects.filter(booking=b).update(claim_token='other-worker')
            return {'name': room}

        with mock.patch.object(DailyClient, 'ensure_room', ensure_while_reclaimed):
            assert dispatch_booking_fulfillment(str(b.id)) is False
        assert FulfillmentDispatch.objects.get(booking=b).claim_token == 'other-worker'

    def test_a_retry_does_not_resync_a_finished_calendar_step(self, teacher_user, student_user):
        teacher_user.user.google_calendar_token = {'access_token': 'tok'}
        teacher_user.user.save(update_fields=['google_calendar_token'])
        b = confirmed(teacher_user, student_user)
        with mock.patch('apps.bookings.services.fulfillment.sync_booking_to_teacher_gcal', return_value='evt') as sync, \
                mock.patch('apps.bookings.services.fulfillment.send_booking_confirmation_email', side_effect=[False, True]):
            dispatch_booking_fulfillment(str(b.id))
            make_due(b)
            assert dispatch_booking_fulfillment(str(b.id)) is True
        assert sync.call_count == 1

    def test_adjudication_rechecks_the_status_under_the_lock(self, teacher_user, student_user):
        """Race between the candidate query and the row lock: a lesson cancelled in between is left alone."""
        b = at_t10(teacher_user, student_user)
        student_joined(b)
        Booking.objects.filter(pk=b.pk).update(status=S.CANCELLED_BY_TEACHER)
        module = probe_module()
        results = {'teacher_no_shows': 0, 'student_no_shows': 0}
        with mock.patch.object(module, '_t10_candidates', lambda now: Booking.objects.filter(pk=b.pk)):
            module.adjudicate_t10(timezone.now(), {b.id: (module.ROOM, module.NOT_STARTED)}, results)
        b.refresh_from_db()
        assert b.status == S.CANCELLED_BY_TEACHER and results['teacher_no_shows'] == 0
        assert not TeacherStrike.objects.filter(booking=b).exists()

    def test_an_in_progress_lesson_is_not_probed(self, teacher_user, student_user, fake_daily):
        b = at_t10(teacher_user, student_user)
        student_joined(b)
        Booking.objects.filter(pk=b.pk).update(status=S.IN_PROGRESS)
        probe_module().probe_t10_candidates(timezone.now())
        assert not presence_calls(fake_daily)


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
    """QA merge requirement (N1c integration): e-mail failures never mark the step done, never re-provision the room,
    and a permanent failure is terminal (no endless 5-minute re-queue)."""

    def test_permanent_email_failure_is_terminal_and_alerted(self, teacher_user, student_user, caplog, fake_daily):
        b = confirmed(teacher_user, student_user)
        with mock.patch('apps.bookings.services.fulfillment.send_booking_confirmation_email',
                        side_effect=_email_error('failed')) as mail, caplog.at_level(logging.ERROR):
            assert dispatch_booking_fulfillment(str(b.id)) is False
            d = FulfillmentDispatch.objects.get(booking=b)
            assert (d.status, d.room_state, d.email_state, d.next_retry_at) == (FD.FAILED, St.DONE, St.FAILED, None)
            assert d.attempts == 1 and d.last_error == 'email: EmailDeliveryError'
            assert f'FULFILMENT FAILED booking={b.id}' in caplog.text and 'student@test.com' not in caplog.text
            assert retry_fulfillment_dispatches_task()['redispatched_count'] == 0
            dispatch_fulfillment(str(b.id))                          # a duplicate webhook does not revive it either
        assert FulfillmentDispatch.objects.get(booking=b).status == FD.FAILED
        assert fake_daily.created == [room_name(b)] and mail.call_count == 1

    def test_transient_email_failure_retries_without_reprovisioning_the_room(self, teacher_user, student_user, fake_daily):
        b = confirmed(teacher_user, student_user)
        with mock.patch('apps.bookings.services.fulfillment.send_booking_confirmation_email',
                        side_effect=[_email_error('retryable'), True]) as mail:
            assert dispatch_booking_fulfillment(str(b.id)) is False
            d = FulfillmentDispatch.objects.get(booking=b)
            assert (d.status, d.email_state) == (FD.RETRYABLE, St.FAILED)
            assert not d.email_completed
            FulfillmentDispatch.objects.filter(booking=b).update(next_retry_at=timezone.now() - timedelta(seconds=1))
            assert retry_fulfillment_dispatches_task()['redispatched_count'] == 1
        d = FulfillmentDispatch.objects.get(booking=b)
        assert (d.status, d.email_state) == (FD.SUCCEEDED, St.DONE)
        assert fake_daily.created == [room_name(b)] and mail.call_count == 2

    def test_retry_after_is_honoured(self, teacher_user, student_user, settings):
        settings.FULFILLMENT_RETRY_SECONDS = 60
        b = confirmed(teacher_user, student_user)
        before = timezone.now()
        with mock.patch('apps.bookings.services.fulfillment.send_booking_confirmation_email',
                        side_effect=_email_error('in_flight', retry_after=900)):
            dispatch_booking_fulfillment(str(b.id))
        d = FulfillmentDispatch.objects.get(booking=b)
        assert d.status == FD.RETRYABLE
        assert before + timedelta(seconds=899) <= d.next_retry_at <= timezone.now() + timedelta(seconds=901)

    def test_a_transient_error_without_a_result_uses_the_default_delay(self, teacher_user, student_user, settings):
        settings.FULFILLMENT_RETRY_SECONDS = 60
        b = confirmed(teacher_user, student_user)
        with mock.patch('apps.bookings.services.fulfillment.send_booking_confirmation_email',
                        side_effect=_email_error()):
            dispatch_booking_fulfillment(str(b.id))
        d = FulfillmentDispatch.objects.get(booking=b)
        assert d.status == FD.RETRYABLE
        assert d.next_retry_at <= timezone.now() + timedelta(seconds=73)       # 60 s base, +20 % jitter

    def test_transient_failures_end_terminal_at_the_cap(self, teacher_user, student_user, settings, fake_daily):
        settings.FULFILLMENT_MAX_ATTEMPTS = 2
        b = confirmed(teacher_user, student_user, start_in_min=-1)
        with mock.patch('apps.bookings.services.fulfillment.send_booking_confirmation_email',
                        side_effect=_email_error('retryable')):
            dispatch_booking_fulfillment(str(b.id))
            make_due(b)
            dispatch_booking_fulfillment(str(b.id))
            assert retry_fulfillment_dispatches_task()['redispatched_count'] == 0
        assert FulfillmentDispatch.objects.get(booking=b).status == FD.FAILED
        assert fake_daily.created == [room_name(b)]


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
def test_postgres_new_row_locks_run(price_catalog, teacher_user, student_user, fake_daily):
    """The select_for_update sites (fulfilment room step, T+10 adjudication, no-verdict dispute) are valid SQL on Postgres."""
    _postgres_only()
    b = confirmed(teacher_user, student_user)
    assert dispatch_booking_fulfillment(str(b.id)) is True
    probed = lesson(teacher_user, student_user, -13, status=S.CONFIRMED)
    student_joined(probed)
    open_room(fake_daily, probed, probed.student_id)
    audit_attendance_and_noshows_task()
    assert Booking.objects.get(pk=probed.pk).status == S.TEACHER_NO_SHOW
