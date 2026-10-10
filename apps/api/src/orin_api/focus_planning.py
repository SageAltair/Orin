"""Deterministic, database-independent focus planning rules."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Sequence

from orin_api.models import EnergyLevel, FocusSession, Task, TaskStatus


def _touch_time(task: Task) -> datetime:
    value = task.last_touched_at or task.updated_at or task.created_at
    if value is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def task_rank(task: Task) -> tuple[int, datetime, int]:
    """Prefer tasks with context and momentum, then shorter estimates; stale work stays available."""
    context = int(bool(task.first_step)) + int(bool(task.why))
    estimated_minutes = task.estimated_minutes if task.estimated_minutes is not None else 25
    return context, _touch_time(task), -estimated_minutes


def select_todays_three(
    tasks: Sequence[Task],
    energy: EnergyLevel,
    *,
    excluded_ids: set[uuid.UUID] | None = None,
    routines: Sequence[str] = (),
) -> tuple[list[Task], uuid.UUID | None]:
    """Select up to three energy-matched open tasks and an eligible anchor."""
    excluded = excluded_ids or set()
    eligible = [
        task for task in tasks
        if task.id not in excluded
        and task.status not in {TaskStatus.DONE, TaskStatus.CANCELLED}
        and task.energy_level == energy
    ]
    routine_names = tuple(name.casefold() for name in routines)
    eligible.sort(key=lambda task: (int(bool(task.trigger and any(name in task.trigger.casefold() for name in routine_names))), *task_rank(task)), reverse=True)
    anchor_pool = eligible
    if energy == EnergyLevel.LOW:
        anchor_pool = [task for task in eligible if task.estimated_minutes is not None and task.estimated_minutes <= 15]
    anchor_id = anchor_pool[0].id if anchor_pool else None
    selected = eligible[:3]
    if anchor_id is not None:
        anchor = anchor_pool[0]
        selected = [anchor, *(task for task in selected if task.id != anchor_id)][:3]
    return selected, anchor_id


def select_now_task(active_session: FocusSession | None, assignments: Sequence[tuple[Task, bool, int]]) -> Task | None:
    """Apply the Now order: active session task, anchor, then position."""
    open_tasks = {task.id: task for task, _, _ in assignments if task.status not in {TaskStatus.DONE, TaskStatus.CANCELLED}}
    if active_session is not None and active_session.task_id in open_tasks:
        return open_tasks[active_session.task_id]
    anchors = sorted((entry for entry in assignments if entry[1] and entry[0].id in open_tasks), key=lambda item: item[2])
    if anchors:
        return anchors[0][0]
    next_items = sorted((entry for entry in assignments if entry[0].id in open_tasks), key=lambda item: item[2])
    return next_items[0][0] if next_items else None
