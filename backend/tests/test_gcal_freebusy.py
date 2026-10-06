"""
Slice G2: a tutor's own Google Calendar events hide slots on the PUBLIC listing, as a hint only.

The hint never decides a booking (reserve/checkout/reschedule ask the generator for strict database truth), our own lesson
events are not counted as the tutor being busy, and any Google failure degrades to "no hiding", never to "no slots".
"""
from datetime import date, datetime, time, timedelta, timezone as dt_tz
from unittest import mock

import pytest
from cryptography.fernet import Fernet
from django.core.cache import cache
from rest_framework.test import APIClient

import factories as f
from apps.bookings.services.slot_generator import generate_teacher_slots
from apps.common.crypto import encrypt_integration_secret
from apps.integrations import google_calendar, tasks
from apps.integrations.models import CalendarCredential
from apps.teachers.models import TeacherAvailability

pytestmark = pytest.mark.django_db

UTC = dt_tz.utc
MONDAY = date(2026, 1, 5)


def at(hour, minute=0, day=MONDAY):
    return datetime.combine(day, time(hour, minute), tzinfo=UTC)


@pytest.fixture(autouse=True)
def now_is_before_the_lesson_day(frozen_clock, settings):
    frozen_clock.set(at(0, 0, date(2026, 1, 1)))
    settings.INTEGRATION_DATA_KEYS = {'v1': Fernet.generate_key().decode()}
    settings.INTEGRATION_DATA_ACTIVE_KEY = 'v1'
    cache.clear()


@pytest.fixture
def tutor(db):
    """A UTC tutor free Monday 09:00-11:00: four slots, 09:00 09:30 10:00 10:30."""
    profile = f.make_teacher_profile(f.make_user('teacher', timezone='UTC'), availability=False)
    TeacherAvailability.objects.create(teacher=profile, day_of_week=0, start_time=time(9, 0), end_time=time(11, 0),
                                       is_active=True)
    return profile


def connect(profile, **fields):
    return CalendarCredential.objects.create(user=profile.user, refresh_token_enc=encrypt_integration_secret('refresh'),
                                             **fields)


def listing(profile, **kwargs):
    slots = generate_teacher_slots(teacher=profile, start_date=MONDAY, days_ahead=1, **kwargs)
    return {s['start_time_utc'][11:16]: s['status'] for s in slots}


def refresh(profile):
    return tasks.sync_tutor_busy_task(str(profile.id))


class TestBusyHint:
    def test_a_personal_event_hides_the_slots_it_overlaps_on_the_public_listing(self, tutor, fake_google):
        connect(tutor)
        fake_google.add_external_event(at(9, 40), at(10, 10))          # touches the 09:30 and 10:00 slots
        refresh(tutor)
        assert listing(tutor, include_external_busy=True) == {'09:00': 'available', '10:30': 'available'}

    def test_the_hint_is_off_by_default_so_reserve_and_checkout_see_database_truth(self, tutor, fake_google):
        connect(tutor)
        fake_google.add_external_event(at(9, 0), at(11, 0))
        refresh(tutor)
        assert list(listing(tutor)) == ['09:00', '09:30', '10:00', '10:30']
        assert listing(tutor, include_external_busy=True) == {}

    def test_reserve_validates_against_strict_records_even_when_google_says_busy(self, tutor, fake_google):
        from apps.bookings.services.reservation import reserve_slot
        connect(tutor)
        fake_google.add_external_event(at(9, 0), at(11, 0))
        refresh(tutor)
        booking, created = reserve_slot(student=f.make_student(), teacher_id=tutor.id, start_time_utc=at(10, 0))
        assert created and booking.start_time_utc == at(10, 0)

    def test_events_that_do_not_make_the_tutor_busy_are_ignored(self, tutor, fake_google):
        connect(tutor)
        fake_google.add_external_event(at(9, 0), at(11, 0), transparent=True)       # shown as "free"
        fake_google.add_external_event(at(9, 0), at(11, 0), status='cancelled')
        refresh(tutor)
        assert len(listing(tutor, include_external_busy=True)) == 4

    def test_an_all_day_event_blocks_the_tutors_whole_local_day(self, tutor, fake_google):
        connect(tutor)
        fake_google.add_external_event(all_day=(MONDAY, MONDAY + timedelta(days=1)))
        refresh(tutor)
        assert listing(tutor, include_external_busy=True) == {}

    def test_every_page_of_events_is_read(self, tutor, fake_google):
        connect(tutor)
        fake_google.page_size = 1
        fake_google.add_external_event(at(9, 0), at(9, 25))
        fake_google.add_external_event(at(10, 0), at(10, 25))
        refresh(tutor)
        assert listing(tutor, include_external_busy=True) == {'09:30': 'available', '10:30': 'available'}

    def test_the_busy_hint_composes_with_other_blocked_intervals(self, tutor, fake_google):
        connect(tutor)
        fake_google.add_external_event(at(9, 0), at(9, 25))
        refresh(tutor)
        eskom = [(at(10, 30), at(10, 55))]
        assert list(listing(tutor, include_external_busy=True, blocked_intervals=eskom)) == ['09:30', '10:00']


class TestOwnLessonsAreNotBusy:
    def test_events_we_created_carry_a_private_marker(self, tutor, fake_google):
        connect(tutor)
        booking = f.make_booking(teacher=tutor, start=at(9, 30), status='confirmed', zoom_join_url='https://zoom.example/j/1')
        event_id = google_calendar.sync_booking_to_teacher_gcal(booking)
        assert fake_google.events[event_id]['extendedProperties']['private']['sharon_booking_id'] == str(booking.id)

    def test_a_lesson_event_does_not_hide_its_own_slot_it_shows_as_booked(self, tutor, fake_google):
        connect(tutor)
        booking = f.make_booking(teacher=tutor, start=at(9, 30), status='confirmed', zoom_join_url='https://zoom.example/j/1')
        google_calendar.sync_booking_to_teacher_gcal(booking)
        refresh(tutor)
        assert cache.get(f'gcal:busy:{tutor.id}') == []
        assert listing(tutor, include_external_busy=True) == {
            '09:00': 'available', '09:30': 'booked', '10:00': 'available', '10:30': 'available'}

    def test_an_external_event_next_to_a_lesson_event_still_counts(self, tutor, fake_google):
        connect(tutor)
        booking = f.make_booking(teacher=tutor, start=at(9, 30), status='confirmed', zoom_join_url='https://zoom.example/j/1')
        google_calendar.sync_booking_to_teacher_gcal(booking)
        fake_google.add_external_event(at(10, 0), at(10, 25))
        refresh(tutor)
        assert list(listing(tutor, include_external_busy=True)) == ['09:00', '09:30', '10:30']


class TestOptInAndConnection:
    def test_a_tutor_who_turned_the_toggle_off_is_never_hidden_even_with_a_stale_cache(self, tutor, fake_google):
        credential = connect(tutor)
        fake_google.add_external_event(at(9, 0), at(11, 0))
        refresh(tutor)
        assert listing(tutor, include_external_busy=True) == {}
        CalendarCredential.objects.filter(pk=credential.pk).update(block_busy=False)
        assert len(listing(tutor, include_external_busy=True)) == 4

    def test_a_revoked_connection_hides_nothing(self, tutor, fake_google):
        credential = connect(tutor)
        fake_google.add_external_event(at(9, 0), at(11, 0))
        refresh(tutor)
        CalendarCredential.objects.filter(pk=credential.pk).update(revoked_at=at(0, 0))
        assert len(listing(tutor, include_external_busy=True)) == 4

    def test_a_tutor_who_never_connected_makes_no_google_call(self, tutor, fake_google):
        assert refresh(tutor) == 'not_connected'
        assert not fake_google.requests


class TestFailOpen:
    @pytest.mark.parametrize('status', [401, 403, 429, 500, 503])
    def test_a_google_error_changes_nothing_and_does_not_raise(self, tutor, fake_google, status):
        connect(tutor)
        fake_google.fail_next('list', status)
        assert refresh(tutor) == 'unavailable'
        assert len(listing(tutor, include_external_busy=True)) == 4

    def test_a_failed_refresh_keeps_the_last_good_hint_instead_of_erasing_it(self, tutor, fake_google):
        connect(tutor)
        fake_google.add_external_event(at(9, 0), at(11, 0))
        refresh(tutor)
        fake_google.fail_next('list', 429)
        assert refresh(tutor) == 'unavailable'
        assert listing(tutor, include_external_busy=True) == {}

    def test_a_revoked_google_grant_stops_the_sync_and_marks_the_connection_once(self, tutor, fake_google):
        credential = connect(tutor)
        fake_google.revoke()
        assert refresh(tutor) == 'unavailable'
        credential.refresh_from_db()
        assert credential.revoked_at is not None and credential.last_error == 'invalid_grant'
        assert refresh(tutor) == 'not_connected'
        assert len(listing(tutor, include_external_busy=True)) == 4

    def test_an_unreadable_cache_never_breaks_the_listing(self, tutor, fake_google):
        connect(tutor)
        with mock.patch('apps.integrations.google_calendar.cache', **{'get.side_effect': ConnectionError('redis down')}):
            assert len(listing(tutor, include_external_busy=True)) == 4

    def test_the_public_endpoint_still_answers_200_when_google_is_down(self, tutor, fake_google):
        connect(tutor)
        fake_google.fail_next('list', 500)
        refresh(tutor)
        response = APIClient().get(f'/api/v1/bookings/slots/{tutor.id}/?days=7')
        assert response.status_code == 200
        assert response.json()['slot_count'] > 0


class TestPublicEndpoint:
    def test_the_slots_endpoint_applies_the_hint(self, tutor, fake_google):
        connect(tutor)
        fake_google.add_external_event(at(9, 0), at(11, 0))
        refresh(tutor)
        url = f'/api/v1/bookings/slots/{tutor.id}/?days=7'
        monday = [s for s in APIClient().get(url).json()['slots'] if s['start_time_utc'].startswith('2026-01-05')]
        assert monday == []


class TestFanOut:
    def test_the_periodic_task_queues_one_job_per_connected_opted_in_tutor(self, tutor, fake_google):
        connect(tutor)
        opted_out = f.make_teacher_profile(f.make_user('teacher'))
        connect(opted_out, block_busy=False)
        never = f.make_teacher_profile(f.make_user('teacher'))                      # noqa: F841
        revoked = f.make_teacher_profile(f.make_user('teacher'))
        connect(revoked, revoked_at=at(0, 0))
        applicant = f.make_teacher_profile(f.make_user('teacher'), status='applied')
        connect(applicant)
        with mock.patch.object(tasks.sync_tutor_busy_task, 'delay') as delay:
            result = tasks.reconcile_teacher_gcal_task()
        assert result == {'queued_tutors': 1}
        delay.assert_called_once_with(str(tutor.id))

    def test_a_tutor_who_opted_out_has_a_stale_hint_cleared(self, tutor, fake_google):
        credential = connect(tutor)
        fake_google.add_external_event(at(9, 0), at(11, 0))
        refresh(tutor)
        CalendarCredential.objects.filter(pk=credential.pk).update(block_busy=False)
        assert refresh(tutor) == 'opted_out'
        assert cache.get(f'gcal:busy:{tutor.id}') == []
