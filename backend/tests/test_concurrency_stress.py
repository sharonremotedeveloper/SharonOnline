import pytest
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from apps.bookings.services.lock_service import (
    acquire_slot_lock,
    release_slot_lock,
    is_slot_locked,
    build_slot_lock_key
)
from django.core.cache import cache

@pytest.mark.django_db
def test_simultaneous_50_worker_lock_contention():
    """
    Stress test: Simulates 50 concurrent threads attempting to reserve the exact same
    teacher slot simultaneously. Exactly 1 must win, and 49 must fail.
    Zero race conditions, zero deadlocks.
    """
    teacher_id = str(uuid.uuid4())
    slot_utc = "2026-10-15T09:00:00Z"
    concurrency_count = 50

    # Ensure clean slate
    cache.delete(build_slot_lock_key(teacher_id, slot_utc))

    # Generate 50 unique student IDs
    student_ids = [str(uuid.uuid4()) for _ in range(concurrency_count)]

    results = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        future_to_student = {
            executor.submit(acquire_slot_lock, teacher_id, slot_utc, s_id): s_id
            for s_id in student_ids
        }
        for future in as_completed(future_to_student):
            results.append(future.result())

    # Exactly one thread acquired the lock
    assert results.count(True) == 1, f"Expected exactly 1 winner, got {results.count(True)}"
    assert results.count(False) == concurrency_count - 1

    # Verify state in cache
    assert is_slot_locked(teacher_id, slot_utc) is True

    # Cleanup
    winning_student = cache.get(build_slot_lock_key(teacher_id, slot_utc))
    release_slot_lock(teacher_id, slot_utc, winning_student)
    assert is_slot_locked(teacher_id, slot_utc) is False


@pytest.mark.django_db
def test_multislot_concurrent_isolation():
    """
    Verifies that concurrent lock requests on DIFFERENT slots do not block or interfere
    with one another. All 25 distinct slot reservation attempts must succeed.
    """
    teacher_id = str(uuid.uuid4())
    slot_count = 25
    slots = [f"2026-10-15T{hour:02d}:00:00Z" for hour in range(slot_count)]
    student_id = str(uuid.uuid4())

    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [
            executor.submit(acquire_slot_lock, teacher_id, slot, student_id)
            for slot in slots
        ]
        for f in as_completed(futures):
            results.append(f.result())

    assert all(results) is True
    assert len(results) == slot_count

    # Cleanup all
    for slot in slots:
        assert release_slot_lock(teacher_id, slot, student_id) is True
        assert is_slot_locked(teacher_id, slot) is False


@pytest.mark.django_db
def test_unauthorized_lock_release_rejected():
    """
    Security check: A student who does not hold the slot lock CANNOT release it.
    Only the legitimate holder can clear it.
    """
    teacher_id = str(uuid.uuid4())
    slot_utc = "2026-10-20T14:00:00Z"
    legitimate_student = str(uuid.uuid4())
    imposter_student = str(uuid.uuid4())

    cache.delete(build_slot_lock_key(teacher_id, slot_utc))

    # 1. Legitimate student acquires lock
    assert acquire_slot_lock(teacher_id, slot_utc, legitimate_student) is True

    # 2. Imposter attempts to release lock -> Must return False
    assert release_slot_lock(teacher_id, slot_utc, imposter_student) is False
    assert is_slot_locked(teacher_id, slot_utc) is True

    # 3. Legitimate student releases lock -> Returns True
    assert release_slot_lock(teacher_id, slot_utc, legitimate_student) is True
    assert is_slot_locked(teacher_id, slot_utc) is False
