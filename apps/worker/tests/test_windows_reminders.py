"""Isolated tests for opt-in Windows reminder scheduling. No OS alerts or live API."""
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import os
import subprocess

import orin_worker.windows_reminders as windows_reminders

import httpx
import pytest

from orin_worker.windows_reminders import (
    ReminderLedger, _due_epoch, _quiet, _secure_api, _toast_environment,
    _toast_identity, _toast_script, _shortcut_identity_script,
    check_toast_registration, single_instance, run_once,
)

OWNER = "16e447d8-27f9-4b0d-82be-3f0dbf2d899b"
WORKSPACE = "65e77714-26ba-420b-99a4-54093a5ad36b"
NOW = int(datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc).timestamp())


def task(id: str, due: int | None, status: str = "todo") -> dict[str, object]:
    return {"id": id, "status": status, "due_at": (
        datetime.fromtimestamp(due, timezone.utc).isoformat() if due is not None else None
    )}


def api(tasks: list[dict[str, object]], *, enabled=True, categories=None, owner=OWNER,
        status=200, prefs_extra=None, focus_session=None, focus_status=200,
        focus_payload=None) -> httpx.Client:
    prefs = {"enabled": enabled, "categories": categories if categories is not None else ["tasks"],
             "quiet_enabled": False, "timezone": "UTC", "quiet_start": "22:00", "quiet_end": "07:00",
             "respect_focus": True}
    prefs.update(prefs_extra or {})

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth/me"):
            return httpx.Response(status if status != 200 else 200, json={"id": owner})
        if request.url.path.endswith("/notifications/preferences"):
            return httpx.Response(200, json=prefs)
        if request.url.path.endswith("/focus-sessions/active"):
            payload = focus_payload if focus_payload is not None else {"active": bool(focus_session and focus_session.get("status") == "active")}
            return httpx.Response(focus_status, json=payload)
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


def test_workspace_switch_preserves_attempted_reminders_and_scoped_clearing(tmp_path):
    """A -> B -> A must not re-arm unchanged tasks, even with identical IDs."""
    path = tmp_path / "reminders.sqlite3"
    other_workspace = "49b9a7e6-58c8-4b64-9d5c-fdd1e9c43ec8"

    first = ReminderLedger(path, OWNER, WORKSPACE)
    first.sync({"shared-task-id": NOW + 60})
    first.mark_attempted("shared-task-id", NOW + 60, NOW)
    assert first.due(NOW) == []
    first.close()

    second = ReminderLedger(path, OWNER, other_workspace)
    assert second.due(NOW) == []  # Cannot read the first workspace's queue.
    second.sync({"shared-task-id": NOW + 60})
    assert second.due(NOW) == [("shared-task-id", NOW + 60)]
    second.mark_attempted("shared-task-id", NOW + 60, NOW)
    second.close()

    reopened = ReminderLedger(path, OWNER, WORKSPACE)
    assert reopened.due(NOW) == []  # First workspace's attempt survives.
    reopened.sync({"shared-task-id": NOW + 60})
    assert reopened.due(NOW) == []  # Unchanged snapshot does not re-arm.
    reopened.sync({"shared-task-id": NOW + 120})
    assert reopened.due(NOW) == [("shared-task-id", NOW + 120)]
    reopened.clear()  # Revoking/clearing A cannot erase B's attempt.
    reopened.close()

    second_again = ReminderLedger(path, OWNER, other_workspace)
    assert second_again.due(NOW) == []
    assert second_again.db.execute(
        "SELECT COUNT(*) FROM reminders WHERE owner_id=?", (OWNER,)
    ).fetchone() == (1,)
    second_again.close()


def test_switching_accounts_discards_other_owners_reminder_records(tmp_path):
    path = tmp_path / "reminders.sqlite3"
    other_owner = "86223e18-43e7-40ab-a3e0-36b7f9cdd5c4"
    first = ReminderLedger(path, OWNER, WORKSPACE)
    first.sync({"private-task": NOW + 60})
    first.close()

    other = ReminderLedger(path, other_owner, WORKSPACE)
    assert other.db.execute(
        "SELECT COUNT(*) FROM reminders WHERE owner_id=?", (OWNER,)
    ).fetchone() == (0,)
    other.sync({"other-account-task": NOW + 60})
    other.close()

    first_again = ReminderLedger(path, OWNER, WORKSPACE)
    assert first_again.due(NOW) == []
    assert first_again.db.execute(
        "SELECT COUNT(*) FROM reminders"
    ).fetchone() == (0,)
    first_again.close()


def test_due_timestamp_must_be_timezone_aware():
    assert _due_epoch("2026-10-29T12:00:00Z") == NOW
    with pytest.raises(ValueError, match="timezone"):
        _due_epoch("2026-10-29T12:00:00")
    with pytest.raises(ValueError, match="Invalid"):
        _due_epoch("not-a-date")


@pytest.mark.parametrize("raw", [
    "2026-02-31T12:00:00Z",
    "2025-02-29T12:00:00Z",
    "2026-04-31T12:00:00Z",
    "2026-10-29T12:00:00+15:00",
    "2026-10-29T12:00:00-14:30",
    "2026-10-29T12:00:00+23:59",
    "2026-10-29T12:00:00+00:00:30",
    "2026-10-29 12:00:00Z",
    "2026-10-29T12:00:00.1234567890Z",
    "0001-01-01T00:00:00Z",
])
def test_due_timestamp_rejects_impossible_dates_and_offsets(raw):
    with pytest.raises(ValueError, match="Invalid"):
        _due_epoch(raw)


def test_due_timestamp_accepts_leap_day_precision_and_legal_offsets():
    assert _due_epoch("2024-02-29T12:34:56.123456789+03:00") == int(
        datetime(2024, 2, 29, 9, 34, 56, tzinfo=timezone.utc).timestamp()
    )
    assert _due_epoch("2024-02-29T12:00+14:00") == int(
        datetime(2024, 2, 28, 22, 0, tzinfo=timezone.utc).timestamp()
    )
    assert _due_epoch("2024-02-29T12:00-14:00") == int(
        datetime(2024, 3, 1, 2, 0, tzinfo=timezone.utc).timestamp()
    )


@pytest.mark.parametrize("bad_due", [
    "2026-10-29T12:00:00+15:00",
    "2026-02-31T12:00:00Z",
])
def test_invalid_due_snapshot_preserves_existing_queue_and_never_toasts(tmp_path, bad_due):
    queue = ledger(tmp_path)
    queue.sync({"previous": NOW + 60})
    invalid = task("bad", NOW + 60)
    invalid["due_at"] = bad_due
    with api([invalid]) as client:
        with pytest.raises(ValueError, match="Invalid"):
            run_once(client, queue, now=NOW, notify=lambda: pytest.fail("no toast"))
    assert queue.due(NOW) == [("previous", NOW + 60)]
    queue.close()


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


def test_active_standalone_focus_suppresses_alert_until_session_ends(tmp_path):
    queue = ledger(tmp_path)
    alerts = []
    # A session without a task is omitted by /focus/now but included in
    # /focus-sessions/active, matching the global respect_focus policy.
    with api([task("a", NOW + 60)], prefs_extra={"respect_focus": True},
             focus_session={"status": "active", "task_id": None}) as client:
        assert run_once(client, queue, now=NOW, notify=lambda: alerts.append("toast")) == 0
    assert len(queue.due(NOW)) == 1
    with api([task("a", NOW + 60)], prefs_extra={"respect_focus": True}) as client:
        assert run_once(client, queue, now=NOW + 1, notify=lambda: alerts.append("toast")) == 1
    assert alerts == ["toast"]
    queue.close()


def test_focus_api_failure_and_malformed_state_fail_closed(tmp_path):
    queue = ledger(tmp_path)
    with api([task("a", NOW + 60)], prefs_extra={"respect_focus": True},
             focus_status=503) as client:
        with pytest.raises(httpx.HTTPStatusError):
            run_once(client, queue, now=NOW, notify=lambda: pytest.fail("no toast"))
    assert len(queue.due(NOW)) == 1
    with api([task("a", NOW + 60)], prefs_extra={"respect_focus": True},
             focus_payload={"unexpected": True}) as client:
        with pytest.raises(ValueError, match="Invalid Focus"):
            run_once(client, queue, now=NOW, notify=lambda: pytest.fail("no toast"))
    assert len(queue.due(NOW)) == 1
    with api([task("a", NOW + 60)], prefs_extra={"respect_focus": True},
             focus_status=401) as client:
        with pytest.raises(httpx.HTTPStatusError):
            run_once(client, queue, now=NOW, notify=lambda: pytest.fail("no toast"))
    assert queue.due(NOW) == []
    queue.close()


def test_inactive_focus_does_not_block_reminder(tmp_path):
    queue = ledger(tmp_path)
    with api([task("a", NOW + 60)], prefs_extra={"respect_focus": True},
             focus_payload={"active": False}) as client:
        assert run_once(client, queue, now=NOW, notify=lambda: None) == 1
    queue.close()


@pytest.mark.parametrize("malformed", [{"active": "true"}, {"active": 1}, [{"status": "active"}]])
def test_malformed_focus_state_fails_closed_without_consuming_reminder(tmp_path, malformed):
    queue = ledger(tmp_path)
    with api([task("a", NOW + 60)], prefs_extra={"respect_focus": True},
             focus_payload=malformed) as client:
        with pytest.raises(ValueError, match="Invalid Focus active state"):
            run_once(client, queue, now=NOW, notify=lambda: pytest.fail("no toast"))
    assert queue.due(NOW) == [("a", NOW + 60)]
    queue.close()


def test_focus_suppression_is_opt_out(tmp_path):
    queue = ledger(tmp_path)
    with api([task("a", NOW + 60)], prefs_extra={"respect_focus": False},
             focus_status=503) as client:
        assert run_once(client, queue, now=NOW, notify=lambda: None) == 1
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


@pytest.mark.parametrize("override", [
    {"enabled": "true"},
    {"categories": "tasks"},
    {"categories": [1, "tasks"]},
    {"respect_focus": None},
    {"respect_focus": "false"},
    {"quiet_enabled": "false"},
    {"quiet_start": "99:00"},
    {"quiet_end": "12:99"},
    {"timezone": "Not/A_Timezone"},
])
def test_malformed_notification_policy_fails_closed_without_queue_mutation(tmp_path, override):
    queue = ledger(tmp_path)
    queue.sync({"previous": NOW + 60})
    with api([task("a", NOW + 60)], prefs_extra=override) as client:
        with pytest.raises(ValueError, match="Invalid notification"):
            run_once(client, queue, now=NOW, notify=lambda: pytest.fail("no toast"))
    assert queue.due(NOW) == [("previous", NOW + 60)]
    queue.close()


def test_disabled_policy_does_not_require_suppression_fields(tmp_path):
    queue = ledger(tmp_path)
    with api([task("a", NOW + 60)], enabled=False, prefs_extra={
        "respect_focus": None, "quiet_start": None, "categories": "malformed",
    }) as client:
        assert run_once(client, queue, now=NOW, notify=lambda: pytest.fail("no toast")) == 0
    assert queue.due(NOW) == []
    queue.close()


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


@pytest.mark.parametrize("change", [
    "disabled", "category_removed", "quiet_enabled", "focus_enabled", "malformed",
])
def test_live_policy_recheck_prevents_toast_after_mid_scan_change(tmp_path, change):
    queue = ledger(tmp_path)
    initial = {"enabled": True, "categories": ["tasks"], "quiet_enabled": False,
               "timezone": "UTC", "quiet_start": "11:00", "quiet_end": "13:00",
               "respect_focus": False}
    updated = dict(initial)
    if change == "disabled":
        updated["enabled"] = False
    elif change == "category_removed":
        updated["categories"] = ["calendar"]
    elif change == "quiet_enabled":
        updated["quiet_enabled"] = True
    elif change == "focus_enabled":
        updated["respect_focus"] = True
    else:
        updated["respect_focus"] = "yes"
    requests = {"preferences": 0, "focus": 0}
    alerts = []

    def handler(request):
        if request.url.path.endswith("/auth/me"):
            return httpx.Response(200, json={"id": OWNER})
        if request.url.path.endswith("/notifications/preferences"):
            requests["preferences"] += 1
            return httpx.Response(200, json=initial if requests["preferences"] == 1 else updated)
        if request.url.path.endswith("/tasks"):
            return httpx.Response(200, json=[task("a", NOW + 60)])
        if request.url.path.endswith("/focus-sessions/active"):
            requests["focus"] += 1
            return httpx.Response(200, json={"active": True})
        return httpx.Response(404)

    with httpx.Client(base_url="https://orin.example/api/v1",
                      transport=httpx.MockTransport(handler)) as client:
        if change == "malformed":
            with pytest.raises(ValueError, match="Invalid notification"):
                run_once(client, queue, now=NOW, notify=lambda: alerts.append("toast"))
        else:
            assert run_once(client, queue, now=NOW,
                            notify=lambda: alerts.append("toast")) == 0
    assert requests["preferences"] == 2
    assert requests["focus"] == (1 if change == "focus_enabled" else 0)
    assert alerts == []
    if change in {"disabled", "category_removed"}:
        assert queue.due(NOW) == []
    else:
        assert queue.due(NOW) == [("a", NOW + 60)]
    queue.close()


@pytest.mark.parametrize("change", ["disabled", "focus_started", "quiet_started"])
def test_final_task_scan_suppression_change_never_emits_stale_toast(tmp_path, change):
    """A policy or Focus change during the final task read must win over toast."""
    queue = ledger(tmp_path)
    state = {"enabled": True, "focus_active": False, "quiet_enabled": False}
    requests = {"tasks": 0, "preferences": 0, "focus": 0}
    alerts = []

    def handler(request):
        if request.url.path.endswith("/auth/me"):
            return httpx.Response(200, json={"id": OWNER})
        if request.url.path.endswith("/notifications/preferences"):
            requests["preferences"] += 1
            return httpx.Response(200, json={
                "enabled": state["enabled"], "categories": ["tasks"],
                "quiet_enabled": state["quiet_enabled"],
                "timezone": "UTC", "quiet_start": "11:00", "quiet_end": "13:00",
                "respect_focus": True,
            })
        if request.url.path.endswith("/tasks"):
            requests["tasks"] += 1
            if requests["tasks"] == 2:
                # The initial scan succeeded; policy changes before delivery.
                if change == "disabled":
                    state["enabled"] = False
                elif change == "focus_started":
                    state["focus_active"] = True
                else:
                    state["quiet_enabled"] = True
            return httpx.Response(200, json=[task("a", NOW + 60)])
        if request.url.path.endswith("/focus-sessions/active"):
            requests["focus"] += 1
            return httpx.Response(200, json={"active": state["focus_active"]})
        return httpx.Response(404)

    with httpx.Client(base_url="https://orin.example/api/v1",
                      transport=httpx.MockTransport(handler)) as client:
        assert run_once(client, queue, now=NOW,
                        notify=lambda: alerts.append("toast")) == 0
    assert requests["tasks"] == 2
    assert requests["preferences"] == 2
    assert requests["focus"] == (1 if change == "focus_started" else 0)
    assert alerts == []
    if change == "disabled":
        assert queue.due(NOW) == []
    else:
        assert queue.due(NOW) == [("a", NOW + 60)]
    queue.close()


@pytest.mark.parametrize("auth_change", ["revoked", "wrong_owner"])
def test_live_auth_recheck_clears_queue_after_mid_scan_session_change(tmp_path, auth_change):
    queue = ledger(tmp_path)
    queue.sync({"previous": NOW + 60})
    auth_calls = 0

    def handler(request):
        nonlocal auth_calls
        if request.url.path.endswith("/auth/me"):
            auth_calls += 1
            if auth_calls == 2 and auth_change == "revoked":
                return httpx.Response(401)
            owner = OWNER if auth_calls == 1 else "someone-else"
            return httpx.Response(200, json={"id": owner})
        if request.url.path.endswith("/notifications/preferences"):
            return httpx.Response(200, json={
                "enabled": True, "categories": ["tasks"], "quiet_enabled": False,
                "timezone": "UTC", "quiet_start": "22:00", "quiet_end": "07:00",
                "respect_focus": False,
            })
        if request.url.path.endswith("/tasks"):
            return httpx.Response(200, json=[task("a", NOW + 60)])
        return httpx.Response(404)

    with httpx.Client(base_url="https://orin.example/api/v1",
                      transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError if auth_change == "revoked" else PermissionError):
            run_once(client, queue, now=NOW, notify=lambda: pytest.fail("no toast"))
    assert auth_calls == 2
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


@pytest.mark.parametrize("change", ["delete_during_pages", "change_deadline_between_scans"])
def test_offset_shift_or_deadline_edit_does_not_replace_windows_reminders(tmp_path, change):
    queue = ledger(tmp_path)
    queue.sync({"previous": NOW + 60})
    original = [task(f"t-{i}", NOW + 60) for i in range(101)]
    changed = [dict(item) for item in original]
    if change == "delete_during_pages":
        # The first 100 rows were fetched, then an earlier row was deleted.
        # Page two is now empty, so no ID overlaps and a single pass silently
        # omits t-100. The confirming scan must reject the changed snapshot.
        changed.pop(0)
    else:
        changed[-1]["due_at"] = datetime.fromtimestamp(
            NOW + 3600, timezone.utc,
        ).isoformat()
    scans = 0

    def handler(request):
        nonlocal scans
        if request.url.path.endswith("/auth/me"):
            return httpx.Response(200, json={"id": OWNER})
        if request.url.path.endswith("/notifications/preferences"):
            return httpx.Response(200, json={
                "enabled": True, "categories": ["tasks"],
                "quiet_enabled": False, "respect_focus": True,
                "timezone": "UTC", "quiet_start": "22:00", "quiet_end": "07:00",
            })
        if request.url.path.endswith("/tasks"):
            assert request.headers["X-Orin-Workspace-Id"] == WORKSPACE
            offset = int(request.url.params["offset"])
            limit = int(request.url.params["limit"])
            if offset == 0:
                scans += 1
            if change == "delete_during_pages" and scans == 1 and offset > 0:
                records = changed
            else:
                records = original if scans == 1 else changed
            return httpx.Response(200, json=records[offset:offset + limit])
        return httpx.Response(404)

    with httpx.Client(
        base_url="https://orin.example/api/v1",
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(ValueError, match="changed during pagination"):
            run_once(client, queue, now=NOW, notify=lambda: pytest.fail("no toast"))
    assert scans == 2
    assert queue.due(NOW) == [("previous", NOW + 60)]
    queue.close()


def test_large_snapshot_is_safe_under_legacy_sqlite_variable_limit(tmp_path):
    queue = ledger(tmp_path)
    # Older SQLite builds permit only 999 bound variables per statement.
    # The prior NOT IN implementation failed with 1,000 or more task IDs.
    if hasattr(queue.db, "setlimit"):
        queue.db.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 999)
    initial = {f"task-{i}": NOW + 60 for i in range(1500)}
    queue.sync(initial)
    queue.mark_attempted("task-1200", NOW + 60, NOW)
    queue.mark_attempted("task-1400", NOW + 60, NOW)

    revised = {f"task-{i}": NOW + 60 for i in range(198, 1500)}
    revised["task-1400"] = NOW + 3600
    queue.sync(revised)

    assert queue.db.execute("SELECT COUNT(*) FROM reminders").fetchone()[0] == 1302
    assert queue.db.execute(
        "SELECT attempted_epoch FROM reminders WHERE task_id='task-1200'"
    ).fetchone() == (NOW,)
    assert queue.db.execute(
        "SELECT due_epoch,attempted_epoch FROM reminders WHERE task_id='task-1400'"
    ).fetchone() == (NOW + 3600, None)
    assert queue.db.execute(
        "SELECT COUNT(*) FROM reminders WHERE task_id='task-0'"
    ).fetchone()[0] == 0

    queue.sync({})
    assert queue.db.execute("SELECT COUNT(*) FROM reminders").fetchone()[0] == 0
    queue.close()


def test_failed_snapshot_update_rolls_back_staging_and_reminders(tmp_path):
    queue = ledger(tmp_path)
    queue.sync({"a": NOW + 60, "b": NOW + 120})
    queue.db.execute(
        "CREATE TEMP TRIGGER reject_due_change BEFORE UPDATE OF due_epoch "
        "ON reminders WHEN NEW.task_id='a' "
        "BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END"
    )
    with pytest.raises(sqlite3.DatabaseError, match="synthetic failure"):
        queue.sync({"a": NOW + 3600})
    assert queue.db.execute(
        "SELECT task_id,due_epoch FROM reminders ORDER BY task_id"
    ).fetchall() == [("a", NOW + 60), ("b", NOW + 120)]
    queue.db.execute("DROP TRIGGER reject_due_change")
    queue.sync({"a": NOW + 60})
    assert queue.db.execute(
        "SELECT task_id FROM reminders"
    ).fetchall() == [("a",)]
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


def test_equal_quiet_hour_bounds_mean_quiet_all_day(tmp_path):
    prefs = {"quiet_enabled": True, "timezone": "UTC",
             "quiet_start": "12:00", "quiet_end": "12:00"}
    assert _quiet(prefs, NOW)
    assert _quiet(prefs, NOW + 3600)
    queue = ledger(tmp_path)
    with api([task("a", NOW + 60)], prefs_extra=prefs) as client:
        assert run_once(client, queue, now=NOW, notify=lambda: pytest.fail("quiet all day")) == 0
    assert len(queue.due(NOW)) == 1
    queue.close()


def test_slow_scan_crossing_into_quiet_hours_does_not_toast(tmp_path):
    queue = ledger(tmp_path)
    alerts = []
    prefs = {"quiet_enabled": True, "timezone": "UTC",
             "quiet_start": "12:01", "quiet_end": "13:00",
             "respect_focus": False}
    with api([task("a", NOW + 60)], prefs_extra=prefs) as client:
        # The poll starts at 12:00, but the authenticated final task scan
        # finishes after 12:01. Using only poll-start time would alert in
        # the newly active quiet window.
        assert run_once(client, queue, now=NOW,
                        delivery_clock=lambda: NOW + 61,
                        notify=lambda: alerts.append("toast")) == 0
        assert queue.due(NOW) == [("a", NOW + 60)]
        # The original deadline remains retryable after quiet hours end.
        assert run_once(client, queue, now=NOW + 3601,
                        delivery_clock=lambda: NOW + 3601,
                        notify=lambda: alerts.append("toast")) == 1
    assert alerts == ["toast"]
    queue.close()


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
    monkeypatch.setenv("APPDATA", r"C:\Users\runner\AppData\Roaming")
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\runner\AppData\Local")
    monkeypatch.setenv("USERPROFILE", r"C:\Users\runner")
    monkeypatch.setenv("PSModuleAnalysisCachePath", r"C:\Users\runner\AppData\Local\ModuleAnalysisCache")
    assert _toast_environment()["PATH"] == "safe-bin"
    assert _toast_environment()["APPDATA"].endswith("Roaming")
    assert _toast_environment()["LOCALAPPDATA"].endswith("Local")
    assert _toast_environment()["USERPROFILE"].endswith("runner")
    assert {key.upper(): value for key, value in _toast_environment().items()}["PSMODULEANALYSISCACHEPATH"].endswith("ModuleAnalysisCache")
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
            return httpx.Response(200, json={"enabled": True, "categories": ["tasks"],
                                            "respect_focus": True, "quiet_enabled": False,
                                            "timezone": "UTC", "quiet_start": "22:00",
                                            "quiet_end": "07:00"})
        return httpx.Response(200, json=first if request.url.params["offset"] == "0" else second)
    with httpx.Client(base_url="https://orin.example/api/v1", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="Overlapping"):
            run_once(client, queue, now=NOW, notify=lambda: pytest.fail("no alerts"))
    assert queue.due(NOW) == [("previous", NOW + 60)]
    queue.close()


def test_only_one_companion_can_hold_a_queue_lock(tmp_path):
    path = tmp_path / "reminders.sqlite3"
    with single_instance(path):
        with pytest.raises(RuntimeError, match="already running"):
            with single_instance(path):
                pytest.fail("second instance must not start")
    with single_instance(path):
        pass


def test_cross_workspace_task_record_is_rejected(tmp_path):
    queue = ledger(tmp_path)
    queue.sync({"previous": NOW + 60})
    wrong = task("foreign", NOW + 60)
    wrong["workspace_id"] = "another-workspace"
    with api([wrong]) as client:
        with pytest.raises(PermissionError, match="workspace"):
            run_once(client, queue, now=NOW, notify=lambda: pytest.fail("no alerts"))
    assert queue.due(NOW) == []
    queue.close()


def test_invalid_task_status_aborts_without_notification(tmp_path):
    queue = ledger(tmp_path)
    record = task("bad", NOW + 60)
    record["status"] = "unknown"
    with api([record]) as client:
        with pytest.raises(ValueError, match="status"):
            run_once(client, queue, now=NOW, notify=lambda: pytest.fail("no alerts"))
    queue.close()


def test_windows_toast_identity_requires_start_menu_shortcut(tmp_path, monkeypatch):
    user_root = tmp_path / "user-profile"
    programs = user_root / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    programs.mkdir(parents=True)
    shortcut = programs / "Orin.lnk"
    shortcut.write_bytes(b"test-only shortcut placeholder")
    monkeypatch.setenv("APPDATA", str(user_root))
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "machine-profile"))
    monkeypatch.setenv("ORIN_WINDOWS_REMINDERS_APP_ID", "Orin.Desktop")
    monkeypatch.setenv("ORIN_WINDOWS_REMINDERS_SHORTCUT", str(shortcut))
    assert _toast_identity() == ("Orin.Desktop", shortcut.resolve())

    monkeypatch.setenv("ORIN_WINDOWS_REMINDERS_APP_ID", "Orin;Write-Host bad")
    with pytest.raises(RuntimeError, match="AppUserModelID"):
        _toast_identity()
    monkeypatch.setenv("ORIN_WINDOWS_REMINDERS_APP_ID", "Orin.Desktop")

    monkeypatch.setenv("ORIN_WINDOWS_REMINDERS_SHORTCUT", str(tmp_path / "outside.lnk"))
    (tmp_path / "outside.lnk").write_bytes(b"outside")
    with pytest.raises(RuntimeError, match="Start Menu Programs"):
        _toast_identity()

    monkeypatch.setenv("ORIN_WINDOWS_REMINDERS_SHORTCUT", str(programs / "missing.lnk"))
    with pytest.raises(RuntimeError, match="does not exist"):
        _toast_identity()


def test_windows_toast_script_checks_registered_identity_before_show(tmp_path):
    shortcut = tmp_path / "O'Brien.lnk"
    script = _toast_script("Orin.Desktop", shortcut)
    assert "O''Brien.lnk" in script
    assert "$registered -cne $appId" in script
    assert script.index("ExtendedProperty('System.AppUserModel.ID')") < script.index(".Show($toast)")
    assert "CreateToastNotifier($appId)" in script
    assert "Bearer" not in script



def test_windows_toast_refuses_unconfigured_identity_before_subprocess(monkeypatch):
    class WindowsOS:
        name = "nt"
        environ = os.environ
        getenv = staticmethod(os.getenv)

    monkeypatch.setattr(windows_reminders, "os", WindowsOS)
    monkeypatch.delenv("ORIN_WINDOWS_REMINDERS_APP_ID", raising=False)
    monkeypatch.setattr(windows_reminders.subprocess, "run",
                        lambda *args, **kwargs: pytest.fail("no subprocess without identity"))
    with pytest.raises(RuntimeError, match="AppUserModelID"):
        windows_reminders._windows_toast()


def test_windows_toast_subprocess_failure_does_not_consume_reminder(tmp_path):
    queue = ledger(tmp_path)
    with api([task("a", NOW + 60)]) as client:
        with pytest.raises(subprocess.CalledProcessError):
            run_once(client, queue, now=NOW, notify=lambda: (_ for _ in ()).throw(
                subprocess.CalledProcessError(1, "powershell.exe")))
        assert queue.due(NOW) == [("a", NOW + 60)]
        assert run_once(client, queue, now=NOW + 1, notify=lambda: None) == 1
    queue.close()


def test_toast_resolves_system_powershell_without_searching_path(tmp_path, monkeypatch):
    import ctypes
    from types import SimpleNamespace

    system = tmp_path / "System32"
    executable = system / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"test-only executable placeholder")
    (tmp_path / "powershell.exe").write_bytes(b"untrusted PATH candidate")
    monkeypatch.setenv("PATH", str(tmp_path))

    class Kernel32:
        @staticmethod
        def GetSystemDirectoryW(buffer, size):
            buffer.value = str(system)
            return len(buffer.value)

    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(kernel32=Kernel32()), raising=False)
    assert windows_reminders._powershell_executable() == str(executable)
    executable.unlink()
    with pytest.raises(RuntimeError, match="unavailable"):
        windows_reminders._powershell_executable()


def test_toast_invokes_pinned_powershell_without_exposing_token(tmp_path, monkeypatch):
    class WindowsOS:
        name = "nt"
        environ = os.environ
        getenv = staticmethod(os.getenv)

    monkeypatch.setattr(windows_reminders, "os", WindowsOS)
    monkeypatch.setattr(windows_reminders, "_toast_identity",
                        lambda: ("Orin.Desktop", tmp_path / "Orin.lnk"))
    monkeypatch.setattr(windows_reminders, "_powershell_executable",
                        lambda: r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
    monkeypatch.setenv("ORIN_WINDOWS_REMINDERS_TOKEN", "secret-bearer-token")
    calls = []
    monkeypatch.setattr(windows_reminders.subprocess, "run",
                        lambda args, **kwargs: calls.append((args, kwargs)))
    windows_reminders._windows_toast()
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[0].endswith(r"WindowsPowerShell\v1.0\powershell.exe")
    assert args[1:6] == ("-NoProfile", "-NonInteractive", "-InputFormat", "None", "-Command")
    assert "ORIN_WINDOWS_REMINDERS_TOKEN" not in kwargs["env"]
    assert "secret-bearer-token" not in str(args)
    assert kwargs["check"] is True
    assert kwargs["stdin"] == subprocess.DEVNULL
    assert kwargs["stdout"] == subprocess.DEVNULL
    assert kwargs["stderr"] == subprocess.DEVNULL
    assert "capture_output" not in kwargs


def test_registration_probe_script_never_displays_toast_or_runs_shortcut(tmp_path):
    script = _shortcut_identity_script("Orin.Desktop", tmp_path / "O'Brien.lnk")
    assert "O''Brien.lnk" in script
    assert "ExtendedProperty('System.AppUserModel.ID')" in script
    assert "$registered -cne $appId" in script
    assert ".Show(" not in script
    assert "Start-Process" not in script
    assert "ToastNotificationManager" not in script


def test_registration_diagnostic_uses_pinned_powershell_without_credentials(tmp_path, monkeypatch, capsys):
    class WindowsOS:
        name = "nt"
        environ = os.environ
        getenv = staticmethod(os.getenv)

    monkeypatch.setattr(windows_reminders, "os", WindowsOS)
    monkeypatch.setattr(windows_reminders, "_toast_identity",
                        lambda: ("Orin.Desktop", tmp_path / "Orin.lnk"))
    monkeypatch.setattr(windows_reminders, "_powershell_executable",
                        lambda: r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
    monkeypatch.setenv("ORIN_WINDOWS_REMINDERS_TOKEN", "private-bearer-value")
    calls = []
    monkeypatch.setattr(windows_reminders.subprocess, "run",
                        lambda args, **kwargs: calls.append((args, kwargs)))
    check_toast_registration()
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[0].endswith(r"WindowsPowerShell\v1.0\powershell.exe")
    assert args[1:6] == ("-NoProfile", "-NonInteractive", "-InputFormat", "None", "-Command")
    assert ".Show(" not in args[6]
    assert "ORIN_WINDOWS_REMINDERS_TOKEN" not in kwargs["env"]
    assert "private-bearer-value" not in str(args)
    assert kwargs["check"] is True
    assert kwargs["stdin"] == subprocess.DEVNULL
    assert kwargs["stdout"] == subprocess.DEVNULL
    assert kwargs["stderr"] == subprocess.DEVNULL
    assert "capture_output" not in kwargs
    assert "Visible delivery is still unverified" in capsys.readouterr().out


def test_registration_diagnostic_fails_closed_without_modifying_shortcut(tmp_path, monkeypatch):
    class WindowsOS:
        name = "nt"
        environ = os.environ
        getenv = staticmethod(os.getenv)

    monkeypatch.setattr(windows_reminders, "os", WindowsOS)
    monkeypatch.setattr(windows_reminders, "_toast_identity",
                        lambda: ("Orin.Desktop", tmp_path / "Orin.lnk"))
    monkeypatch.setattr(windows_reminders, "_powershell_executable",
                        lambda: r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
    monkeypatch.setattr(windows_reminders.subprocess, "run",
                        lambda *args, **kwargs: (_ for _ in ()).throw(
                            subprocess.CalledProcessError(1, "powershell.exe")))
    with pytest.raises(SystemExit, match=r"CalledProcessError.*no changes were made"):
        check_toast_registration()
    monkeypatch.setattr(windows_reminders, "_toast_identity",
                        lambda: (_ for _ in ()).throw(RuntimeError("missing shortcut")))
    monkeypatch.setattr(windows_reminders.subprocess, "run",
                        lambda *args, **kwargs: pytest.fail("no process without shortcut"))
    with pytest.raises(SystemExit, match=r"RuntimeError.*no changes were made"):
        check_toast_registration()


@pytest.mark.parametrize("change", ["completed", "cancelled", "rescheduled", "deleted"])
def test_late_task_state_change_cannot_emit_stale_windows_toast(tmp_path, change):
    """A task can change after the initial snapshot and live policy recheck."""
    queue = ledger(tmp_path)
    reads = 0
    alerts = []
    initial = task("a", NOW + 60)
    changed = dict(initial)
    if change in {"completed", "cancelled"}:
        changed["status"] = "done" if change == "completed" else "cancelled"
    elif change == "rescheduled":
        changed["due_at"] = task("a", NOW + 3600)["due_at"]

    def handler(request):
        nonlocal reads
        if request.url.path.endswith("/auth/me"):
            return httpx.Response(200, json={"id": OWNER})
        if request.url.path.endswith("/notifications/preferences"):
            return httpx.Response(200, json={
                "enabled": True, "categories": ["tasks"], "quiet_enabled": False,
                "respect_focus": False, "timezone": "UTC",
                "quiet_start": "22:00", "quiet_end": "07:00",
            })
        if request.url.path.endswith("/tasks"):
            assert request.headers["X-Orin-Workspace-Id"] == WORKSPACE
            reads += 1
            return httpx.Response(200, json=[initial] if reads == 1 else (
                [] if change == "deleted" else [changed]
            ))
        return httpx.Response(404)

    with httpx.Client(base_url="https://orin.example/api/v1",
                      transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="Tasks changed before reminder delivery"):
            run_once(client, queue, now=NOW, notify=lambda: alerts.append("toast"))
    assert reads == 2
    assert alerts == []
    assert queue.due(NOW) == [("a", NOW + 60)]
    queue.close()


def test_late_task_revalidation_failure_does_not_consume_reminder(tmp_path):
    queue = ledger(tmp_path)
    reads = 0

    def handler(request):
        nonlocal reads
        if request.url.path.endswith("/auth/me"):
            return httpx.Response(200, json={"id": OWNER})
        if request.url.path.endswith("/notifications/preferences"):
            return httpx.Response(200, json={
                "enabled": True, "categories": ["tasks"], "quiet_enabled": False,
                "respect_focus": False, "timezone": "UTC",
                "quiet_start": "22:00", "quiet_end": "07:00",
            })
        if request.url.path.endswith("/tasks"):
            reads += 1
            return httpx.Response(200, json=[task("a", NOW + 60)]) if reads == 1 else httpx.Response(503)
        return httpx.Response(404)

    with httpx.Client(base_url="https://orin.example/api/v1",
                      transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            run_once(client, queue, now=NOW, notify=lambda: pytest.fail("no stale toast"))
    assert reads == 2
    assert queue.due(NOW) == [("a", NOW + 60)]
    queue.close()


def test_late_task_revalidation_allows_unchanged_due_task(tmp_path):
    queue = ledger(tmp_path)
    reads = 0
    alerts = []
    initial = [task("a", NOW + 60), task("b", NOW + 3600)]
    changed = [initial[0], task("b", NOW + 3600, "done")]

    def handler(request):
        nonlocal reads
        if request.url.path.endswith("/auth/me"):
            return httpx.Response(200, json={"id": OWNER})
        if request.url.path.endswith("/notifications/preferences"):
            return httpx.Response(200, json={
                "enabled": True, "categories": ["tasks"], "quiet_enabled": False,
                "respect_focus": False, "timezone": "UTC",
                "quiet_start": "22:00", "quiet_end": "07:00",
            })
        if request.url.path.endswith("/tasks"):
            reads += 1
            return httpx.Response(200, json=initial if reads == 1 else changed)
        return httpx.Response(404)

    with httpx.Client(base_url="https://orin.example/api/v1",
                      transport=httpx.MockTransport(handler)) as client:
        assert run_once(client, queue, now=NOW, notify=lambda: alerts.append("toast")) == 1
    assert reads == 2
    assert alerts == ["toast"]
    assert queue.due(NOW) == []
    queue.close()
