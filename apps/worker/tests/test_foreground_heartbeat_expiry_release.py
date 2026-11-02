"""Fail-first foreground heartbeat privacy regressions. Disposable API/SQLite only."""
import httpx
import pytest
import orin_worker.windows_reminders as reminders

OWNER = "16e447d8-27f9-4b0d-82be-3f0dbf2d899b"
WORKSPACE = "65e77714-26ba-420b-99a4-54093a5ad36b"
NOW = 1793275200
GENERATION = "3c413eed-47a2-45c5-922f-57d60610f728"


def _client():
    return httpx.Client(
        base_url="http://127.0.0.1:8100/api/v1",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={})),
    )


def test_heartbeat_expiry_during_lease_check_blocks_private_snapshot(tmp_path, monkeypatch):
    queue = reminders.ReminderLedger(tmp_path / "lease-expiry.sqlite3", OWNER, WORKSPACE)
    browser = {"recent": True}

    def lease_check(*args, **kwargs):
        # A slow server lease check outlives the last authenticated browser pulse.
        browser["recent"] = False

    monkeypatch.setattr(reminders, "_check_bound_browser_lease", lease_check)
    monkeypatch.setattr(reminders, "_fetch_snapshot",
                        lambda *args, **kwargs: pytest.fail("private task snapshot after heartbeat expiry"))
    try:
        with _client() as client:
            assert reminders.run_once(
                client, queue, now=NOW, browser_lease_generation=GENERATION,
                delivery_permitted=lambda: browser["recent"],
                notify=lambda: pytest.fail("stale native notification"),
            ) == 0
    finally:
        queue.close()


def test_heartbeat_expiry_during_snapshot_blocks_followup_private_scan(tmp_path, monkeypatch):
    queue = reminders.ReminderLedger(tmp_path / "snapshot-expiry.sqlite3", OWNER, WORKSPACE)
    browser = {"recent": True}

    def snapshot(*args, **kwargs):
        # The tab closes while the first task snapshot is in flight.
        browser["recent"] = False
        return {"due": NOW + 60}, {"quiet_enabled": False}

    monkeypatch.setattr(reminders, "_check_bound_browser_lease", lambda *args: None)
    monkeypatch.setattr(reminders, "_fetch_snapshot", snapshot)
    monkeypatch.setattr(reminders, "_scan_task_pages",
                        lambda *args, **kwargs: pytest.fail("second private task scan after heartbeat expiry"))
    try:
        with _client() as client:
            assert reminders.run_once(
                client, queue, now=NOW, browser_lease_generation=GENERATION,
                delivery_permitted=lambda: browser["recent"],
                notify=lambda: pytest.fail("stale native notification"),
            ) == 0
    finally:
        queue.close()



def test_heartbeat_expiry_during_task_pagination_blocks_second_page(tmp_path):
    queue = reminders.ReminderLedger(tmp_path / "pagination-expiry.sqlite3", OWNER, WORKSPACE)
    browser = {"recent": True}
    task_page = [
        {"id": f"task-{index}", "owner_id": OWNER, "workspace_id": WORKSPACE,
         "status": "todo", "due_at": "2026-10-29T12:01:00Z"}
        for index in range(reminders.PAGE_SIZE)
    ]
    requested_offsets = []

    def handler(request):
        path = request.url.path
        if path.endswith("/auth/me"):
            return httpx.Response(200, json={"id": OWNER})
        if path.endswith("/notifications/preferences"):
            return httpx.Response(200, json={
                "enabled": True, "categories": ["tasks"], "quiet_enabled": False,
                "respect_focus": False, "timezone": "UTC", "quiet_start": "22:00", "quiet_end": "07:00",
            })
        if path.endswith("/tasks"):
            offset = int(request.url.params["offset"])
            requested_offsets.append(offset)
            if offset != 0:
                pytest.fail("private task page read after browser heartbeat expired")
            browser["recent"] = False
            return httpx.Response(200, json=task_page)
        return httpx.Response(404)

    try:
        with httpx.Client(base_url="http://127.0.0.1:8100/api/v1",
                          transport=httpx.MockTransport(handler)) as client:
            assert reminders.run_once(
                client, queue, now=NOW,
                delivery_permitted=lambda: browser["recent"],
                notify=lambda: pytest.fail("stale native notification"),
            ) == 0
        assert requested_offsets == [0]
    finally:
        queue.close()

