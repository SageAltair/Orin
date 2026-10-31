"""Explicitly opted-in, owner/workspace-scoped Windows task reminder companion.

This is a foreground process, not an installed service. It never stores credentials
or task titles and refuses to deliver without a fresh authenticated API poll.
Windows toast delivery and session lifecycle require real-device acceptance.
"""
from __future__ import annotations

import logging
import os
import re
import signal
import sqlite3
import subprocess
import threading
import time
import uuid
from collections.abc import Callable
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
# Match the Android reminder parser: explicit timezone, real calendar date,
# and a legal UTC offset. datetime.fromisoformat alone accepts +23:59 and
# nonstandard separators/offset seconds that could shift Windows alerts.
_AWARE_DUE_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}"
    r"(?::[0-9]{2}(?:\.[0-9]{1,9})?)?(?:Z|[+-][0-9]{2}:[0-9]{2})$"
)


def _due_epoch(raw: object) -> int:
    if not isinstance(raw, str):
        raise ValueError("Task due timestamp is missing")
    try:
        date = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Invalid task due timestamp") from error
    if date.tzinfo is None or date.utcoffset() is None:
        raise ValueError("Task due timestamp must include a timezone")
    if not _AWARE_DUE_RE.fullmatch(raw) or int(raw[:4]) < 1000:
        raise ValueError("Invalid task due timestamp format")
    if raw[-1] != "Z":
        offset = raw[-6:]
        hours, minutes = int(offset[1:3]), int(offset[4:6])
        if hours > 14 or minutes > 59 or (hours == 14 and minutes != 0):
            raise ValueError("Invalid task due timezone offset")
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
        # A reused local database must never retain a different account's queue.
        # Preserve other workspaces of this same owner: their attempted records
        # prevent an unchanged task from notifying twice after A -> B -> A.
        # sync(), due(), mark_attempted() and clear() are workspace-scoped.
        with self.db:
            self.db.execute(
                "DELETE FROM reminders WHERE owner_id != ?",
                (self.owner_id,),
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


def _validate_notification_policy(prefs: dict[str, object]) -> None:
    """Reject malformed policy rather than silently bypassing quiet/Focus rules."""
    if type(prefs.get("enabled")) is not bool:
        raise ValueError("Invalid notification enabled preference")
    # Explicit opt-out always clears the queue, even if other policy fields
    # are malformed. No toast is possible in the disabled state.
    if not prefs["enabled"]:
        return
    categories = prefs.get("categories")
    if not isinstance(categories, list) or any(type(item) is not str for item in categories):
        raise ValueError("Invalid notification categories")
    if "tasks" not in categories:
        return
    if type(prefs.get("quiet_enabled")) is not bool or type(prefs.get("respect_focus")) is not bool:
        raise ValueError("Invalid notification suppression preferences")
    zone = prefs.get("timezone")
    start = prefs.get("quiet_start")
    end = prefs.get("quiet_end")
    if not isinstance(zone, str) or not zone or not isinstance(start, str) or not isinstance(end, str):
        raise ValueError("Invalid notification quiet-hours preferences")
    if not all(re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value) for value in (start, end)):
        raise ValueError("Invalid notification quiet-hours time")
    try:
        ZoneInfo(zone)
    except (KeyError, ValueError) as error:
        raise ValueError("Invalid notification timezone") from error


def _focus_active(client: httpx.Client) -> bool:
    """Check all active Focus sessions, not just the latest 50 history rows.

    The authenticated API expires elapsed sessions and scopes the answer to
    the bearer-token owner. Missing or malformed state fails closed.
    """
    response = client.get("/focus-sessions/active")
    if response.status_code == 405:
        # Older local APIs lack the authoritative endpoint. The history API
        # returns at most 50 records; only a shorter list proves completeness.
        history = client.get("/focus-sessions")
        history.raise_for_status()
        rows = history.json()
        if not isinstance(rows, list) or len(rows) >= 50 or any(
            not isinstance(row, dict) or row.get("status") not in
            {"active", "paused", "completed", "cancelled", "expired"}
            for row in rows
        ):
            raise ValueError("Legacy Focus history cannot establish safe state")
        return any(row["status"] == "active" for row in rows)
    response.raise_for_status()
    state = response.json()
    if not isinstance(state, dict) or type(state.get("active")) is not bool:
        raise ValueError("Invalid Focus active state")
    return state["active"]

def _scan_task_pages(client: httpx.Client, owner_id: str, workspace_id: str, now: int) -> tuple[dict[str, int], dict[str, tuple[object, object]], int]:
    """Read every task page, including identities of completed tasks.

    Signatures let a second scan detect deletions or updates that shift offset
    pages without producing an overlapping ID. This is best-effort consistency,
    not a database snapshot or a guarantee against simultaneous identical edits.
    """
    tasks: dict[str, int] = {}
    signatures: dict[str, tuple[object, object]] = {}
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
            signatures[item["id"]] = (item["status"], item.get("due_at"))
            if item.get("status") in {"done", "cancelled"} or item.get("due_at") is None:
                continue
            due = _due_epoch(item["due_at"])
            if due >= now - MAX_AGE_SECONDS:
                tasks[item["id"]] = due
        if len(items) < PAGE_SIZE:
            return tasks, signatures, page + 1
    raise ValueError("Task pagination limit reached")

def _fetch_live_policy(client: httpx.Client, owner_id: str) -> dict[str, object]:
    """Authenticate and read current suppression settings, never cached policy."""
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
    _validate_notification_policy(prefs)
    return prefs


def _require_browser_session(client: httpx.Client, session_id: str) -> None:
    """Fail closed when the explicitly bound web session was revoked or expired.

    The companion may use a different access token. Checking /auth/me alone
    cannot detect logout of that independent browser session.
    """
    response = client.get("/auth/sessions")
    response.raise_for_status()
    try:
        sessions = response.json()
    except ValueError as error:
        raise PermissionError("Invalid browser session state") from error
    if not isinstance(sessions, list) or any(not isinstance(item, dict) for item in sessions):
        raise PermissionError("Invalid browser session state")
    matches = [item for item in sessions if item.get("id") == session_id]
    if (len(matches) != 1 or type(matches[0].get("active")) is not bool
            or not matches[0]["active"] or "revoked_at" not in matches[0]
            or matches[0]["revoked_at"] is not None):
        raise PermissionError("Bound browser session is inactive or invalid")


def _require_browser_lease(
    client: httpx.Client, session_id: str, workspace_id: str,
    generation_id: str, now: int,
) -> None:
    """Require an unexpired lease from the current browser workspace.

    A manually bound AuthSession alone is insufficient: it stays active when
    the browser changes workspaces without logging out.
    """
    response = client.get(f"/auth/reminder-lease/{session_id}")
    if response.status_code in {401, 403, 404, 409}:
        raise PermissionError("Browser reminder lease is no longer authorized")
    response.raise_for_status()
    try:
        lease = response.json()
    except ValueError as error:
        raise PermissionError("Invalid browser reminder lease") from error
    if (not isinstance(lease, dict) or
        lease.get("workspace_id") != workspace_id or
        lease.get("generation_id") != generation_id):
        raise PermissionError("Browser reminder lease changed")
    try:
        expiry = _due_epoch(lease.get("expires_at"))
    except (ValueError, OverflowError) as error:
        raise PermissionError("Invalid browser reminder lease expiry") from error
    if expiry <= now:
        raise PermissionError("Browser reminder lease expired")


def _check_bound_browser_lease(
    client: httpx.Client, ledger: ReminderLedger,
    session_id: str | None, generation_id: str | None, now: int,
) -> None:
    if session_id is None or generation_id is None:
        return
    try:
        _require_browser_lease(
            client, session_id, ledger.workspace_id, generation_id, now,
        )
    except (PermissionError, httpx.HTTPError, ValueError):
        # No stale workspace queue may survive a missing, revoked or
        # unreachable lease; the browser must renew before any new alert.
        ledger.clear()
        raise


def _check_bound_browser_session(client: httpx.Client, ledger: ReminderLedger,
                                 session_id: str | None) -> None:
    if session_id is None:
        return
    try:
        _require_browser_session(client, session_id)
    except PermissionError:
        ledger.clear()
        raise
    except httpx.HTTPStatusError as error:
        if error.response.status_code in {401, 403}:
            ledger.clear()
        raise


def _fetch_snapshot(client: httpx.Client, owner_id: str, workspace_id: str, now: int) -> tuple[dict[str, int], dict[str, object]]:
    prefs = _fetch_live_policy(client, owner_id)
    if not prefs["enabled"] or "tasks" not in prefs["categories"]:
        return {}, prefs

    tasks, signatures, pages = _scan_task_pages(client, owner_id, workspace_id, now)
    if pages > 1:
        # An offset shift can omit a task without repeating an ID. Confirm the
        # full identity/status/deadline set before replacing durable reminders.
        _, confirmed, _ = _scan_task_pages(client, owner_id, workspace_id, now)
        if signatures != confirmed:
            raise ValueError("Tasks changed during pagination; retry before scheduling")
    return tasks, prefs


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
    # Shell.Application COM shortcut lookup needs the interactive Windows profile.
    # Keep only OS/profile paths, never bearer tokens or arbitrary app settings.
    allowed = {
        "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATHEXT", "COMSPEC",
        "APPDATA", "LOCALAPPDATA", "USERPROFILE", "HOMEDRIVE", "HOMEPATH",
        "PROGRAMDATA", "PSMODULEANALYSISCACHEPATH",
    }
    return {key: value for key, value in os.environ.items() if key.upper() in allowed}


def _toast_identity() -> tuple[str, Path]:
    """Require an existing Start Menu shortcut with an explicit app identity.

    The shortcut's actual AppUserModelID is checked by the toast subprocess.
    This function only validates the configured path and identity syntax.
    """
    app_id = os.getenv("ORIN_WINDOWS_REMINDERS_APP_ID", "")
    raw_path = os.getenv("ORIN_WINDOWS_REMINDERS_SHORTCUT", "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,127}", app_id):
        raise RuntimeError("A valid Windows reminder AppUserModelID is required")
    if not raw_path or not Path(raw_path).is_absolute() or Path(raw_path).suffix.lower() != ".lnk":
        raise RuntimeError("An absolute Start Menu .lnk path is required")
    try:
        shortcut = Path(raw_path).resolve(strict=True)
    except OSError as error:
        raise RuntimeError("Windows reminder Start Menu shortcut does not exist") from error
    if not shortcut.is_file():
        raise RuntimeError("Windows reminder shortcut must be a file")
    roots = []
    for variable, suffix in (
        ("APPDATA", ("Microsoft", "Windows", "Start Menu", "Programs")),
        ("PROGRAMDATA", ("Microsoft", "Windows", "Start Menu", "Programs")),
    ):
        base = os.getenv(variable)
        if base:
            roots.append((Path(base) / Path(*suffix)).resolve())
    if not any(shortcut.is_relative_to(root) for root in roots):
        raise RuntimeError("Windows reminder shortcut must be inside a Start Menu Programs folder")
    return app_id, shortcut


def _ps_quote(value: str) -> str:
    """Quote a PowerShell single-quoted string without permitting code injection."""
    return "'" + value.replace("'", "''") + "'"


def _shortcut_identity_script(app_id: str, shortcut: Path) -> str:
    """Read-only AUMID probe shared by diagnostics and the toast transport."""
    return (
        "$ErrorActionPreference='Stop';"
        "$appId=" + _ps_quote(app_id) + ";"
        "$shortcutPath=" + _ps_quote(str(shortcut)) + ";"
        "$shell=New-Object -ComObject Shell.Application;"
        "$folder=$shell.Namespace((Split-Path -Parent $shortcutPath));"
        "if ($null -eq $folder) { throw 'Start Menu folder unavailable' };"
        "$item=$folder.ParseName((Split-Path -Leaf $shortcutPath));"
        "if ($null -eq $item) { throw 'Start Menu shortcut unavailable' };"
        "$registered=[string]$item.ExtendedProperty('System.AppUserModel.ID');"
        "if ($registered -cne $appId) { throw 'Start Menu AppUserModelID mismatch' };"
    )


def _toast_script(app_id: str, shortcut: Path, *, test_mode: bool = False) -> str:
    """Fail before Show unless the existing shortcut exposes the matching AUMID."""
    message = "This is a test notification." if test_mode else "You have a scheduled task."
    return (
        _shortcut_identity_script(app_id, shortcut) +
        "[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime]|Out-Null;"
        "[Windows.Data.Xml.Dom.XmlDocument,Windows.Data.Xml.Dom.XmlDocument,ContentType=WindowsRuntime]|Out-Null;"
        "$xml=New-Object Windows.Data.Xml.Dom.XmlDocument;"
        "$xml.LoadXml('<toast><visual><binding template=\"ToastGeneric\"><text>Orin</text>"
        f"<text>{message}</text></binding></visual></toast>');"
        "$toast=[Windows.UI.Notifications.ToastNotification]::new($xml);"
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show($toast)"
    )


def _powershell_executable() -> str:
    """Use the OS-reported system directory, never PATH, for the toast process."""
    import ctypes

    buffer = ctypes.create_unicode_buffer(32768)
    length = ctypes.windll.kernel32.GetSystemDirectoryW(buffer, len(buffer))
    if not length or length >= len(buffer):
        raise RuntimeError("Cannot resolve the Windows system directory")
    executable = Path(buffer.value) / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if not executable.is_file():
        raise RuntimeError("System Windows PowerShell executable is unavailable")
    return str(executable)


def _windows_toast(*, test_mode: bool = False) -> None:
    """Generic content only; fail closed unless the registered identity matches."""
    if os.name != "nt":
        raise RuntimeError("Windows toast delivery requires Windows")
    app_id, shortcut = _toast_identity()
    subprocess.run(
        (_powershell_executable(), "-NoProfile", "-NonInteractive", "-InputFormat", "None", "-Command",
         _toast_script(app_id, shortcut, test_mode=test_mode)),
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        timeout=15, env=_toast_environment(),
    )


def check_toast_registration() -> None:
    """Opt-in, read-only Windows shortcut diagnostic; never sends a toast.

    No API credentials or reminder queue are needed. A matching AUMID does not
    prove Windows will display a notification, which needs interactive testing.
    """
    if os.name != "nt":
        raise SystemExit("Windows toast registration diagnostics require Windows")
    try:
        app_id, shortcut = _toast_identity()
        subprocess.run(
            (_powershell_executable(), "-NoProfile", "-NonInteractive", "-InputFormat", "None", "-Command",
             _shortcut_identity_script(app_id, shortcut)),
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        timeout=15, env=_toast_environment(),
        )
    except (RuntimeError, OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise SystemExit(
            f"Orin toast registration check failed ({type(error).__name__}). "
            "Verify the existing Start Menu shortcut and matching AppUserModelID; "
            "no changes were made."
        ) from error
    print("Orin toast shortcut identity matches. Visible delivery is still unverified.")


def test_toast_delivery() -> None:
    """Manual, interactive one-shot toast probe; never run by the scheduler.

    An OS API success only confirms submission, not that Windows displayed it.
    This requires a second explicit opt-in and an existing registered shortcut.
    No API token, database or task state is needed.
    """
    if os.name != "nt":
        raise SystemExit("Windows toast testing requires Windows")
    if os.getenv("ORIN_WINDOWS_REMINDERS_TEST_TOAST") != "1":
        raise SystemExit(
            "Test toast is disabled. Set ORIN_WINDOWS_REMINDERS_TEST_TOAST=1 "
            "explicitly in an interactive Windows session."
        )
    try:
        _windows_toast(test_mode=True)
    except (RuntimeError, OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise SystemExit(
            f"Orin test toast request failed ({type(error).__name__}). "
            "No visible delivery was confirmed."
        ) from error
    print(
        "Orin test toast request submitted. Check the Windows banner and "
        "notification center yourself; API success does not prove visibility."
    )


def run_once(client: httpx.Client, ledger: ReminderLedger, *, now: int, notify=_windows_toast,
             delivery_clock: Callable[[], int] | None = None,
             browser_session_id: str | None = None,
             browser_lease_generation: str | None = None) -> int:
    """No stale/offline alerts: fetch and validate all pages before any delivery."""
    # A revoked browser lease must also block *reading* old-workspace tasks.
    # Check before the first task request, after the snapshot and before toast.
    if browser_lease_generation is not None:
        _check_bound_browser_lease(
            client, ledger, browser_session_id, browser_lease_generation, now,
        )
    try:
        tasks, prefs = _fetch_snapshot(client, ledger.owner_id, ledger.workspace_id, now)
    except httpx.HTTPStatusError as error:
        if error.response.status_code in {401, 403}:
            ledger.clear()
        raise
    except PermissionError:
        ledger.clear()
        raise
    # An independent companion credential must not continue delivering after
    # the explicitly selected browser session has logged out.
    _check_bound_browser_session(client, ledger, browser_session_id)
    _check_bound_browser_lease(client, ledger, browser_session_id, browser_lease_generation, now)
    ledger.sync(tasks)
    if _quiet(prefs, now):
        return 0
    due_tasks = ledger.due(now)
    if not due_tasks:
        return 0

    # The initial task snapshot can become stale while other requests run.
    # Confirm that every due task is still active at the same deadline
    # immediately before delivery. A failure leaves reminders retryable.
    # This is a best-effort final read, not a transactional server snapshot.
    try:
        current_tasks, _, _ = _scan_task_pages(
            client, ledger.owner_id, ledger.workspace_id, now,
        )
    except httpx.HTTPStatusError as error:
        if error.response.status_code in {401, 403}:
            ledger.clear()
        raise
    except PermissionError:
        ledger.clear()
        raise
    if any(current_tasks.get(task_id) != due for task_id, due in due_tasks):
        raise ValueError("Tasks changed before reminder delivery; retry next poll")

    # Revalidate the owner and suppression policy AFTER the final task scan,
    # immediately before delivery. A focus session, quiet-hours change, or
    # opt-out during that scan must suppress the pending toast.
    try:
        live_prefs = _fetch_live_policy(client, ledger.owner_id)
    except httpx.HTTPStatusError as error:
        if error.response.status_code in {401, 403}:
            ledger.clear()
        raise
    except PermissionError:
        ledger.clear()
        raise
    if not live_prefs["enabled"] or "tasks" not in live_prefs["categories"]:
        ledger.clear()
        return 0
    if _quiet(live_prefs, now):
        return 0
    if live_prefs["respect_focus"]:
        try:
            if _focus_active(client):
                return 0
        except httpx.HTTPStatusError as error:
            if error.response.status_code in {401, 403}:
                ledger.clear()
            raise
    # A long task scan can cross into quiet hours after the poll-start
    # timestamp. Re-evaluate the *current* local clock immediately before
    # delivery. Tests may inject a deterministic clock; production supplies
    # the live wall clock rather than trusting the original poll timestamp.
    delivery_now = delivery_clock() if delivery_clock is not None else now
    if _quiet(live_prefs, delivery_now):
        return 0

    # Logout can occur during the final task/policy scan. Revalidate the
    # browser session immediately before the native transport.
    _check_bound_browser_session(client, ledger, browser_session_id)
    _check_bound_browser_lease(client, ledger, browser_session_id, browser_lease_generation, delivery_now)

    # One generic toast per poll avoids flooding the user with N alerts.
    notify()
    for task_id, due in due_tasks:
        ledger.mark_attempted(task_id, due, delivery_now)
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
    browser_session = os.getenv("ORIN_WINDOWS_REMINDERS_BROWSER_SESSION_ID", "")
    browser_lease = os.getenv("ORIN_WINDOWS_REMINDERS_BROWSER_LEASE_GENERATION", "")
    if not _secure_api(url) or not token or not owner or not workspace:
        raise SystemExit("Secure API URL, token, owner and workspace are required")
    try:
        owner, workspace = _uuid(owner), _uuid(workspace)
        browser_session = _uuid(browser_session) if browser_session else None
        browser_lease = _uuid(browser_lease) if browser_lease else None
    except ValueError as error:
        raise SystemExit("Owner, workspace and optional browser session must be UUIDs") from error
    if not browser_session or not browser_lease:
        raise SystemExit("An active browser session and short-lived workspace lease are required")
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
                        run_once(client, ledger, now=int(time.time()),
                                 delivery_clock=lambda: int(time.time()),
                                 browser_session_id=browser_session,
                                 browser_lease_generation=browser_lease)
                    except httpx.HTTPStatusError as error:
                        if error.response.status_code in {401, 403}:
                            logger.error("Reminder authorization revoked; stopping companion")
                            break
                        logger.warning("Reminder API unavailable; no toast attempted")
                    except PermissionError:
                        logger.error("Reminder account verification failed; stopping companion")
                        break
                    except (httpx.HTTPError, ValueError, sqlite3.Error,
                            subprocess.SubprocessError, RuntimeError, OSError) as error:
                        # Windows process launch can raise OSError before a toast is submitted.
                        # Never log request headers, tokens, task titles, or exception strings.
                        logger.warning("Reminder sync or toast failed (%s); no delivery is confirmed", type(error).__name__)
                    stopping.wait(POLL_SECONDS)
        finally:
            ledger.close()


if __name__ == "__main__":
    main()
