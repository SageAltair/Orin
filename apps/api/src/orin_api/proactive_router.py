"""Evidence-based planning and recovery signals for the signed-in user."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from orin_api.auth import get_current_user
from orin_api.database import get_session
from orin_api.models import CalendarEvent, Project, Task, TaskReturnPoint, TaskSchedule, TaskStatus, User, UserSettings


router = APIRouter(prefix="/api/v1/intelligence", tags=["personal intelligence"])


def _aware(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


@router.get("/briefing")
def proactive_briefing(user: User = Depends(get_current_user),
                       session: Session = Depends(get_session)) -> dict[str, object]:
    settings = session.get(UserSettings, user.id)
    timezone_name = settings.timezone if settings else "UTC"
    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        zone, timezone_name = ZoneInfo("UTC"), "UTC"
    now = datetime.now(timezone.utc)
    week_end = now + timedelta(days=7)
    tasks = session.scalars(select(Task).where(
        Task.owner_id == user.id, Task.status.notin_([TaskStatus.DONE, TaskStatus.CANCELLED]),
    ).order_by(Task.updated_at.desc()).limit(200)).all()
    schedules = session.scalars(select(TaskSchedule).where(
        TaskSchedule.user_id == user.id, TaskSchedule.end_at >= now,
    ).order_by(TaskSchedule.start_at).limit(100)).all()
    scheduled_ids = {row.task_id for row in schedules}
    dated = [(task, _aware(task.due_at)) for task in tasks]
    passed = [task for task, due in dated if due and due < now]
    due_soon = [task for task, due in dated if due and now <= due <= week_end]
    blocked = [task for task in tasks if task.status == TaskStatus.BLOCKED]
    unscheduled_soon = [task for task in due_soon if task.id not in scheduled_ids]

    findings: list[dict[str, object]] = []
    if passed:
        findings.append({"kind": "recovery", "severity": "attention", "title": "Dates to revisit",
            "detail": f"{len(passed)} open task{'s have' if len(passed) != 1 else ' has'} a date that has passed. Review, reschedule, shrink, or release the work.",
            "evidence": [{"task_id": str(task.id), "title": task.title,
                "due_at": _aware(task.due_at).astimezone(zone).isoformat() if task.due_at else None} for task in passed[:5]],
            "suggested_prompt": "Help me realistically recover the open tasks whose dates have passed."})
    if blocked:
        findings.append({"kind": "blockers", "severity": "attention", "title": "Blocked work",
            "detail": f"{len(blocked)} task{'s are' if len(blocked) != 1 else ' is'} marked blocked. Resolve a prerequisite or choose another useful move.",
            "evidence": [{"task_id": str(task.id), "title": task.title} for task in blocked[:5]],
            "suggested_prompt": "Review my blocked tasks and identify the smallest useful unblock action."})
    if unscheduled_soon:
        findings.append({"kind": "schedule", "severity": "planning", "title": "Due soon without time reserved",
            "detail": f"{len(unscheduled_soon)} task{'s are' if len(unscheduled_soon) != 1 else ' is'} due in the next seven days without a calendar block.",
            "evidence": [{"task_id": str(task.id), "title": task.title,
                "due_at": _aware(task.due_at).astimezone(zone).isoformat() if task.due_at else None} for task in unscheduled_soon[:5]],
            "suggested_prompt": "Find realistic time for my unscheduled tasks due this week."})

    timed_events = session.scalars(select(CalendarEvent).where(
        CalendarEvent.user_id == user.id, CalendarEvent.is_all_day.is_(False),
        CalendarEvent.end_at >= now, CalendarEvent.start_at <= week_end,
    ).order_by(CalendarEvent.start_at).limit(100)).all()
    intervals = ([{"kind": "event", "title": row.title, "start": _aware(row.start_at), "end": _aware(row.end_at)} for row in timed_events]
                 + [{"kind": "task", "title": next((task.title for task in tasks if task.id == row.task_id), "Scheduled task"),
                     "start": _aware(row.start_at), "end": _aware(row.end_at)} for row in schedules if _aware(row.start_at) <= week_end])
    intervals.sort(key=lambda item: item["start"])
    conflicts = [{"first": previous["title"], "second": current["title"],
                  "at": current["start"].astimezone(zone).isoformat()}
                 for previous, current in zip(intervals, intervals[1:]) if current["start"] < previous["end"]]
    if conflicts:
        findings.insert(0, {"kind": "conflict", "severity": "attention", "title": "Schedule conflicts",
            "detail": f"{len(conflicts)} overlapping calendar commitment{'s' if len(conflicts) != 1 else ''} need a decision.",
            "evidence": conflicts[:5], "suggested_prompt": "Review my schedule conflicts and propose safe adjustments without changing anything yet."})

    candidates = [task for task in tasks if task.status != TaskStatus.BLOCKED]
    priority = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
    candidates.sort(key=lambda task: (0 if task.status == TaskStatus.IN_PROGRESS else 1,
        priority.get(task.priority.value, 4), _aware(task.due_at) or datetime.max.replace(tzinfo=timezone.utc), task.updated_at))
    one = candidates[0] if candidates else None
    return_point = None
    if one:
        point = session.scalar(select(TaskReturnPoint).where(
            TaskReturnPoint.user_id == user.id, TaskReturnPoint.task_id == one.id,
        ).order_by(TaskReturnPoint.created_at.desc()).limit(1))
        if point:
            return_point = {"next_action": point.next_action, "stopped_at": point.stopped_at, "blocker": point.blocker}
    completed = session.scalars(select(Task).where(
        Task.owner_id == user.id, Task.status == TaskStatus.DONE,
        Task.completed_at >= now - timedelta(days=7),
    ).order_by(Task.completed_at.desc()).limit(100)).all()
    advanced_projects = {task.project_id for task in completed if task.project_id}
    project_names = session.scalars(select(Project.name).where(
        Project.owner_id == user.id, Project.id.in_(advanced_projects))).all() if advanced_projects else []
    return {"generated_at": now.isoformat(), "timezone": timezone_name,
        "one_move": ({"task_id": str(one.id), "title": one.title,
            "first_step": one.first_step, "why": one.why, "return_point": return_point,
            "reason": "Already in progress" if one.status == TaskStatus.IN_PROGRESS else
                      f"{one.priority.value.capitalize()} priority" + (" with an approaching date" if one in due_soon or one in passed else "")}
            if one else None),
        "findings": findings[:3],
        "progress": {"completed_tasks": len(completed), "advanced_projects": list(project_names)[:5]},
        "scope": {"open_tasks_reviewed": len(tasks), "scheduled_blocks_reviewed": len(schedules),
                  "calendar_events_reviewed": len(timed_events)}}
