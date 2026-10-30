"""Explicitly opted-in, owner/workspace-scoped Windows task reminder companion.

This is a foreground process, not an installed service. It never stores credentials
or task titles and refuses to deliver without a fresh authenticated API poll.
Windows toast delivery and session lifecycle require real-device acceptance.
"""
from __future__ import annotations

import logging
import os
import signal
import sqlite3
import subprocess
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx

logger = logging.getLogger(__name__)
PAGE_SIZE = 100
LEAD_SECONDS = 30 * 60
MAX_AGE_SECONDS = 24 * 60 * 60
POLL_SECONDS = 60


def _due_epoch(raw: object) -> int:
    if not isinstance(raw, str):
        raise ValueError("Task due timestamp is missing")
    try:
        date = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Invalid task due timestamp") from error
    if date.tzinfo is None or date.utcoffset() is None:
        raise ValueError("Task due timestamp must include a timezone")
    return int(date.timestamp())


def _secure_api(url: str) -> bool:
    parsed = urlparse(url)
    return (bool(parsed.hostname) and not parsed.username and not parsed.password
        and not parsed.query and not parsed.fragment
        and (parsed.scheme == "https" or (
            parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        )))


def _uuid(value: str) -> str:
    return str(uuid.UUID(value))


class ReminderLedger:
    """Durable, minimal queue. A changed due timestamp re-arms the reminder."""

    def __init__(self, path: Path, owner_id: str, workspace_id: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.owner_id = _uuid(owner_id)
        self.workspace_id = _uuid(workspace_id)
        self.db = sqlite3.connect(path, timeout=5)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS reminders ("
            "owner_id TEXT NOT NULL, workspace_id TEXT NOT NULL, "
            "task_id TEXT NOT NULL, due_epoch INTEGER NOT NULL, "
            "attempted_epoch INTEGER, PRIMARY KEY(owner_id,workspace_id,task_id))"
        )
        # A reused local database must never expose a previous account's queue.
        with self.db:
            self.db.execute(
                "DELETE FROM reminders WHERE owner_id != ? OR workspace_id != ?",
                (self.owner_id, self.workspace_id),
            )
        # Connection-local staging avoids SQLite's bound-variable limit while
        # keeping snapshot replacement transactional. No task IDs are persisted
        # in a second on-disk table.
        self.db.execute(
            "CREATE TEMP TABLE IF NOT EXISTS reminder_snapshot_tasks "
            "(task_id TEXT PRIMARY KEY)"
        )

    def sync(self, tasks: dict[str, int]) -> None:
        """Replace the entire scoped snapshot atomically; never sync partial pages."""
        with self.db:
            self.db.execute("DELETE FROM reminder_snapshot_tasks")
            self.db.executemany(
                "INSERT INTO reminder_snapshot_tasks(task_id) VALUES (?)",
                ((task_id,) for task_id in tasks),
            )
            for task_id, due_epoch in tasks.items():
                self.db.execute(
                    "INSERT INTO reminders(owner_id,workspace_id,task_id,due_epoch) "
                    "VALUES(?,?,?,?) ON CONFLICT(owner_id,workspace_id,task_id) "
                    "DO UPDATE SET due_epoch=excluded.due_epoch, "
                    "attempted_epoch=CASE WHEN due_epoch=excluded.due_epoch "
                    "THEN attempted_epoch ELSE NULL END",
                    (self.owner_id, self.workspace_id, task_id, due_epoch),
                )
            self.db.execute(
                "DELETE FROM reminders WHERE owner_id=? AND workspace_id=? "
                "AND NOT EXISTS (SELECT 1 FROM reminder_snapshot_tasks "
                "WHERE reminder_snapshot_tasks.task_id=reminders.task_id)",
                (self.owner_id, self.workspace_id),
            )

    def due(self, now: int) -> list[tuple[str, int]]:
        return self.db.execute(
            "SELECT task_id,due_epoch FROM reminders "
            "WHERE owner_id=? AND workspace_id=? AND attempted_epoch IS NULL "
            "AND due_epoch-?<=? AND due_epoch>=? ORDER BY due_epoch,task_id",
            (self.owner_id, self.workspace_id, LEAD_SECONDS, now, now - MAX_AGE_SECONDS),
        ).fetchall()

    def mark_attempted(self, task_id: str, due_epoch: int, now: int) -> None:
        with self.db:
            self.db.execute(
                "UPDATE reminders SET attempted_epoch=? "
                "WHERE owner_id=? AND workspace_id=? AND task_id=? "
                "AND due_epoch=? AND attempted_epoch IS NULL",
                (now, self.owner_id, self.workspace_id, task_id, due_epoch),
            )

    def clear(self) -> None:
        with self.db:
            self.db.execute(
                "DELETE FROM reminders WHERE owner_id=? AND workspace_id=?",
                (self.owner_id, self.workspace_id),
            )

    def close(self) -> None:
        self.db.close()


def _quiet(prefs: dict[str, object], now: int) -> bool:
    if not prefs.get("quiet_enabled"):
        return False
    try:
        zone = ZoneInfo(str(prefs["timezone"]))
        start = str(prefs["quiet_start"])
        end = str(prefs["quiet_end"])
        current = datetime.fromtimestamp(now, timezone.utc).astimezone(zone).strftime("%H:%M")
        if start == end:
            # Match the server policy: equal bounds mean quiet all day.
            return True
        return start <= current < end if start < end else current >= start or current < end
    except (KeyError, ValueError) as error:
        raise ValueError("Invalid quiet-hours preferences") from error


def _focus_active(client: httpx.Client) -> bool:
    """Fail closed if the authenticated Focus state cannot be validated."""
    response = client.get("/focus/now")
    response.raise_for_status()
    state = response.json()
    if not isinstance(state, dict) or "focus_session" not in state:
        raise ValueError("Invalid Focus state")
    focus = state["focus_session"]
    if focus is None:
        return False
    if not isinstance(focus, dict) or focus.get("status") != "active":
        raise ValueError("Invalid active Focus session")
    return True


def _fetch_snapshot(client: httpx.Client, owner_id: str, workspace_id: str, now: int) -> tuple[dict[str, int], dict[str, object]]:
    identity = client.get("/auth/me")
    identity.raise_for_status()
    account = identity.json()
    if not isinstance(account, dict) or account.get("id") != owner_id:
        raise PermissionError("Authenticated owner differs from the configured owner")
    response = client.get("/notifications/preferences")
    response.raise_for_status()
    prefs = response.json()
    if not isinstance(prefs, dict):
        raise ValueError("Invalid notification preferences")
    if prefs.get("enabled") is not True or "tasks" not in prefs.get("categories", []):
        return {}, prefs

    tasks: dict[str, int] = {}
    seen: set[str] = set()
    for page in range(1000):
        response = client.get(
            "/tasks",
            params={"limit": PAGE_SIZE, "offset": page * PAGE_SIZE},
            headers={"X-Orin-Workspace-Id": workspace_id},
        )
        response.raise_for_status()
        items = response.json()
        if not isinstance(items, list) or len(items) > PAGE_SIZE:
            raise ValueError("Invalid tasks page")
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                raise ValueError("Invalid task record")
            if item.get("owner_id", owner_id) != owner_id or item.get("workspace_id", workspace_id) != workspace_id:
                raise PermissionError("Task belongs to another owner or workspace")
            if item.get("status") not in {"todo", "in_progress", "blocked", "done", "cancelled"}:
                raise ValueError("Invalid task status")
            if item["id"] in seen:
                raise ValueError("Overlapping task pages")
            seen.add(item["id"])
            if item.get("status") in {"done", "cancelled"} or item.get("due_at") is None:
                continue
            due = _due_epoch(item["due_at"])
            if due >= now - MAX_AGE_SECONDS:
                tasks[item["id"]] = due
        if len(items) < PAGE_SIZE:
            return tasks, prefs
    raise ValueError("Task pagination limit reached")


@contextmanager
def single_instance(path: Path):
    """Prevent duplicate companion processes and simultaneous duplicate alerts."""
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise RuntimeError("Another Windows reminder companion is already running") from error
        try:
            yield
        finally:
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _toast_environment() -> dict[str, str]:
    # Do not inherit the user's bearer token into the PowerShell toast process.
    allowed = {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATHEXT", "COMSPEC"}
    return {key: value for key, value in os.environ.items() if key.upper() in allowed}


def _windows_toast() -> None:
    """Generic content only; no task titles, credentials, or user data cross the OS boundary."""
    if os.name != "nt":
        raise RuntimeError("Windows toast delivery requires Windows")
    script = (
        "$ErrorActionPreference='Stop';"
        "[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime]|Out-Null;"
        "[Windows.Data.Xml.Dom.XmlDocument,Windows.Data.Xml.Dom.XmlDocument,ContentType=WindowsRuntime]|Out-Null;"
        "$xml=New-Object Windows.Data.Xml.Dom.XmlDocument;"
        "$xml.LoadXml('<toast><visual><binding template=\"ToastGeneric\"><text>Orin</text>"
        "<text>You have a scheduled task.</text></binding></visual></toast>');"
        "$toast=[Windows.UI.Notifications.ToastNotification]::new($xml);"
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Orin').Show($toast)"
    )
    subprocess.run(
        ("powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script),
        check=True, capture_output=True, timeout=15, env=_toast_environment(),
    )


def run_once(client: httpx.Client, ledger: ReminderLedger, *, now: int, notify=_windows_toast) -> int:
    """No stale/offline alerts: fetch and validate all pages before any delivery."""
    try:
        tasks, prefs = _fetch_snapshot(client, ledger.owner_id, ledger.workspace_id, now)
    except httpx.HTTPStatusError as error:
        if error.response.status_code in {401, 403}:
            ledger.clear()
        raise
    except PermissionError:
        ledger.clear()
        raise
    ledger.sync(tasks)
    if _quiet(prefs, now):
        return 0
    due_tasks = ledger.due(now)
    if due_tasks:
        if prefs.get("respect_focus") is True:
            try:
                if _focus_active(client):
                    return 0
            except httpx.HTTPStatusError as error:
                if error.response.status_code in {401, 403}:
                    ledger.clear()
                raise
        # One generic toast per poll avoids flooding the user with N alerts.
        notify()
        for task_id, due in due_tasks:
            ledger.mark_attempted(task_id, due, now)
    return len(due_tasks)


def main() -> None:
    if os.name != "nt":
        raise SystemExit("Windows reminders require Windows")
    if os.getenv("ORIN_WINDOWS_REMINDERS_ENABLED") != "1":
        raise SystemExit("Windows reminders are disabled; explicit opt-in is required")
    url = os.getenv("ORIN_WINDOWS_REMINDERS_API_URL", "").rstrip("/")
    token = os.getenv("ORIN_WINDOWS_REMINDERS_TOKEN", "")
    owner = os.getenv("ORIN_WINDOWS_REMINDERS_OWNER_ID", "")
    workspace = os.getenv("ORIN_WINDOWS_REMINDERS_WORKSPACE_ID", "")
    if not _secure_api(url) or not token or not owner or not workspace:
        raise SystemExit("Secure API URL, token, owner and workspace are required")
    try:
        owner, workspace = _uuid(owner), _uuid(workspace)
    except ValueError as error:
        raise SystemExit("Owner and workspace must be UUIDs") from error
    path = Path(os.getenv("ORIN_WINDOWS_REMINDERS_DB", str(Path.home() / ".orin" / "windows-reminders.sqlite3")))
    with single_instance(path):
        ledger = ReminderLedger(path, owner, workspace)
        stopping = threading.Event()
        signal.signal(signal.SIGINT, lambda *_: stopping.set())
        signal.signal(signal.SIGTERM, lambda *_: stopping.set())
        logging.basicConfig(level=logging.INFO)
        try:
            with httpx.Client(
                base_url=url + "/api/v1", headers={"Authorization": "Bearer " + token},
                timeout=httpx.Timeout(15, connect=5), follow_redirects=False,
                trust_env=urlparse(url).hostname not in {"localhost", "127.0.0.1", "::1"},
            ) as client:
                while not stopping.is_set():
                    try:
                        run_once(client, ledger, now=int(time.time()))
                    except httpx.HTTPStatusError as error:
                        if error.response.status_code in {401, 403}:
                            logger.error("Reminder authorization revoked; stopping companion")
                            break
                        logger.warning("Reminder API unavailable; no toast attempted")
                    except PermissionError:
                        logger.error("Reminder account verification failed; stopping companion")
                        break
                    except (httpx.HTTPError, ValueError, sqlite3.Error, subprocess.SubprocessError, RuntimeError):
                        logger.warning("Reminder sync or toast failed; no delivery is confirmed")
                    stopping.wait(POLL_SECONDS)
        finally:
            ledger.close()


if __name__ == "__main__":
    main()
