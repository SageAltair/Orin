"""Shared focus-task transitions and local day-boundary calculations."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from orin_api.models import FocusState, Task, TaskStatus


DAY_START_HOUR = 4


def local_day_key(instant: datetime, timezone_name: str, *, day_start_hour: int = DAY_START_HOUR) -> str:
    """Return the user's YYYY-MM-DD day, which rolls over at 04:00 local time."""
    # SQLite may return timezone-aware database columns as naive UTC datetimes.
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("timezone must be a valid IANA timezone") from exc
    if not 0 <= day_start_hour <= 23:
        raise ValueError("day_start_hour must be between 0 and 23")
    local = instant.astimezone(zone).replace(tzinfo=None)
    return (local - timedelta(hours=day_start_hour)).date().isoformat()


def touch_task(task: Task, *, now: datetime | None = None) -> None:
    instant = now or datetime.now(timezone.utc)
    task.last_touched_at = instant
    if task.decay_review_at is None:
        task.decay_review_at = instant + timedelta(days=30)


def keep_task_in_review(task: Task, *, now: datetime | None = None) -> None:
    instant = now or datetime.now(timezone.utc)
    task.last_touched_at = instant
    task.decay_review_at = instant + timedelta(days=30)


def shrink_task_step(task: Task, first_step: str, *, now: datetime | None = None) -> None:
    task.first_step = first_step
    keep_task_in_review(task, now=now)


def set_focus_state(task: Task, state: FocusState, *, now: datetime | None = None) -> None:
    """Move an open task between focus states without changing legacy status."""
    if task.status in {TaskStatus.DONE, TaskStatus.CANCELLED}:
        raise ValueError("Closed tasks cannot change focus state")
    task.focus_state = state
    touch_task(task, now=now)


def transition_task_status(task: Task, status: TaskStatus, *, now: datetime | None = None) -> None:
    """Apply a legacy status transition while keeping focus state consistent."""
    instant = now or datetime.now(timezone.utc)
    if status == TaskStatus.DONE:
        task.status = TaskStatus.DONE
        task.focus_state = None
        task.completed_at = instant
    elif status == TaskStatus.CANCELLED:
        release_task(task, now=instant)
        return
    elif task.status in {TaskStatus.DONE, TaskStatus.CANCELLED}:
        # Reopening a finished task always restores a safe Later state.
        task.status = TaskStatus.TODO
        task.focus_state = FocusState.LATER
        task.completed_at = None
        task.released_at = None
    else:
        task.status = status
        task.focus_state = FocusState.ACTIVE if status == TaskStatus.IN_PROGRESS else FocusState.LATER
        task.completed_at = None
    touch_task(task, now=instant)


def complete_task(task: Task, *, now: datetime | None = None) -> None:
    transition_task_status(task, TaskStatus.DONE, now=now)


def release_task(task: Task, *, now: datetime | None = None) -> None:
    instant = now or datetime.now(timezone.utc)
    task.status = TaskStatus.CANCELLED
    task.focus_state = FocusState.RELEASED
    task.released_at = instant
    task.completed_at = None
    touch_task(task, now=instant)


def reopen_task(task: Task, *, now: datetime | None = None) -> None:
    instant = now or datetime.now(timezone.utc)
    task.status = TaskStatus.TODO
    task.focus_state = FocusState.LATER
    task.completed_at = None
    task.released_at = None
    touch_task(task, now=instant)
