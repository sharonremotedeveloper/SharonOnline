"""Slot listing reads every Redis hold in ONE round trip (it did one GET per slot: ~3.3 s for one tutor on Upstash)."""
from datetime import date, datetime, time, timezone as dt_tz
from unittest import mock

import pytest

import factories as f
from apps.bookings.services.lock_service import acquire_slot_lock
from apps.bookings.services.slot_generator import generate_teacher_slots
from apps.teachers.models import TeacherAvailability

MONDAY = date(2026, 1, 5)


@pytest.fixture
def tutor(db, frozen_clock):
    frozen_clock.set(datetime(2026, 1, 1, tzinfo=dt_tz.utc))
    profile = f.make_teacher_profile(f.make_user('teacher', timezone='UTC'), availability=False)
    TeacherAvailability.objects.create(teacher=profile, day_of_week=0, start_time=time(9, 0), end_time=time(11, 0),
                                       is_active=True)
    return profile


def test_listing_uses_one_batched_lock_lookup(tutor):
    # django-redis turns get_many into one MGET; the test LocMem cache loops internally, so assert the call contract.
    from apps.bookings.services import lock_service
    with mock.patch('apps.bookings.services.slot_generator.locked_slots', wraps=lock_service.locked_slots) as batched:
        slots = generate_teacher_slots(teacher=tutor, start_date=MONDAY, days_ahead=1)
    assert len(slots) == 4 and batched.call_count == 1
    assert len(batched.call_args.args[1]) == 4  # every open slot in the single lookup


def test_a_held_slot_is_still_reported_reserved(tutor):
    held = datetime(2026, 1, 5, 9, 30, tzinfo=dt_tz.utc).isoformat()
    assert acquire_slot_lock(str(tutor.id), held, 'student-1')
    status = {s['start_time_utc']: s['status'] for s in generate_teacher_slots(teacher=tutor, start_date=MONDAY, days_ahead=1)}
    assert status[held] == 'reserved'
    assert sorted(status.values()) == ['available', 'available', 'available', 'reserved']
