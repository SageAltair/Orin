"""Isolated tests for opt-in Windows reminder scheduling. No OS alerts or live API."""
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from orin_worker.windows_reminders import (
    ReminderLedger, _due_epoch, _quiet, _secure_api, _toast_environment, run_once,
)

OWNER = "16e447d8-27f9-4b0d-82be-3f0dbf2d899b"
WORKSPACE = "65e77714-26ba-420b-99a4-54093a5ad36b"
NOW = int(datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc).timestamp())


def task(id: str, due: int | None, status: str = "todo") -> dict[str, object]:
    return {"id": id, "status": status, "due_at": (
        datetime.fromtimestamp(due, timezone.utc).isoformat() if due is not None else None
    )}


def api(tasks: list[dict[str, object]], *, enabled=True, categories=None, owner=OWNER,
        status=200, prefs_extra=None) -> httpx.Client:
    prefs = {"enabled": enabled, "categories": categories if categories is not None else ["tasks"],
             "quiet_enabled": False, "timezone": "UTC", "quiet_start": "22:00", "quiet_end": "07:00"}
    prefs.update(prefs_extra or {})

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth/me"):
            return httpx.Response(status if status != 200 else 200, json={"id": owner})
        if request.url.path.endswith("/notifications/preferences"):
            return httpx.Response(200, json=prefs)
        if request.url.path.endswith("/tasks"):
            assert request.headers["X-Orin-Workspace-Id"] == WORKSPACE
            assert request.headers["Authorization"] == "Bearer test-token"
            offset = int(request.url.params["offset"])
            limit = int(request.url.params["limit"])
            return httpx.Response(200, json=tasks[offset:offset + limit])
        return httpx.Response(404)
    return httpx.Client(base_url="http://localhost:8100/api/v1", headers={
        "Authorization": "Bearer test-token",
    }, transport=httpx.MockTransport(handler))


def ledger(tmp_path: Path) -> ReminderLedger:
    return ReminderLedger(tmp_path / "reminders.sqlite3", OWNER, WORKSPACE)


def test_due_timestamp_must_be_timezone_aware():
    assert _due_epoch("2026-10-29T12:00:00Z") == NOW
    with pytest.raises(ValueError, match="timezone"):
        _due_epoch("2026-10-29T12:00:00")
    with pytest.raises(ValueError, match="Invalid"):
        _due_epoch("not-a-date")


def test_api_must_be_tls_except_loopback():
    assert _secure_api("https://orin.example")
    assert _secure_api("http://127.0.0.1:8100")
    assert not _secure_api("http://orin.example")


def test_future_task_waits_until_lead_time_then_delivers_once(tmp_path):
    queue = ledger(tmp_path)
    alerts = []
    with api([task("a", NOW + 3600)]) as client:
        assert run_once(client, queue, now=NOW, notify=lambda: alerts.append("toast")) == 0
        assert run_once(client, queue, now=NOW + 1800, notify=lambda: alerts.append("toast")) == 1
        assert run_once(client, queue, now=NOW + 1801, notify=lambda: alerts.append("toast")) == 0
    assert alerts == ["toast"]
    queue.close()


def test_reschedule_rearms_and_completion_cancels(tmp_path):
    queue = ledger(tmp_path)
    alerts = []
    with api([task("a", NOW + 60)]) as client:
        assert run_once(client, queue, now=NOW, notify=lambda: alerts.append(1)) == 1
    with api([task("a", NOW + 7200)]) as client:
        assert run_once(client, queue, now=NOW, notify=lambda: alerts.append(1)) == 0
        assert run_once(client, queue, now=NOW + 5400, notify=lambda: alerts.append(1)) == 1
    with api([task("a", NOW + 7200, "done")]) as client:
        assert run_once(client, queue, now=NOW + 5500, notify=lambda: alerts.append(1)) == 0
    assert queue.due(NOW + 5500) == []
    assert alerts == [1, 1]
    queue.close()


def test_durable_queue_and_account_isolation(tmp_path):
    path = tmp_path / "state.sqlite3"
    first = ReminderLedger(path, OWNER, WORKSPACE)
    first.sync({"a": NOW + 60})
    first.mark_attempted("a", NOW + 60, NOW)
    first.close()
    same = ReminderLedger(path, OWNER, WORKSPACE)
    assert same.due(NOW) == []
    same.close()
    other = ReminderLedger(path, "98ab1b6f-1d12-47c0-8f5a-4f70c9329e9c", WORKSPACE)
    assert other.db.execute("SELECT count(*) FROM reminders").fetchone()[0] == 0
    other.close()


def test_disabled_preferences_clear_stale_alerts(tmp_path):
    queue = ledger(tmp_path)
    queue.sync({"a": NOW + 60})
    with api([task("a", NOW + 60)], enabled=False) as client:
        assert run_once(client, queue, now=NOW, notify=lambda: pytest.fail("no alerts")) == 0
    assert queue.due(NOW) == []
    queue.sync({"a": NOW + 60})
    with api([task("a", NOW + 60)], categories=["calendar"]) as client:
        assert run_once(client, queue, now=NOW, notify=lambda: pytest.fail("no alerts")) == 0
    assert queue.due(NOW) == []
    queue.close()


def test_unauthorized_and_wrong_owner_fail_closed(tmp_path):
    queue = ledger(tmp_path)
    queue.sync({"a": NOW + 60})
    with api([], status=401) as client:
        with pytest.raises(httpx.HTTPStatusError):
            run_once(client, queue, now=NOW, notify=lambda: pytest.fail("no alerts"))
    assert queue.due(NOW) == []
    queue.sync({"a": NOW + 60})
    with api([], owner="someone-else") as client:
        with pytest.raises(PermissionError):
            run_once(client, queue, now=NOW, notify=lambda: pytest.fail("no alerts"))
    assert queue.due(NOW) == []
    queue.close()


def test_network_failure_does_not_emit_stale_queue(tmp_path):
    queue = ledger(tmp_path)
    queue.sync({"a": NOW + 60})
    with httpx.Client(base_url="https://orin.invalid/api/v1", transport=httpx.MockTransport(
        lambda request: httpx.Response(503)
    )) as client:
        with pytest.raises(httpx.HTTPStatusError):
            run_once(client, queue, now=NOW, notify=lambda: pytest.fail("no alerts"))
    assert queue.due(NOW) == [("a", NOW + 60)]
    queue.close()


def test_pagination_reads_all_and_no_partial_snapshot(tmp_path):
    queue = ledger(tmp_path)
    records = [task(f"t-{i}", NOW + 60) for i in range(105)]
    with api(records) as client:
        alerts = []
        assert run_once(client, queue, now=NOW, notify=lambda: alerts.append(1)) == 105
        assert alerts == [1]
    assert queue.db.execute("SELECT count(*) FROM reminders").fetchone()[0] == 105
    queue.close()


def test_invalid_page_aborts_without_mutating_queue(tmp_path):
    queue = ledger(tmp_path)
    queue.sync({"previous": NOW + 60})
    records = [task(f"t-{i}", NOW + 60) for i in range(100)] + [task("bad", NOW + 60)]
    records[-1]["due_at"] = "2026-10-29T12:00"
    with api(records) as client:
        with pytest.raises(ValueError, match="timezone"):
            run_once(client, queue, now=NOW, notify=lambda: pytest.fail("no alerts"))
    assert queue.due(NOW) == [("previous", NOW + 60)]
    queue.close()


def test_quiet_hours_respect_local_timezone_and_midnight():
    prefs = {"quiet_enabled": True, "timezone": "Africa/Dar_es_Salaam",
             "quiet_start": "22:00", "quiet_end": "07:00"}
    assert _quiet(prefs, int(datetime(2026, 10, 29, 20, tzinfo=timezone.utc).timestamp()))
    assert not _quiet(prefs, NOW)


def test_quiet_hours_suppress_then_release_without_repeating(tmp_path):
    queue = ledger(tmp_path)
    prefs = {"quiet_enabled": True, "timezone": "UTC",
             "quiet_start": "11:00", "quiet_end": "12:30"}
    alerts = []
    with api([task("a", NOW + 60)], prefs_extra=prefs) as client:
        assert run_once(client, queue, now=NOW, notify=lambda: alerts.append(1)) == 0
        assert run_once(client, queue, now=NOW + 1801, notify=lambda: alerts.append(1)) == 1
        assert run_once(client, queue, now=NOW + 1802, notify=lambda: alerts.append(1)) == 0
    assert alerts == [1]
    queue.close()


def test_toast_failure_is_retryable(tmp_path):
    queue = ledger(tmp_path)
    with api([task("a", NOW + 60)]) as client:
        with pytest.raises(RuntimeError):
            run_once(client, queue, now=NOW, notify=lambda: (_ for _ in ()).throw(RuntimeError()))
        assert run_once(client, queue, now=NOW, notify=lambda: None) == 1
    queue.close()



def test_cancelled_task_and_duplicate_completed_pages_do_not_alert(tmp_path):
    queue = ledger(tmp_path)
    with api([task("cancelled", NOW + 60, "cancelled")]) as client:
        assert run_once(client, queue, now=NOW, notify=lambda: pytest.fail("no alerts")) == 0
    assert queue.due(NOW) == []
    queue.close()


def test_credentials_in_url_are_rejected():
    assert not _secure_api("https://token@orin.example")
    assert not _secure_api("https://orin.example?access_token=secret")


def test_missing_host_is_not_secure():
    assert not _secure_api("https://")


def test_toast_subprocess_never_inherits_api_token(monkeypatch):
    monkeypatch.setenv("ORIN_WINDOWS_REMINDERS_TOKEN", "private-bearer-value")
    monkeypatch.setenv("PATH", "safe-bin")
    assert _toast_environment()["PATH"] == "safe-bin"
    assert "private-bearer-value" not in _toast_environment().values()
    assert "ORIN_WINDOWS_REMINDERS_TOKEN" not in _toast_environment()


def test_overlapping_task_pages_abort_before_delivery(tmp_path):
    queue = ledger(tmp_path)
    queue.sync({"previous": NOW + 60})
    first = [task(f"t-{i}", NOW + 60) for i in range(100)]
    second = [task("t-99", NOW + 60)]
    def handler(request):
        if request.url.path.endswith("/auth/me"):
            return httpx.Response(200, json={"id": OWNER})
        if request.url.path.endswith("/notifications/preferences"):
            return httpx.Response(200, json={"enabled": True, "categories": ["tasks"]})
        return httpx.Response(200, json=first if request.url.params["offset"] == "0" else second)
    with httpx.Client(base_url="https://orin.example/api/v1", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="Overlapping"):
            run_once(client, queue, now=NOW, notify=lambda: pytest.fail("no alerts"))
    assert queue.due(NOW) == [("previous", NOW + 60)]
    queue.close()
