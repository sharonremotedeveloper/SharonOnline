"""Race tests that intentionally use Redis, never the in-memory test cache.

Run with REDIS_TEST_URL pointing at a disposable Redis database, for example:
REDIS_TEST_URL=redis://127.0.0.1:6379/15 pytest -m redis
"""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.core.cache import cache, caches

from apps.bookings.services.lock_service import (
    acquire_slot_lock,
    build_slot_lock_key,
    extend_slot_lock,
    release_slot_lock,
)


REDIS_TEST_URL = os.environ.get('REDIS_TEST_URL')
pytestmark = [
    pytest.mark.django_db,
    pytest.mark.redis,
    pytest.mark.skipif(not REDIS_TEST_URL, reason='REDIS_TEST_URL is required for Redis integration races'),
]


@pytest.fixture(autouse=True)
def real_redis_cache(settings, test_environment_settings):
    settings.CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_TEST_URL,
            'KEY_PREFIX': f'sharon-lock-test-{uuid.uuid4().hex}',
        }
    }
    caches.close_all()
    cache.clear()
    yield
    cache.clear()
    caches.close_all()


def test_real_redis_allows_exactly_one_contender():
    teacher_id = str(uuid.uuid4())
    slot = '2026-10-15T09:00:00Z'
    contenders = [(str(uuid.uuid4()), uuid.uuid4().hex) for _ in range(50)]

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(
            lambda contender: acquire_slot_lock(
                teacher_id, slot, contender[0], token=contender[1]
            ),
            contenders,
        ))

    assert results.count(True) == 1
    winner = contenders[results.index(True)]
    assert cache.get(build_slot_lock_key(teacher_id, slot)) == winner[1]
    assert release_slot_lock(teacher_id, slot, winner[0], token=winner[1]) is True


def test_real_redis_stale_owner_cannot_mutate_successor():
    teacher_id = str(uuid.uuid4())
    slot = '2026-10-15T10:00:00Z'
    key = build_slot_lock_key(teacher_id, slot)

    assert acquire_slot_lock(teacher_id, slot, 'student-a', token='owner-a') is True
    cache.delete(key)  # expiry boundary
    assert acquire_slot_lock(teacher_id, slot, 'student-b', token='owner-b') is True

    assert release_slot_lock(teacher_id, slot, 'student-a', token='owner-a') is False
    assert extend_slot_lock(teacher_id, slot, 'student-a', 900, token='owner-a') is False
    assert cache.get(key) == 'owner-b'


def test_real_redis_the_rightful_owner_can_extend_and_release():
    """Positive controls. Django's Redis cache pickles values, so these fail if the Lua owner check compares plain strings."""
    teacher_id = str(uuid.uuid4())
    slot = '2026-10-15T11:00:00Z'
    key = build_slot_lock_key(teacher_id, slot)

    assert acquire_slot_lock(teacher_id, slot, 'student-a', token='owner-a') is True
    assert extend_slot_lock(teacher_id, slot, 'student-a', 900, token='owner-a') is True       # checkout extends the hold this way
    assert 0 < cache._cache.get_client(key).ttl(cache.make_key(key)) <= 900
    assert extend_slot_lock(teacher_id, slot, 'student-b', 900, token='owner-b') is False
    assert release_slot_lock(teacher_id, slot, 'student-b', token='owner-b') is False
    assert cache.get(key) == 'owner-a'
    assert release_slot_lock(teacher_id, slot, 'student-a', token='owner-a') is True
    assert cache.get(key) is None


def test_real_redis_a_stale_owner_is_refused_while_the_successor_still_works():
    teacher_id = str(uuid.uuid4())
    slot = '2026-10-15T11:30:00Z'
    key = build_slot_lock_key(teacher_id, slot)
    assert acquire_slot_lock(teacher_id, slot, 'student-a', token='owner-a') is True
    cache.delete(key)
    assert acquire_slot_lock(teacher_id, slot, 'student-b', token='owner-b') is True
    assert release_slot_lock(teacher_id, slot, 'student-a', token='owner-a') is False
    assert extend_slot_lock(teacher_id, slot, 'student-b', 900, token='owner-b') is True
    assert release_slot_lock(teacher_id, slot, 'student-b', token='owner-b') is True


def test_real_redis_a_periodic_task_releases_its_own_lock():
    from apps.common.locks import distributed_task_lock

    @distributed_task_lock(f'lock:beat:race-{uuid.uuid4().hex}', timeout_seconds=300)
    def job():
        return 'ran'

    assert job() == 'ran'
    assert job() == 'ran'          # a lock that was not released would make this a skipped run
