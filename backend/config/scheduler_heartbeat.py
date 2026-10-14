"""Bounded Beat-to-worker freshness check, separate from API liveness."""

import logging
import subprocess
import sys
import threading
import time

from django.conf import settings
from redis import Redis

from config.redis import normalize_redis_url


logger = logging.getLogger(__name__)
KEY = "scheduler:worker-heartbeat:v1"
_TTL_SECONDS = 180
_FRESH_SECONDS = 150
_CACHE_SECONDS = 30
_CHILD_DEADLINE_SECONDS = 4
_PROBE_DEADLINE_SECONDS = 5
_lock = threading.Lock()
_last_checked = 0.0
_last_result = False
_probe_thread = None
_probe_done = None
_probe_started = 0.0


def check_redis(action):
    """Perform one heartbeat command in the short-lived child process."""
    redis_url = getattr(settings, "REDIS_URL", "")
    if not redis_url:
        return False
    client = Redis.from_url(
        normalize_redis_url(redis_url), socket_connect_timeout=1, socket_timeout=1
    )
    try:
        if action == "write":
            return bool(client.set(KEY, str(int(time.time())), ex=_TTL_SECONDS))
        if action == "read":
            value = client.get(KEY)
            if value is None:
                return False
            try:
                age = time.time() - int(value)
            except (ValueError, TypeError, OverflowError):
                return False
            return -10 <= age <= _FRESH_SECONDS
        return False
    finally:
        client.close()


def run_child(action):
    """Bound DNS, TLS and socket stalls even when socket timeouts cannot."""
    if action not in {"read", "write"}:
        return False
    try:
        completed = subprocess.run(  # noqa: S603 - fixed module and validated action, no shell
            [sys.executable, "-m", "config.scheduler_heartbeat", action],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=_CHILD_DEADLINE_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("Scheduler heartbeat child failed: %s", type(exc).__name__)
        return False
    return completed.returncode == 0


def _run_probe(done):
    global _last_checked, _last_result, _probe_thread
    try:
        result = run_child("read")
    except Exception as exc:
        logger.warning("Scheduler freshness probe failed: %s", type(exc).__name__)
        result = False
    with _lock:
        _last_result = result
        _last_checked = time.monotonic()
        _probe_thread = None
        done.set()


def is_fresh():
    """Share one short cached read per API process; fail closed on a stall."""
    global _probe_thread, _probe_done, _probe_started
    with _lock:
        if _probe_thread is None:
            if time.monotonic() - _last_checked < _CACHE_SECONDS:
                return _last_result
            _probe_done = threading.Event()
            _probe_started = time.monotonic()
            _probe_thread = threading.Thread(target=_run_probe, args=(_probe_done,), daemon=True)
            _probe_thread.start()
        done = _probe_done
        remaining = _PROBE_DEADLINE_SECONDS - (time.monotonic() - _probe_started)
    if remaining <= 0 or not done.wait(remaining):
        return False
    with _lock:
        return _last_result


if __name__ == "__main__":
    try:
        ok = len(sys.argv) == 2 and check_redis(sys.argv[1])
    except Exception:
        # No credentials, exception text, or network target may reach stdout.
        ok = False
    sys.exit(0 if ok else 1)
