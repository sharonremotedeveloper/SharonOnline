from django.core.cache import cache
import logging
import uuid

from apps.common.cache_locks import compare_and_delete, compare_and_expire

logger = logging.getLogger(__name__)

LOCK_DURATION_SECONDS = 600  # 10 minutes hold

def build_slot_lock_key(teacher_id: str, slot_timestamp_utc: str) -> str:
    # Normalize timestamp string to prevent whitespace discrepancies
    clean_ts = slot_timestamp_utc.strip().replace(" ", "T")
    return f"lock:slot:{teacher_id}:{clean_ts}"

def acquire_slot_lock(teacher_id: str, slot_timestamp_utc: str, student_id: str, token: str = None) -> bool:
    """
    Attempts to acquire an atomic 10-minute pessimistic lock for a specific teacher slot.
    Returns True if the lock was acquired, False if the slot is currently held by someone else.
    """
    key = build_slot_lock_key(teacher_id, slot_timestamp_utc)
    # cache.add sets the value only if it does not already exist (SET NX)
    lock_token = token or str(student_id)  # legacy/test callers; production reservations always pass a UUID token
    acquired = cache.add(key, lock_token, timeout=LOCK_DURATION_SECONDS)
    if acquired:
        logger.info(f"Slot lock acquired for key={key} by student={student_id}")
    else:
        logger.warning(f"Slot lock conflict for key={key}, already reserved by {cache.get(key)}")
    return acquired

def release_slot_lock(teacher_id: str, slot_timestamp_utc: str, student_id: str = None, token: str = None) -> bool:
    """
    Releases the slot lock. If student_id is provided, only deletes if the lock owner matches.
    """
    key = build_slot_lock_key(teacher_id, slot_timestamp_utc)
    expected = token or (str(student_id) if student_id is not None else None)
    if expected is None:
        logger.error("Refused ownerless slot-lock release for key=%s", key)
        return False
    if cache.get(key) is None:
        return True
    if compare_and_delete(key, expected):
        logger.info(f"Slot lock released for key={key}")
        return True
    return False

def is_slot_locked(teacher_id: str, slot_timestamp_utc: str) -> bool:
    key = build_slot_lock_key(teacher_id, slot_timestamp_utc)
    return cache.get(key) is not None


def extend_slot_lock(teacher_id: str, slot_timestamp_utc: str, student_id: str, seconds: int, token: str = None) -> bool:
    """
    Make sure `student_id` holds the slot lock for at least `seconds` more (used when a payment starts, Task 9.4).
    - their own live lock is extended;
    - a lock that lapsed and is still free is re-taken;
    - a lock held by anyone else is never touched: returns False (the caller must not take that student's money).
    """
    key = build_slot_lock_key(teacher_id, slot_timestamp_utc)
    expected = token or str(student_id)
    holder = cache.get(key)
    if holder is None:
        return cache.add(key, expected, timeout=seconds)
    if str(holder) != expected:
        return False
    return compare_and_expire(key, expected, seconds)


def new_slot_lock_token() -> str:
    return uuid.uuid4().hex
