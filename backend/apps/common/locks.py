import functools
import logging
from django.core.cache import cache

logger = logging.getLogger(__name__)

def distributed_task_lock(lock_key_pattern: str, timeout_seconds: int = 50, release_on_success: bool = True):
    """
    Decorator guaranteeing mutual exclusion for periodic Celery tasks across multi-worker clusters.
    Uses atomic cache.add() (SET NX) to ensure that only a single worker instance runs a scheduled
    beat cycle even when multiple workers receive ticks simultaneously.

    Args:
        lock_key_pattern: The Redis cache key used as the mutex.
        timeout_seconds: TTL for the mutex lock before it automatically expires.
        release_on_success: Whether to delete the lock immediately upon task completion.
    """
    def decorator(task_func):
        @functools.wraps(task_func)
        def wrapper(*args, **kwargs):
            lock_acquired = cache.add(lock_key_pattern, "LOCKED", timeout=timeout_seconds)
            if not lock_acquired:
                logger.info(
                    f"Periodic task '{task_func.__name__}' skipped: lock '{lock_key_pattern}' "
                    f"already acquired by peer worker."
                )
                return {"status": "skipped", "reason": "lock_active"}

            try:
                return task_func(*args, **kwargs)
            finally:
                if release_on_success:
                    cache.delete(lock_key_pattern)

        return wrapper
    return decorator
