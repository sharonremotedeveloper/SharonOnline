"""
Zoom Server-to-Server OAuth token cache (Slice Z1, F0 condition C3; docs/ZOOM_ATTENDANCE.md "Client contract").

* One token per Zoom account id in the Django cache (Redis in production, shared by every worker), kept for
  `expires_in - 60 s` so it is never used in its last minute. A token living 60 s or less is used once and not cached.
* Single-flight: the worker that wins `cache.add(<key>:lock)` fetches; the others poll the cache every
  POLL_SECONDS for at most ZOOM_TOKEN_WAIT_SECONDS and then fetch themselves (a stuck or dead fetcher never blocks them).
  The lock outlives the worst-case fetch (`lock_seconds()`), so a live fetcher never loses it mid-request. It is released
  only by its owner (compare the owner token first).
* Failures are never cached: the fetch raises and nothing is written.
* `invalidate_token(account, token)` (after a 401) deletes the cached token only if it is still the one that failed, so a
  newer token another worker just stored survives.
* **A cache outage never breaks Zoom.** Every cache call is guarded: a failing `get/add` degrades to a direct token fetch
  (no caching, no lock), a failing `set/delete` is skipped. One warning per failure with the error TYPE only.

The token is a bearer secret: it lives only in the cache and in memory, never in a log line.
"""
import hashlib
import logging
import time
import uuid

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

EARLY_REFRESH_SECONDS = 60
LOCK_MARGIN_SECONDS = 5
POLL_SECONDS = 0.25


def _sleep(seconds):
    time.sleep(seconds)


def _degraded(op: str, exc: Exception) -> None:
    logger.warning('Zoom token cache unavailable (%s): %s; continuing without it', op, type(exc).__name__)


def lock_seconds() -> int:
    """Longer than the worst-case token fetch: every try can take the HTTP timeout plus its back-off wait."""
    per_try = settings.ZOOM_HTTP_TIMEOUT_SECONDS + settings.ZOOM_RETRY_AFTER_CAP_SECONDS
    return settings.ZOOM_HTTP_MAX_ATTEMPTS * per_try + LOCK_MARGIN_SECONDS


def token_cache_key(account_id: str) -> str:
    """Per account; hashed so any account id is a safe cache key (and not echoed into key listings)."""
    return 'zoom:s2s-token:' + hashlib.sha256(str(account_id).encode()).hexdigest()[:24]


def lock_key(key: str) -> str:
    return f'{key}:lock'


def acquire_lock(key: str):
    """Owner token when this worker won the lock, else None. A cache error propagates (the caller degrades)."""
    owner = uuid.uuid4().hex
    return owner if cache.add(lock_key(key), owner, lock_seconds()) else None


def release_lock(key: str, owner: str) -> None:
    try:
        if cache.get(lock_key(key)) == owner:          # our lock may have expired and been taken over meanwhile
            cache.delete(lock_key(key))
    except Exception as exc:    # the lock expires by itself
        _degraded('release', exc)


def cache_ttl(expires_in):
    """Seconds to keep a token, or None when it must not be cached (short-lived or an unreadable expires_in)."""
    try:
        ttl = int(expires_in) - EARLY_REFRESH_SECONDS
    except (TypeError, ValueError):
        return None
    return ttl if ttl > 0 else None


def _usable(token, stale):
    return token if token and token != stale else None


def cached_token(account_id: str, fetch, stale=None) -> str:
    """A bearer token for `account_id`. `fetch()` returns (token, expires_in) or raises. `stale` is a token Zoom just
    refused (401): it is never handed out again."""
    key = token_cache_key(account_id)
    try:
        token = _usable(cache.get(key), stale)
        if token:
            return token
        owner = acquire_lock(key)
    except Exception as exc:    # Redis down: fetch directly, cache nothing, lock nothing
        _degraded('lookup', exc)
        return fetch()[0]
    if owner is None:
        token = _wait_for_other_worker(key, stale)
        if token:
            return token
    try:
        return _fetch_and_store(key, fetch)
    finally:
        if owner is not None:
            release_lock(key, owner)


def _wait_for_other_worker(key, stale):
    polls = max(1, int(settings.ZOOM_TOKEN_WAIT_SECONDS / POLL_SECONDS))
    for _ in range(polls):
        _sleep(POLL_SECONDS)
        try:
            token = _usable(cache.get(key), stale)
        except Exception as exc:
            _degraded('wait', exc)
            return None
        if token:
            return token
    return None


def _fetch_and_store(key, fetch) -> str:
    token, expires_in = fetch()
    ttl = cache_ttl(expires_in)
    if ttl is not None:
        try:
            cache.set(key, token, ttl)
        except Exception as exc:    # the token is still good for this call
            _degraded('store', exc)
    return token


def invalidate_token(account_id: str, token: str) -> None:
    key = token_cache_key(account_id)
    try:
        if token and cache.get(key) == token:
            cache.delete(key)
    except Exception as exc:
        _degraded('invalidate', exc)
