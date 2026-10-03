"""
Lock ownership must work through Django's real Redis cache backend, which PICKLES string values.

The atomic compare-and-delete / compare-and-expire scripts run inside Redis and compare the stored bytes. If they compare
against the plain token instead of the serialized one, every owner check fails on a real server (the in-memory test cache hides
this): the rightful holder could never extend or release its lock, so checkout would refuse every payment as "slot taken".

No Redis server is needed here: `ByteRedis` stores values as raw bytes exactly as Redis does and implements the two scripts with
Redis's byte-for-byte comparison, and the cache is Django's genuine `RedisCache` backend (real pickling). The real-server run is
`tests/integration/test_redis_lock_races.py` (CI job `redis-races`).
"""
import uuid

import pytest
from django.core.cache import cache, caches
from django.core.cache.backends.redis import RedisCacheClient

from apps.bookings.services.lock_service import (acquire_slot_lock, build_slot_lock_key, extend_slot_lock, is_slot_locked,
                                                 release_slot_lock)
from apps.common.cache_locks import compare_and_delete, compare_and_expire
from apps.common.locks import distributed_task_lock


class ByteRedis:
    """The few Redis commands the lock code uses, with Redis semantics: values are bytes, comparisons are exact."""

    def __init__(self):
        self.data, self.ttl = {}, {}

    @staticmethod
    def _bytes(value):
        if isinstance(value, bytes):
            return value
        return str(value).encode()                      # Redis stores integers (and numeric args) as their decimal text

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.data:
            return None
        self.data[key] = self._bytes(value)
        self.ttl[key] = ex
        return True

    def get(self, key):
        return self.data.get(key)

    def delete(self, *keys):
        return sum(self.data.pop(k, None) is not None for k in keys)

    def expire(self, key, seconds):
        if key not in self.data:
            return False
        self.ttl[key] = seconds
        return True

    def eval(self, script, numkeys, *args):
        keys, argv = args[:numkeys], [self._bytes(a) for a in args[numkeys:]]
        if self.data.get(keys[0]) != argv[0]:           # `redis.call('get', KEYS[1]) == ARGV[1]`
            return 0
        if 'pexpire' in script:
            self.ttl[keys[0]] = int(argv[1]) / 1000
            return 1
        self.data.pop(keys[0])
        return 1


@pytest.fixture
def redis_like(settings, test_environment_settings, monkeypatch):
    server = ByteRedis()
    settings.CACHES = {'default': {'BACKEND': 'django.core.cache.backends.redis.RedisCache', 'LOCATION': 'redis://emulated:6379/0',
                                   'KEY_PREFIX': 'lockser'}}
    caches.close_all()
    monkeypatch.setattr(RedisCacheClient, 'get_client', lambda self, key=None, *, write=False: server)
    yield server
    caches.close_all()


def real_key(key):
    return cache.make_key(key)


def test_the_stand_in_really_stores_the_pickled_form(redis_like):
    """Guards the premise of every test here: the server holds pickled bytes, not the plain token."""
    assert cache.add('probe', 'tok-1', timeout=30) is True
    assert redis_like.get(real_key('probe')) != b'tok-1'
    assert cache.get('probe') == 'tok-1'


def test_the_holder_can_release_its_slot_lock(redis_like):
    teacher, slot = str(uuid.uuid4()), '2026-10-15T09:00:00Z'
    assert acquire_slot_lock(teacher, slot, 'student-a', token='owner-a') is True
    assert release_slot_lock(teacher, slot, 'student-a', token='owner-a') is True
    assert is_slot_locked(teacher, slot) is False


def test_someone_else_cannot_release_it(redis_like):
    teacher, slot = str(uuid.uuid4()), '2026-10-15T09:30:00Z'
    acquire_slot_lock(teacher, slot, 'student-a', token='owner-a')
    assert release_slot_lock(teacher, slot, 'student-b', token='owner-b') is False
    assert is_slot_locked(teacher, slot) is True


def test_the_holder_can_extend_its_lock_which_is_what_checkout_needs(redis_like):
    teacher, slot = str(uuid.uuid4()), '2026-10-15T10:00:00Z'
    acquire_slot_lock(teacher, slot, 'student-a', token='owner-a')
    assert extend_slot_lock(teacher, slot, 'student-a', 900, token='owner-a') is True
    assert redis_like.ttl[real_key(build_slot_lock_key(teacher, slot))] == 900        # the TTL really moved
    assert extend_slot_lock(teacher, slot, 'student-b', 900, token='owner-b') is False


def test_a_stale_owner_cannot_touch_the_successor_but_the_successor_can(redis_like):
    teacher, slot = str(uuid.uuid4()), '2026-10-15T10:30:00Z'
    key = build_slot_lock_key(teacher, slot)
    assert acquire_slot_lock(teacher, slot, 'student-a', token='owner-a') is True
    cache.delete(key)                                                                  # the first lock expired
    assert acquire_slot_lock(teacher, slot, 'student-b', token='owner-b') is True
    assert release_slot_lock(teacher, slot, 'student-a', token='owner-a') is False
    assert extend_slot_lock(teacher, slot, 'student-a', 900, token='owner-a') is False
    assert cache.get(key) == 'owner-b'
    assert extend_slot_lock(teacher, slot, 'student-b', 900, token='owner-b') is True    # positive control: the live owner works
    assert release_slot_lock(teacher, slot, 'student-b', token='owner-b') is True


@pytest.mark.parametrize('token', ['plain', '0123456789', 'uuid-' + uuid.uuid4().hex, 'ünïcode-tøken', ''])
def test_any_string_token_round_trips(redis_like, token):
    token = token or 'x'
    assert cache.add('k', token, timeout=60) is True
    assert compare_and_expire('k', token, 120) is True
    assert compare_and_delete('k', token + 'x') is False
    assert compare_and_delete('k', token) is True
    assert cache.get('k') is None


def test_a_periodic_task_lock_is_released_when_the_task_finishes(redis_like):
    calls = []

    @distributed_task_lock('lock:beat:serialization-check', timeout_seconds=300)
    def job():
        calls.append(1)
        return 'ran'

    assert job() == 'ran'
    assert job() == 'ran'                       # the first run released the lock; if it had not, this would be 'skipped'
    assert len(calls) == 2


def test_a_running_task_blocks_a_second_worker_but_only_until_it_finishes(redis_like):
    seen = []

    @distributed_task_lock('lock:beat:overlap', timeout_seconds=300)
    def job():
        seen.append(job_inner())
        return 'outer'

    def job_inner():
        return job_wrapped()

    job_wrapped = distributed_task_lock('lock:beat:overlap', timeout_seconds=300)(lambda: 'inner')
    assert job() == 'outer'
    assert seen == [{'status': 'skipped', 'reason': 'lock_active'}]         # the peer was refused while the first held the lock
    assert job_wrapped() == 'inner'                                          # and is allowed once it finished
