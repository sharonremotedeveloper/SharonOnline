"""Task 9.6: a student moves a paid lesson to another open slot of the same tutor."""
from datetime import datetime, time, timedelta
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.utils import timezone
from rest_framework.test import APIClient

from apps.bookings.models import Booking, BookingReschedule
from apps.bookings.services.slot_generator import generate_teacher_slots
from apps.payments.models import LedgerEntry, PaymentTransaction
from apps.teachers.models import TeacherAvailability
from test_settlement_paths import captured, lesson

S = Booking.Status
User = get_user_model()
H = 60


@pytest.fixture
def tutor(teacher_user):
    TeacherAvailability.objects.all().delete()
    for dow in range(7):
        TeacherAvailability.objects.create(teacher=teacher_user, day_of_week=dow, start_time=time(8, 0), end_time=time(11, 0), is_active=True)
    return teacher_user


def open_slots(tutor, *, after_hours=3, before_days=10):
    now = timezone.now()
    return [datetime.fromisoformat(s['start_time_utc']) for s in generate_teacher_slots(teacher=tutor, days_ahead=14)
            if s['is_bookable'] and now + timedelta(hours=after_hours) < datetime.fromisoformat(s['start_time_utc']) < now + timedelta(days=before_days)]


def resched(user, booking, new_start):
    c = APIClient()
    if user:
        c.force_authenticate(user=user)
    return c.post(f'/api/v1/bookings/{booking.id}/reschedule/', {'start_time_utc': new_start.isoformat()} if new_start else {}, format='json')


@pytest.fixture(autouse=True)
def no_background_work():
    with mock.patch('apps.bookings.services.rescheduling.cleanup_zoom_meeting') as zoom, \
         mock.patch('apps.bookings.services.rescheduling.dispatch_booking_fulfillment') as fulfil:
        yield zoom, fulfil


@pytest.mark.django_db
class TestHappyPath:
    def test_moves_the_same_booking_and_keeps_the_money_where_it_is(self, tutor, student_user, no_background_work):
        zoom, fulfil = no_background_work
        b = captured(tutor, student_user, 30 * H)
        old_start, txs = b.start_time_utc, set(PaymentTransaction.objects.filter(booking=b).values_list('pk', 'status'))
        ledger_before = LedgerEntry.objects.count()
        Booking.objects.filter(pk=b.pk).update(zoom_meeting_id='111', reminder_24h_sent=True, reminder_1h_sent=True,
                                               reminder_10m_sent=True, tutor_late_alert_sent=True)
        new = open_slots(tutor)[5]
        res = resched(student_user, b, new)
        assert res.status_code == 200, res.json()
        b.refresh_from_db()
        assert (b.start_time_utc, b.end_time_utc) == (new, new + timedelta(minutes=25))
        assert (b.status, b.reschedule_count, b.original_start_time_utc) == (S.CONFIRMED, 1, old_start)
        assert LedgerEntry.objects.count() == ledger_before and set(PaymentTransaction.objects.filter(booking=b).values_list('pk', 'status')) == txs
        assert not any([b.reminder_24h_sent, b.reminder_1h_sent, b.reminder_10m_sent, b.tutor_late_alert_sent])
        row = BookingReschedule.objects.get(booking=b)
        assert (row.old_start_time_utc, row.new_start_time_utc) == (old_start, new) and row.actor == f'user:{student_user.username}'

    def test_the_zoom_room_is_replaced(self, tutor, student_user, no_background_work):
        zoom, fulfil = no_background_work
        b = captured(tutor, student_user, 30 * H)
        Booking.objects.filter(pk=b.pk).update(zoom_meeting_id='111', zoom_join_url='https://zoom.us/j/111', zoom_start_url='https://zoom.us/s/111',
                                               zoom_password='pw', teacher_gcal_event_id='evt-1')
        with pytest_django_on_commit():
            resched(student_user, b, open_slots(tutor)[5])
        b.refresh_from_db()
        assert (b.zoom_meeting_id, b.zoom_join_url, b.zoom_start_url, b.zoom_password) == ('', '', '', '')
        zoom.delay.assert_called_once_with('111')
        assert b.teacher_gcal_event_id == 'evt-1'      # the calendar event is kept and updated in place, never deleted
        fulfil.delay.assert_called_once_with(str(b.id))

    def test_the_old_slot_is_free_again(self, tutor, student_user):
        b = captured(tutor, student_user, 30 * H)
        new = open_slots(tutor)[5]
        resched(student_user, b, new)
        assert Booking.objects.get(pk=b.pk).start_time_utc == new


@pytest.mark.django_db
class TestRules:
    def test_only_one_reschedule_per_booking(self, tutor, student_user):
        b = captured(tutor, student_user, 30 * H)
        slots = open_slots(tutor)
        assert resched(student_user, b, slots[4]).status_code == 200
        res = resched(student_user, b, slots[6])
        assert res.status_code == 409 and res.json()['code'] == 'reschedule_limit_reached'
        assert BookingReschedule.objects.count() == 1

    def test_too_late_when_the_old_slot_is_within_two_hours(self, tutor, student_user):
        b = captured(tutor, student_user, 90)
        res = resched(student_user, b, open_slots(tutor)[3])
        assert res.status_code == 409 and res.json()['code'] == 'reschedule_too_late'
        assert Booking.objects.get(pk=b.pk).reschedule_count == 0

    @pytest.mark.parametrize('status', [S.PENDING_PAYMENT, S.IN_PROGRESS, S.COMPLETED, S.CANCELLED, S.CANCELLED_BY_STUDENT,
                                        S.STUDENT_LATE_CANCELLED, S.DISPUTED, S.TEACHER_NO_SHOW])
    def test_only_confirmed_lessons_move(self, tutor, student_user, status):
        b = lesson(tutor, student_user, 30 * H, status=status)
        res = resched(student_user, b, open_slots(tutor)[5])
        assert res.status_code == 409 and res.json()['code'] == 'not_reschedulable'

    def test_the_new_time_must_be_a_real_open_slot_in_range(self, tutor, student_user):
        b = captured(tutor, student_user, 30 * H)
        now = timezone.now()
        good = open_slots(tutor)[5]
        for bad in (good + timedelta(minutes=7),                       # off the 30-minute grid
                    now + timedelta(minutes=30),                       # inside the minimum notice
                    now - timedelta(days=1),                           # the past
                    now + timedelta(days=40),                          # beyond the horizon
                    b.start_time_utc):                                 # where it already is
            res = resched(student_user, b, bad)
            assert res.status_code == 400 and res.json()['code'] == 'invalid_slot', bad
        assert Booking.objects.get(pk=b.pk).reschedule_count == 0

    def test_a_taken_slot_is_a_409(self, tutor, student_user):
        b = captured(tutor, student_user, 30 * H)
        target = open_slots(tutor)[5]
        rival = User.objects.create_user(username='rival', email='r@x.com', password='x-pass-12345', role='student')
        Booking.objects.create(teacher=tutor, student=rival, start_time_utc=target, end_time_utc=target + timedelta(minutes=25), status=S.CONFIRMED)
        res = resched(student_user, b, target)
        assert res.status_code == 409 and res.json()['code'] == 'slot_unavailable'
        assert Booking.objects.get(pk=b.pk).reschedule_count == 0

    def test_a_clash_with_the_students_own_other_lesson_is_refused(self, tutor, student_user):
        other_user = User.objects.create_user(username='t2', email='t2@x.com', password='x-pass-12345', role='teacher')
        from apps.teachers.models import TeacherProfile
        other = TeacherProfile.objects.create(user=other_user, headline='x', price_per_25min_usd=9, status='approved')
        b = captured(tutor, student_user, 30 * H)
        target = open_slots(tutor)[5]
        Booking.objects.create(teacher=other, student=student_user, start_time_utc=target, end_time_utc=target + timedelta(minutes=25), status=S.CONFIRMED)
        assert resched(student_user, b, target).status_code == 409

    def test_losing_the_race_at_the_database_is_a_409_not_a_500(self, tutor, student_user):
        b = captured(tutor, student_user, 30 * H)
        with mock.patch('apps.bookings.models.Booking.save', side_effect=IntegrityError('unique_teacher_active_timeslot')):
            res = resched(student_user, b, open_slots(tutor)[5])
        assert res.status_code == 409 and res.json()['code'] == 'slot_unavailable'

    def test_a_deactivated_tutor_cannot_receive_the_lesson(self, tutor, student_user):
        b = captured(tutor, student_user, 30 * H)
        target = open_slots(tutor)[5]
        from factories import advance_teacher
        advance_teacher(tutor, 'suspended')
        assert resched(student_user, b, target).status_code == 409

    def test_bad_input(self, tutor, student_user):
        b = captured(tutor, student_user, 30 * H)
        c = APIClient(); c.force_authenticate(user=student_user)
        for body in ({}, {'start_time_utc': 'tomorrow'}, {'start_time_utc': None}, [], 'x'):
            assert c.post(f'/api/v1/bookings/{b.id}/reschedule/', body, format='json').status_code == 400


@pytest.mark.django_db
class TestWho:
    def test_only_the_lessons_student(self, tutor, student_user, admin_user):
        stranger = User.objects.create_user(username='nosy', email='n@x.com', password='x-pass-12345', role='student')
        b = captured(tutor, student_user, 30 * H)
        target = open_slots(tutor)[5]
        assert resched(None, b, target).status_code == 401
        assert resched(stranger, b, target).status_code == 404
        assert resched(tutor.user, b, target).status_code == 403          # a tutor cancels; they do not move a student's lesson
        assert resched(admin_user, b, target).status_code == 403
        assert Booking.objects.get(pk=b.pk).reschedule_count == 0


def pytest_django_on_commit():
    """Run transaction.on_commit callbacks immediately (the test DB wraps tests in a transaction)."""
    from django.test import TestCase
    return TestCase.captureOnCommitCallbacks(execute=True)


@pytest.mark.django_db
def test_the_new_slot_lock_is_held_by_a_token_only_that_booking_knows(tutor, student_user):
    """Codex's lock-ownership rule applies to a reschedule too: the lock is stored with a unique token, also kept on the booking."""
    from django.core.cache import cache
    from apps.bookings.services.lock_service import build_slot_lock_key
    b = captured(tutor, student_user, 30 * H)
    new = open_slots(tutor)[5]
    assert resched(student_user, b, new).status_code == 200
    b.refresh_from_db()
    key = build_slot_lock_key(str(tutor.id), new.isoformat())
    assert b.slot_lock_token and cache.get(key) == b.slot_lock_token
    assert cache.get(key) != str(student_user.id)
