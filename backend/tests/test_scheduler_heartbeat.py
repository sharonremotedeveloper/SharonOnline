"""Beat-to-worker freshness is separate from HTTP and dependency liveness."""

import subprocess
from unittest.mock import Mock

from django.urls import reverse

from config import scheduler_heartbeat
from config.celery_schedule import CELERY_BEAT_SCHEDULE, CELERY_TASK_ROUTES


TASK = "apps.notifications.tasks.scheduler_heartbeat_task"


def test_schedule_targets_a_consumed_queue_with_short_expiry():
    entry = CELERY_BEAT_SCHEDULE["scheduler-heartbeat-every-minute"]
    assert entry["task"] == TASK
    assert entry["schedule"] == 60.0
    assert entry["options"] == {"queue": "scheduler_beat", "expires": 50}
    assert CELERY_TASK_ROUTES[TASK] == {"queue": "scheduler_beat"}


def test_heartbeat_task_is_discovered_and_writes_only_after_execution(monkeypatch):
    from config.celery import app
    from apps.notifications.tasks import scheduler_heartbeat_task

    app.autodiscover_tasks(force=True)
    assert TASK in app.tasks
    assert app.tasks[TASK].ignore_result is True
    probe = Mock(return_value=True)
    monkeypatch.setattr(scheduler_heartbeat, "run_child", probe)
    assert scheduler_heartbeat_task() is True
    probe.assert_called_once_with("write")


def test_child_writes_ttl_and_enforces_freshness(monkeypatch, settings):
    settings.REDIS_URL = "rediss://default:secret@redis.example:6379/0"
    client = Mock()
    monkeypatch.setattr(scheduler_heartbeat.Redis, "from_url", Mock(return_value=client))
    monkeypatch.setattr(scheduler_heartbeat.time, "time", lambda: 1000.0)

    assert scheduler_heartbeat.check_redis("write") is True
    client.set.assert_called_once_with(scheduler_heartbeat.KEY, "1000", ex=180)
    scheduler_heartbeat.Redis.from_url.assert_called_with(
        "rediss://default:secret@redis.example:6379/0?ssl_cert_reqs=required",
        socket_connect_timeout=1,
        socket_timeout=1,
    )
    client.get.return_value = b"850"
    assert scheduler_heartbeat.check_redis("read") is True
    client.get.return_value = b"849"
    assert scheduler_heartbeat.check_redis("read") is False
    client.get.return_value = b"1011"
    assert scheduler_heartbeat.check_redis("read") is False
    client.get.return_value = b"garbage"
    assert scheduler_heartbeat.check_redis("read") is False
    client.close.assert_called()


def test_missing_redis_and_expired_key_fail_closed(monkeypatch, settings):
    settings.REDIS_URL = ""
    assert scheduler_heartbeat.check_redis("read") is False
    settings.REDIS_URL = "redis://localhost:6379/0"
    client = Mock()
    client.get.return_value = None
    monkeypatch.setattr(scheduler_heartbeat.Redis, "from_url", Mock(return_value=client))
    assert scheduler_heartbeat.check_redis("read") is False


def test_child_failure_is_bounded_and_silent(monkeypatch):
    def timeout(*args, **kwargs):
        assert kwargs["timeout"] <= 5
        assert kwargs["stdout"] == subprocess.DEVNULL
        assert kwargs["stderr"] == subprocess.DEVNULL
        raise subprocess.TimeoutExpired("heartbeat", 4)

    monkeypatch.setattr(scheduler_heartbeat.subprocess, "run", timeout)
    assert scheduler_heartbeat.run_child("read") is False


def test_scheduler_endpoint_is_safe_and_distinct(client, monkeypatch):
    probe = Mock(return_value=True)
    monkeypatch.setattr(scheduler_heartbeat, "run_child", probe)
    monkeypatch.setattr(scheduler_heartbeat, "_last_checked", 0.0)
    monkeypatch.setattr(scheduler_heartbeat, "_probe_thread", None)
    url = reverse("scheduler-readiness-check")
    assert url == "/api/scheduler-ready/"
    response = client.get(url)
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    assert response["Cache-Control"] == "no-store"
    assert client.head(url).status_code == 200
    assert client.post(url).status_code == 405
    assert probe.call_count == 1
    assert client.get("/api/health/").status_code == 200


def test_scheduler_endpoint_fails_closed_without_details(client, monkeypatch):
    monkeypatch.setattr(scheduler_heartbeat, "run_child", lambda action: False)
    monkeypatch.setattr(scheduler_heartbeat, "_last_checked", 0.0)
    monkeypatch.setattr(scheduler_heartbeat, "_probe_thread", None)
    response = client.get("/api/scheduler-ready/")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert response["Cache-Control"] == "no-store"


def test_cached_read_expires_after_thirty_seconds(monkeypatch):
    probe = Mock(side_effect=[True, False])
    clock = Mock(return_value=100.0)
    monkeypatch.setattr(scheduler_heartbeat, "run_child", probe)
    monkeypatch.setattr(scheduler_heartbeat.time, "monotonic", clock)
    monkeypatch.setattr(scheduler_heartbeat, "_last_checked", 0.0)
    monkeypatch.setattr(scheduler_heartbeat, "_probe_thread", None)

    assert scheduler_heartbeat.is_fresh() is True
    clock.return_value = 110.0
    assert scheduler_heartbeat.is_fresh() is True
    clock.return_value = 131.0
    assert scheduler_heartbeat.is_fresh() is False
    assert probe.call_count == 2


def test_scheduler_probe_does_not_stampede_on_stall(monkeypatch):
    import threading

    release = threading.Event()
    entered = threading.Event()
    calls = []

    def stalled(action):
        calls.append(action)
        entered.set()
        release.wait(2)
        return True

    monkeypatch.setattr(scheduler_heartbeat, "run_child", stalled)
    monkeypatch.setattr(scheduler_heartbeat, "_last_checked", 0.0)
    monkeypatch.setattr(scheduler_heartbeat, "_probe_thread", None)
    monkeypatch.setattr(scheduler_heartbeat, "_PROBE_DEADLINE_SECONDS", 0.01)
    try:
        assert scheduler_heartbeat.is_fresh() is False
        assert entered.is_set()
        assert scheduler_heartbeat.is_fresh() is False
        assert calls == ["read"]
    finally:
        release.set()
        thread = scheduler_heartbeat._probe_thread
        if thread is not None:
            thread.join(timeout=2)
