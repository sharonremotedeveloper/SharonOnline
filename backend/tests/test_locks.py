import pytest
from django.core.cache import cache

from apps.bookings.services.lock_service import (
    acquire_slot_lock,
    build_slot_lock_key,
    extend_slot_lock,
    is_slot_locked,
    release_slot_lock,
)

@pytest.mark.django_db
def test_pessimistic_lock_concurrency():
    teacher_id = "11111111-1111-1111-1111-111111111111"
    slot_utc = "2026-10-01T07:00:00Z"
    student_a = "22222222-2222-2222-2222-222222222222"
    student_b = "33333333-3333-3333-3333-333333333333"

    # Clean prior state if any
    cache.delete(build_slot_lock_key(teacher_id, slot_utc))

    # 1. Student A acquires lock
    assert acquire_slot_lock(teacher_id, slot_utc, student_a) is True
    assert is_slot_locked(teacher_id, slot_utc) is True

    # 2. Student B attempts to acquire same slot simultaneously -> MUST FAIL
    assert acquire_slot_lock(teacher_id, slot_utc, student_b) is False

    # 3. Student A releases lock
    assert release_slot_lock(teacher_id, slot_utc, student_a) is True
    assert is_slot_locked(teacher_id, slot_utc) is False

    # 4. Now Student B can acquire
    assert acquire_slot_lock(teacher_id, slot_utc, student_b) is True
    release_slot_lock(teacher_id, slot_utc, student_b)


@pytest.mark.django_db
def test_expired_owner_cannot_release_or_renew_successor_lock():
    teacher_id = "44444444-4444-4444-4444-444444444444"
    slot_utc = "2026-10-01T08:00:00Z"
    key = build_slot_lock_key(teacher_id, slot_utc)

    assert acquire_slot_lock(teacher_id, slot_utc, "student-a", token="token-a") is True
    # Simulate expiry followed by a new reservation winning the same cache key.
    cache.delete(key)
    assert acquire_slot_lock(teacher_id, slot_utc, "student-b", token="token-b") is True

    assert release_slot_lock(teacher_id, slot_utc, "student-a", token="token-a") is False
    assert extend_slot_lock(teacher_id, slot_utc, "student-a", 900, token="token-a") is False
    assert cache.get(key) == "token-b"
    assert release_slot_lock(teacher_id, slot_utc, "student-b", token="token-b") is True
