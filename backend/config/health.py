"""Dependency readiness for the public /api/ready/ route.

Railway's internal liveness probe is served separately by ``config.wsgi`` so
a temporary database or broker outage does not restart an otherwise live API.
"""

import logging
import subprocess
import sys
import threading
import time

from django.conf import settings
from django.db import connection, connections
from redis import Redis


logger = logging.getLogger(__name__)
_lock = threading.Lock()
_last_checked = 0.0
_last_result = False
_CACHE_SECONDS = 60.0
_PROBE_DEADLINE_SECONDS = 9.0
_CHILD_DEADLINE_SECONDS = 6.0
_probe_thread = None
_probe_done = None
_probe_started = 0.0
_timeout_logged = False


def _probe_production_dependencies():
    # DB and Redis DNS resolution can stall before socket timeouts apply. A
    # child process lets subprocess.run terminate both connect/query paths on
    # timeout, so a later readiness poll can try again after recovery.
    completed = subprocess.run(
        [sys.executable, "-m", "config.probe_dependencies"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=_CHILD_DEADLINE_SECONDS,
        check=False,
    )
    return completed.returncode == 0


def _probe_dependencies():
    if connection.vendor == "postgresql":
        return _probe_production_dependencies()

    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        if cursor.fetchone() != (1,):
            return False

    redis_url = getattr(settings, "REDIS_URL", "")
    if redis_url:
        # Keep readiness bounded even if the broker is unreachable. The
        # production URL has already been TLS-normalized by its settings.
        client = Redis.from_url(redis_url, socket_connect_timeout=1, socket_timeout=1)
        try:
            if not client.ping():
                return False
        finally:
            client.close()
    return True


def _run_probe(done):
    global _last_checked, _last_result, _probe_thread, _timeout_logged
    try:
        result = _probe_dependencies()
    except Exception as exc:
        # Exception messages can contain DSNs or credentials; log only the
        # class name and keep the response deliberately generic.
        logger.warning("Readiness probe failed: %s", type(exc).__name__)
        result = False
    finally:
        # Django DB connections are thread-local. This bounded background
        # check must not leave an idle connection open on each poll.
        connections.close_all()
    with _lock:
        _last_result = result
        _last_checked = time.monotonic()
        _probe_thread = None
        _timeout_logged = False
        done.set()


def check_dependencies():
    """Return DB/broker readiness within a bounded HTTP request time.

    One probe per process may run at once. A stalled DB cannot hold request
    threads or create an unbounded number of probes: after the deadline,
    callers receive 503 until the existing daemon probe finishes. Successful
    and failed results are cached for one minute to limit Upstash traffic.
    """
    global _probe_thread, _probe_done, _probe_started, _timeout_logged
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
        with _lock:
            if not _timeout_logged:
                logger.warning("Readiness probe exceeded its deadline")
                _timeout_logged = True
        return False
    with _lock:
        return _last_result
