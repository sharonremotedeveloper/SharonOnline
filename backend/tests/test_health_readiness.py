from unittest.mock import MagicMock, Mock
import subprocess
import threading
import time

import pytest

from config import health
from config import probe_dependencies


@pytest.mark.django_db
def test_dependency_probe_checks_database_and_redis(monkeypatch, settings):
    settings.REDIS_URL = "rediss://example.invalid:6379/0"
    client = Mock()
    client.ping.return_value = True
    from_url = Mock(return_value=client)
    monkeypatch.setattr(health.Redis, "from_url", from_url)

    assert health._probe_dependencies() is True
    from_url.assert_called_once_with(
        settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1
    )
    client.ping.assert_called_once_with()
    client.close.assert_called_once_with()


def test_dependency_probe_is_cached_and_catches_failure(monkeypatch, caplog):
    calls = []

    def fail_once():
        calls.append(True)
        raise RuntimeError("secret-not-for-logs")

    monkeypatch.setattr(health, "_probe_dependencies", fail_once)
    monkeypatch.setattr(health, "_last_checked", 0.0)
    monkeypatch.setattr(health, "_probe_thread", None)

    assert health.check_dependencies() is False
    assert health.check_dependencies() is False
    assert len(calls) == 1
    assert "secret-not-for-logs" not in caplog.text


def test_stalled_probe_has_request_deadline_and_no_probe_stampede(monkeypatch):
    release = threading.Event()
    entered = threading.Event()
    calls = []

    def stalled_probe():
        calls.append(True)
        entered.set()
        release.wait(2)
        return True

    monkeypatch.setattr(health, "_probe_dependencies", stalled_probe)
    monkeypatch.setattr(health, "_last_checked", 0.0)
    monkeypatch.setattr(health, "_probe_thread", None)
    monkeypatch.setattr(health, "_PROBE_DEADLINE_SECONDS", 0.01)

    try:
        assert health.check_dependencies() is False
        assert entered.is_set()
        assert health.check_dependencies() is False
        assert len(calls) == 1
    finally:
        release.set()
        probe = health._probe_thread
        if probe is not None:
            probe.join(timeout=2)


def test_concurrent_calls_share_the_inflight_probe(monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    calls = []
    results = []

    def probe():
        calls.append(True)
        entered.set()
        release.wait(2)
        return True

    monkeypatch.setattr(health, "_probe_dependencies", probe)
    monkeypatch.setattr(health, "_last_checked", 0.0)
    monkeypatch.setattr(health, "_probe_thread", None)
    threads = [threading.Thread(target=lambda: results.append(health.check_dependencies())) for _ in range(2)]
    try:
        threads[0].start()
        assert entered.wait(1)
        threads[1].start()
        time.sleep(0.01)
    finally:
        release.set()
        for thread in threads:
            thread.join(timeout=2)
    assert results == [True, True]
    assert len(calls) == 1


def test_production_probe_uses_bounded_silent_child(monkeypatch):
    run = Mock(return_value=subprocess.CompletedProcess([], 0))
    monkeypatch.setattr(health.subprocess, "run", run)

    assert health._probe_production_dependencies() is True
    run.assert_called_once_with(
        [health.sys.executable, "-m", "config.probe_dependencies"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=health._CHILD_DEADLINE_SECONDS,
        check=False,
    )


def test_timed_out_child_allows_a_fresh_recovery_probe(monkeypatch):
    outcomes = [subprocess.TimeoutExpired("config.probe_dependencies", 6), subprocess.CompletedProcess([], 0)]

    def run(*args, **kwargs):
        result = outcomes.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(health.subprocess, "run", run)

    with pytest.raises(subprocess.TimeoutExpired):
        health._probe_production_dependencies()
    assert health._probe_production_dependencies() is True


def test_child_checks_database_and_redis_with_configured_tls(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://user:password@db.example/readiness?sslmode=verify-full&connect_timeout=5",
    )
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings.production")
    monkeypatch.setenv("REDIS_URL", "rediss://default:secret@redis.example:6379/0")
    cursor = MagicMock()
    cursor.fetchone.return_value = (1,)
    cursor.__enter__.return_value = cursor
    conn = Mock()
    conn.cursor.return_value = cursor
    connect = Mock(return_value=conn)
    monkeypatch.setattr(probe_dependencies.psycopg2, "connect", connect)
    redis_client = Mock()
    redis_client.ping.return_value = True
    redis_connect = Mock(return_value=redis_client)
    monkeypatch.setattr(probe_dependencies.Redis, "from_url", redis_connect)

    assert probe_dependencies.main() == 0
    connect.assert_called_once_with(
        dbname="readiness", user="user", password="password", host="db.example",
        connect_timeout=2,
        sslmode="verify-full",
    )
    cursor.execute.assert_called_once_with("SELECT 1")
    conn.close.assert_called_once_with()
    redis_connect.assert_called_once_with(
        "rediss://default:secret@redis.example:6379/0?ssl_cert_reqs=required",
        socket_connect_timeout=1,
        socket_timeout=1,
    )
    redis_client.ping.assert_called_once_with()
    redis_client.close.assert_called_once_with()


def test_local_postgres_child_does_not_require_tls_unless_configured(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:password@localhost/readiness")
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings.local")
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value.fetchone.return_value = (1,)
    connect = Mock(return_value=conn)
    monkeypatch.setattr(probe_dependencies.psycopg2, "connect", connect)
    monkeypatch.delenv("REDIS_URL", raising=False)

    assert probe_dependencies.main() == 0
    assert "sslmode" not in connect.call_args.kwargs
