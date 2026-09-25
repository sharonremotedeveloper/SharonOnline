from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)

LOCK_DURATION_SECONDS = 600  # 10 minutes hold

def build_slot_lock_key(teacher_id: str, slot_timestamp_utc: str) -> str:
    # Normalize timestamp string to prevent whitespace discrepancies
    clean_ts = slot_timestamp_utc.strip().replace(" ", "T")
    return f"lock:slot:{teacher_id}:{clean_ts}"

def acquire_slot_lock(teacher_id: str, slot_timestamp_utc: str, student_id: str) -> bool:
    """
    Attempts to acquire an atomic 10-minute pessimistic lock for a specific teacher slot.
    Returns True if the lock was acquired, False if the slot is currently held by someone else.
    """
    key = build_slot_lock_key(teacher_id, slot_timestamp_utc)
    # cache.add sets the value only if it does not already exist (SET NX)
    acquired = cache.add(key, str(student_id), timeout=LOCK_DURATION_SECONDS)
    if acquired:
        logger.info(f"Slot lock acquired for key={key} by student={student_id}")
    else:
        logger.warning(f"Slot lock conflict for key={key}, already reserved by {cache.get(key)}")
    return acquired

def release_slot_lock(teacher_id: str, slot_timestamp_utc: str, student_id: str = None) -> bool:
    """
    Releases the slot lock. If student_id is provided, only deletes if the lock owner matches.
    """
    key = build_slot_lock_key(teacher_id, slot_timestamp_utc)
    current_holder = cache.get(key)
    if current_holder is None:
        return True
    if student_id is None or str(current_holder) == str(student_id):
        cache.delete(key)
        logger.info(f"Slot lock released for key={key}")
        return True
    return False

def is_slot_locked(teacher_id: str, slot_timestamp_utc: str) -> bool:
    key = build_slot_lock_key(teacher_id, slot_timestamp_utc)
    return cache.get(key) is not None
