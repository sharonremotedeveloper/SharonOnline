"""Ownership-safe cache primitives used by slot and periodic-task locks.

Redis operations are executed with Lua so comparison and mutation are one atomic
operation.  The local-memory fallback is protected by a process lock for unit
tests and single-process development only.
"""
from __future__ import annotations

import threading

from django.core.cache import cache


class LockBackendUnavailable(RuntimeError):
    """The configured lock backend could not safely perform the operation."""


_local_guard = threading.RLock()
_COMPARE_DELETE = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""
_COMPARE_EXPIRE = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('pexpire', KEYS[1], ARGV[2])
end
return 0
"""


def _redis_client(key: str, expected):
    """
    Return (redis client, transformed key, expected value AS REDIS STORES IT), or None for a non-Redis cache.

    Django's Redis cache backend serializes every value it writes (strings are pickled), and the Lua scripts compare the raw bytes
    held by the server. The expected token must therefore go through the cache's own serializer, otherwise the comparison never
    matches and even the rightful owner can neither release nor extend its lock.
    """
    backend_client = getattr(cache, "_cache", None)
    get_client = getattr(backend_client, "get_client", None)
    if not callable(get_client):
        return None
    try:
        stored_form = backend_client._serializer.dumps(expected)
        return get_client(key, write=True), cache.make_key(key), stored_form
    except Exception as exc:  # configuration/network failures must never degrade to an unsafe operation
        raise LockBackendUnavailable("Redis lock backend is unavailable.") from exc


def compare_and_delete(key: str, expected: str) -> bool:
    redis_target = _redis_client(key, expected)
    if redis_target:
        client, real_key, stored_form = redis_target
        try:
            return bool(client.eval(_COMPARE_DELETE, 1, real_key, stored_form))
        except Exception as exc:
            raise LockBackendUnavailable("Atomic lock release failed.") from exc
    with _local_guard:
        if cache.get(key) != expected:
            return False
        cache.delete(key)
        return True


def compare_and_expire(key: str, expected: str, seconds: int) -> bool:
    redis_target = _redis_client(key, expected)
    if redis_target:
        client, real_key, stored_form = redis_target
        try:
            return bool(client.eval(_COMPARE_EXPIRE, 1, real_key, stored_form, max(1, seconds) * 1000))
        except Exception as exc:
            raise LockBackendUnavailable("Atomic lock renewal failed.") from exc
    with _local_guard:
        if cache.get(key) != expected:
            return False
        return bool(cache.touch(key, max(1, seconds)))
