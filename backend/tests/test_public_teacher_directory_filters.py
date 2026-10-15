"""Public directory filters must agree with the bookable slot grid."""
from datetime import datetime, time, timedelta, timezone

import pytest
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

import factories as f
from apps.bookings.models import Booking
from apps.bookings.services.lock_service import build_slot_lock_key
from apps.integrations.google_calendar import busy_cache_key
from apps.integrations.models import CalendarCredential
from apps.teachers.models import TeacherAvailability, TeacherDateOverride, TeacherTimeOff

pytestmark = pytest.mark.django_db
URL = '/api/v1/teachers/'
NOW = datetime(2026, 1, 5, 8, 25, tzinfo=timezone.utc)  # Monday, 10:25 Johannesburg


def tutor_at(day, start, end, **fields):
    tutor = f.make_teacher_profile(availability=False, **fields)
    TeacherAvailability.objects.create(teacher=tutor, day_of_week=day,
                                       start_time=start, end_time=end)
    return tutor


def listed(**params):
    response = APIClient().get(URL, params)
    assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize('value', ['', 'yes', '1', 'false-ish', 'TRUE '])
@pytest.mark.parametrize('param', ['backup_power', 'free_next_24h'])
def test_rejects_invalid_boolean_parameters(param, value):
    assert APIClient().get(URL, {param: value}).status_code == 400


def test_backup_power_filters_declaration_and_exposes_it_on_list_and_detail():
    declared = tutor_at(0, time(9), time(12), has_inverter_backup=True)
    tutor_at(0, time(9), time(12), has_lte_failover=True)
    body = listed(backup_power='true')
    assert body['count'] == 1
    assert body['results'][0]['id'] == str(declared.id)
    assert body['results'][0]['has_inverter_backup'] is True
    assert APIClient().get(f'{URL}{declared.id}/').json()['has_inverter_backup'] is True


def test_combined_filters_use_rolling_utc_window_and_hide_unbookable(frozen_clock):
    frozen_clock.set(NOW)
    matching = tutor_at(1, time(10), time(10, 25), has_inverter_backup=True)
    tutor_at(1, time(10, 30), time(10, 55), has_inverter_backup=True)  # beyond 24 hours
    tutor_at(1, time(10), time(10, 25), has_inverter_backup=False)
    tutor_at(1, time(10), time(10, 25), has_inverter_backup=True, status='suspended')
    body = listed(backup_power='true', free_next_24h='true')
    assert body['count'] == 1
    assert [row['id'] for row in body['results']] == [str(matching.id)]


def test_free_filter_respects_overrides_time_off_bookings_holds_and_locks(frozen_clock):
    frozen_clock.set(NOW)
    start = datetime(2026, 1, 6, 8, tzinfo=timezone.utc)
    open_tutor = tutor_at(1, time(10), time(10, 25))
    override = f.make_teacher_profile(availability=False)
    TeacherDateOverride.objects.create(teacher=override, date=start.date(), kind='open',
                                       start_time=time(10), end_time=time(10, 25))
    off = tutor_at(1, time(10), time(10, 25))
    TeacherTimeOff.objects.create(teacher=off, start_utc=start, end_utc=start + timedelta(minutes=25))
    booked = tutor_at(1, time(10), time(10, 25))
    f.make_booking(teacher=booked, start=start, status=Booking.Status.CONFIRMED)
    held = tutor_at(1, time(10), time(10, 25))
    hold = f.make_booking(teacher=held, start=start, status=Booking.Status.PENDING_PAYMENT)
    Booking.objects.filter(pk=hold.pk).update(created_at=NOW)
    locked = tutor_at(1, time(10), time(10, 25))
    cache.set(build_slot_lock_key(str(locked.id), start.isoformat()), 'another-student', 600)
    ids = {row['id'] for row in listed(free_next_24h='true')['results']}
    assert ids == {str(open_tutor.id), str(override.id)}


def test_free_filter_counts_matches_before_pagination(frozen_clock):
    frozen_clock.set(NOW)
    tutors = [tutor_at(1, time(10), time(10, 25)) for _ in range(21)]
    tutor_at(1, time(10, 30), time(10, 55))  # excluded even if it sorts ahead of a match
    first = listed(free_next_24h='true', page=1, page_size=12)
    second = listed(free_next_24h='true', page=2, page_size=12)
    assert first['count'] == second['count'] == 21
    assert len(first['results']) == 12 and len(second['results']) == 9
    assert {row['id'] for row in first['results'] + second['results']} == {str(t.id) for t in tutors}


def test_directory_page_size_matches_ui_when_13_to_20_tutors(frozen_clock):
    frozen_clock.set(NOW)
    for _ in range(13):
        tutor_at(1, time(10), time(10, 25))
    first = listed(free_next_24h='true', page_size=12)
    second = listed(free_next_24h='true', page_size=12, page=2)
    assert first['count'] == second['count'] == 13
    assert len(first['results']) == 12
    assert len(second['results']) == 1


def test_free_filter_respects_notice_and_cached_busy_hint(frozen_clock):
    frozen_clock.set(NOW)
    too_close = tutor_at(0, time(10, 30), time(10, 55))
    busy = tutor_at(1, time(10), time(10, 25))
    CalendarCredential.objects.create(user=busy.user, refresh_token_enc='unused-by-cache-read', block_busy=True)
    start = datetime(2026, 1, 6, 8, tzinfo=timezone.utc)
    cache.set(busy_cache_key(busy.id), [(start.isoformat(), (start + timedelta(minutes=25)).isoformat())])
    free = tutor_at(0, time(11), time(11, 25))
    ids = {row['id'] for row in listed(free_next_24h='true')['results']}
    assert ids == {str(free.id)}
    assert str(too_close.id) not in ids


def test_explicit_false_is_unfiltered(frozen_clock):
    frozen_clock.set(NOW)
    tutor_at(1, time(10, 30), time(10, 55), has_inverter_backup=False)
    assert listed(backup_power='false', free_next_24h='false')['count'] == 1


def test_directory_batch_does_not_query_once_per_tutor(frozen_clock):
    frozen_clock.set(NOW)
    for _ in range(21):
        tutor_at(1, time(10), time(10, 25))
    with CaptureQueriesContext(connection) as queries:
        assert listed(free_next_24h='true')['count'] == 21
    assert len(queries) <= 12


def test_tutor_budget_returns_503_before_cache_work(frozen_clock, monkeypatch):
    frozen_clock.set(NOW)
    from apps.teachers.services import directory
    monkeypatch.setattr(directory, 'MAX_TUTORS', 2)
    for _ in range(3):
        tutor_at(1, time(10), time(10, 25))
    monkeypatch.setattr(directory.cache, 'get_many', lambda _: pytest.fail('no cache read expected'))
    response = APIClient().get(URL, {'free_next_24h': 'true'})
    assert response.status_code == 503
    assert response.json()['code'] == 'directory_budget_exceeded'
    assert 'Retry-After' not in response
    assert 'Refine your filters' in response.json()['detail']


def test_lock_key_budget_returns_503_without_partial_results(frozen_clock, monkeypatch):
    frozen_clock.set(NOW)
    from apps.teachers.services import directory
    monkeypatch.setattr(directory, 'MAX_LOCK_KEYS', 1)
    tutor_at(1, time(10), time(10, 25))
    tutor_at(1, time(10), time(10, 25))
    monkeypatch.setattr(directory.cache, 'get_many', lambda _: pytest.fail('no cache read expected'))
    response = APIClient().get(URL, {'free_next_24h': 'true'})
    assert response.status_code == 503
    assert response.json()['code'] == 'directory_budget_exceeded'


def test_lock_cache_failure_returns_retryable_503_without_details(frozen_clock, monkeypatch):
    frozen_clock.set(NOW)
    from apps.teachers.services import directory
    tutor_at(1, time(10), time(10, 25))

    def unavailable(_):
        raise ConnectionError('private Redis endpoint')

    monkeypatch.setattr(directory.cache, 'get_many', unavailable)
    response = APIClient().get(URL, {'free_next_24h': 'true'})
    assert response.status_code == 503
    assert response.json()['code'] == 'directory_cache_unavailable'
    assert 'private Redis endpoint' not in str(response.json())


def test_no_candidate_slots_does_not_touch_cache(frozen_clock, monkeypatch):
    frozen_clock.set(NOW)
    from apps.teachers.services import directory
    tutor_at(1, time(10, 30), time(10, 55))
    monkeypatch.setattr(directory.cache, 'get_many', lambda _: pytest.fail('no cache read expected'))
    assert listed(free_next_24h='true')['count'] == 0


def test_lock_reads_are_chunked_and_keep_exact_results(frozen_clock, monkeypatch):
    frozen_clock.set(NOW)
    from apps.teachers.services import directory
    monkeypatch.setattr(directory, 'MAX_MGET_KEYS', 1)
    tutors = [tutor_at(1, time(10), time(10, 25)) for _ in range(2)]
    original = directory.cache.get_many
    calls = []

    def get_many(keys):
        calls.append(len(keys))
        return original(keys)

    monkeypatch.setattr(directory.cache, 'get_many', get_many)
    body = listed(free_next_24h='true')
    assert body['count'] == 2
    assert {row['id'] for row in body['results']} == {str(t.id) for t in tutors}
    assert calls == [1, 1]


def test_cached_busy_failure_returns_defined_503(frozen_clock, monkeypatch):
    frozen_clock.set(NOW)
    from apps.teachers.services import directory
    tutor = tutor_at(1, time(10), time(10, 25))
    CalendarCredential.objects.create(user=tutor.user, refresh_token_enc='unused-by-cache-read', block_busy=True)

    def unavailable(_):
        raise ConnectionError('private Redis endpoint')

    monkeypatch.setattr(directory.cache, 'get_many', unavailable)
    response = APIClient().get(URL, {'free_next_24h': 'true'})
    assert response.status_code == 503
    assert response.json()['code'] == 'directory_cache_unavailable'
    assert 'private Redis endpoint' not in str(response.json())


def test_exhausted_lock_budget_after_locked_candidate_returns_503(frozen_clock, monkeypatch):
    frozen_clock.set(NOW)
    from apps.teachers.services import directory
    monkeypatch.setattr(directory, 'MAX_LOCK_KEYS', 1)
    tutor_at(0, time(11), time(11, 55))  # two starts, first locked
    calls = []

    def locked(keys):
        calls.append(len(keys))
        return {key: 'held' for key in keys}

    monkeypatch.setattr(directory.cache, 'get_many', locked)
    response = APIClient().get(URL, {'free_next_24h': 'true'})
    assert response.status_code == 503
    assert response.json()['code'] == 'directory_budget_exceeded'
    assert calls == [1]


def test_first_free_slot_avoids_later_lock_reads(frozen_clock, monkeypatch):
    frozen_clock.set(NOW)
    from apps.teachers.services import directory
    tutor_at(0, time(11), time(11, 55))
    original = directory.cache.get_many
    calls = []

    def get_many(keys):
        calls.append(len(keys))
        return original(keys)

    monkeypatch.setattr(directory.cache, 'get_many', get_many)
    assert listed(free_next_24h='true')['count'] == 1
    assert calls == [1]
