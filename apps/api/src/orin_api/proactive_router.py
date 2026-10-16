"""Evidence-based planning and recovery signals for the signed-in user."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from orin_api.auth import get_current_user
from orin_api.database import get_session
from orin_api.memory_context import memory_provenance
from orin_api.models import (Activity, CalendarEvent, Memory, Opportunity, Project, Risk, Task, TaskDependency,
                             TaskReturnPoint, TaskSchedule, TaskStatus, User, UserPreferences, UserSettings)
from orin_api.action_plan_router import ActionPlanRequest, PlanStep, _preview, _run_plan
from orin_api.models import Command, CommandStatus


router = APIRouter(prefix="/api/v1/intelligence", tags=["personal intelligence"])


class DecisionScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=3, max_length=1000)
    project_id: uuid.UUID
    delay_days: int = Field(default=0, ge=0, le=365)


class BrainDumpRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=3, max_length=6000)
    execute: bool = False


def _aware(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


@router.get("/briefing")
def proactive_briefing(user: User = Depends(get_current_user),
                       session: Session = Depends(get_session)) -> dict[str, object]:
    settings = session.get(UserSettings, user.id)
    preferences = session.scalar(select(UserPreferences).where(UserPreferences.user_id == user.id))
    proactive_mode = preferences.proactive_mode if preferences else "supportive"
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
    if proactive_mode == "quiet":
        one, findings = None, []
    return {"generated_at": now.isoformat(), "timezone": timezone_name, "proactive_mode": proactive_mode,
        "one_move": ({"task_id": str(one.id), "title": one.title,
            "first_step": one.first_step, "why": one.why, "return_point": return_point,
            "reason": "Already in progress" if one.status == TaskStatus.IN_PROGRESS else
                      f"{one.priority.value.capitalize()} priority" + (" with an approaching date" if one in due_soon or one in passed else "")}
            if one else None),
        "findings": findings[:3],
        "progress": {"completed_tasks": len(completed), "advanced_projects": list(project_names)[:5]},
        "scope": {"open_tasks_reviewed": len(tasks), "scheduled_blocks_reviewed": len(schedules),
                  "calendar_events_reviewed": len(timed_events)}}


@router.get("/radar")
def personal_radar(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict[str, object]:
    now = datetime.now(timezone.utc); today = now.date(); horizon = today + timedelta(days=14)
    risks = session.scalars(select(Risk).where(
        Risk.user_id == user.id, Risk.status.in_(["open", "watching"]),
    ).order_by((Risk.likelihood * Risk.impact).desc()).limit(20)).all()
    opportunities = session.scalars(select(Opportunity).where(
        Opportunity.user_id == user.id, Opportunity.stage.notin_(["won", "closed"]),
    ).order_by(Opportunity.deadline.asc().nulls_last()).limit(50)).all()
    commitments = session.scalars(select(Memory).where(
        Memory.user_id == user.id, Memory.memory_type == "commitment", Memory.archived.is_(False),
    ).order_by(Memory.updated_at.asc()).limit(50)).all()
    items: list[dict[str, object]] = []
    for row in risks:
        if row.likelihood * row.impact >= 12 or (row.review_on and row.review_on <= horizon):
            items.append({"kind": "risk", "id": str(row.id), "title": row.title,
                "why": f"Open risk rated {row.likelihood} likelihood × {row.impact} impact.",
                "project_id": str(row.project_id) if row.project_id else None,
                "date": row.review_on.isoformat() if row.review_on else None, "confidence": "confirmed"})
    for row in opportunities:
        if (row.deadline and row.deadline <= horizon) or (row.review_on and row.review_on <= today):
            items.append({"kind": "opportunity", "id": str(row.id), "title": row.title,
                "why": "A recorded deadline is approaching." if row.deadline else "Its review date has arrived.",
                "project_id": str(row.project_id) if row.project_id else None,
                "date": (row.deadline or row.review_on).isoformat(), "confidence": "confirmed"})
    for row in commitments:
        metadata = row.metadata_json or {}
        if metadata.get("status") != "completed" and _aware(row.updated_at) < now - timedelta(days=14):
            items.append({"kind": "commitment", "id": str(row.id), "title": row.title,
                "why": "This open commitment has not been updated in fourteen days.",
                "project_id": str(row.project_id) if row.project_id else None, "date": None,
                "confidence": memory_provenance(row)})
    order = {"risk": 0, "commitment": 1, "opportunity": 2}
    items.sort(key=lambda item: (order.get(str(item["kind"]), 9), str(item.get("date") or "9999")))
    return {"items": items[:12], "scope": {"risks": len(risks), "opportunities": len(opportunities),
        "commitments": len(commitments)}, "generated_at": now.isoformat()}


@router.get("/graph")
def life_graph(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict[str, object]:
    projects = session.scalars(select(Project).where(Project.owner_id == user.id).limit(100)).all()
    tasks = session.scalars(select(Task).where(Task.owner_id == user.id).limit(300)).all()
    memories = session.scalars(select(Memory).where(Memory.user_id == user.id, Memory.archived.is_(False)).limit(150)).all()
    opportunities = session.scalars(select(Opportunity).where(Opportunity.user_id == user.id).limit(100)).all()
    risks = session.scalars(select(Risk).where(Risk.user_id == user.id).limit(100)).all()
    dependencies = session.scalars(select(TaskDependency).where(
        TaskDependency.task_id.in_([task.id for task in tasks]))).all() if tasks else []
    nodes = ([{"id": f"project:{row.id}", "kind": "project", "label": row.name, "status": row.status.value} for row in projects]
        + [{"id": f"task:{row.id}", "kind": "task", "label": row.title, "status": row.status.value} for row in tasks]
        + [{"id": f"memory:{row.id}", "kind": "goal" if row.memory_type == "identity" else "memory",
            "label": row.title, "status": memory_provenance(row)} for row in memories]
        + [{"id": f"opportunity:{row.id}", "kind": "opportunity", "label": row.title, "status": row.stage} for row in opportunities]
        + [{"id": f"risk:{row.id}", "kind": "risk", "label": row.title, "status": row.status} for row in risks])
    edges = ([{"from": f"task:{row.id}", "to": f"project:{row.project_id}", "relationship": "contributes_to"}
              for row in tasks if row.project_id]
        + [{"from": f"memory:{row.id}", "to": f"project:{row.project_id}", "relationship": "informs"}
           for row in memories if row.project_id]
        + [{"from": f"opportunity:{row.id}", "to": f"project:{row.project_id}", "relationship": "supports"}
           for row in opportunities if row.project_id]
        + [{"from": f"opportunity:{row.id}", "to": f"task:{row.task_id}", "relationship": "next_action"}
           for row in opportunities if row.task_id]
        + [{"from": f"risk:{row.id}", "to": f"project:{row.project_id}", "relationship": "may_affect"}
           for row in risks if row.project_id]
        + [{"from": f"risk:{row.id}", "to": f"opportunity:{row.opportunity_id}", "relationship": "may_affect"}
           for row in risks if row.opportunity_id]
        + [{"from": f"task:{row.task_id}", "to": f"task:{row.depends_on_task_id}", "relationship": "depends_on"}
           for row in dependencies])
    return {"nodes": nodes, "edges": edges, "scope": {"truncated": any((len(projects) == 100, len(tasks) == 300,
        len(memories) == 150, len(opportunities) == 100, len(risks) == 100))}}


@router.post("/simulate")
def simulate_decision(data: DecisionScenario, user: User = Depends(get_current_user),
                      session: Session = Depends(get_session)) -> dict[str, object]:
    project = session.scalar(select(Project).where(Project.id == data.project_id, Project.owner_id == user.id))
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    tasks = session.scalars(select(Task).where(Task.owner_id == user.id, Task.project_id == project.id,
        Task.status.notin_([TaskStatus.DONE, TaskStatus.CANCELLED]))).all()
    task_ids = {task.id for task in tasks}
    dependencies = session.scalars(select(TaskDependency).where(
        TaskDependency.depends_on_task_id.in_(task_ids))).all() if task_ids else []
    schedules = session.scalars(select(TaskSchedule).where(
        TaskSchedule.user_id == user.id, TaskSchedule.task_id.in_(task_ids))).all() if task_ids else []
    known = [{"fact": f"{len(tasks)} open tasks belong to {project.name}.", "source": "workspace"},
        {"fact": f"{len(dependencies)} downstream task dependencies reference its open tasks.", "source": "workspace"},
        {"fact": f"{len(schedules)} calendar blocks are reserved for its open tasks.", "source": "workspace"}]
    estimates: list[dict[str, str]] = []
    if data.delay_days:
        affected_due = sum(bool(task.due_at) for task in tasks)
        estimates.append({"estimate": f"A {data.delay_days}-day delay may put {affected_due} dated open tasks under more schedule pressure.",
            "assumption": "The task dates and scope remain unchanged."})
        if dependencies:
            estimates.append({"estimate": f"Up to {len(dependencies)} dependent tasks may also move later.",
                "assumption": "Dependencies remain active and cannot proceed in parallel."})
    if schedules:
        estimates.append({"estimate": f"{len(schedules)} reserved calendar blocks may need review.",
            "assumption": "The current blocks are project-specific and cannot be repurposed."})
    return {"question": data.question, "project": {"id": str(project.id), "name": project.name},
        "known_facts": known, "estimates": estimates,
        "unknowns": ["Available people, budget, and scope changes are not represented in this workspace."],
        "recommendation": "Review the affected tasks and calendar blocks before deciding. This simulation did not change any records.",
        "changes_applied": False}


@router.get("/missing")
def what_am_i_missing(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict[str, object]:
    briefing = proactive_briefing(user, session)
    tasks = session.scalars(select(Task).where(
        Task.owner_id == user.id, Task.status.notin_([TaskStatus.DONE, TaskStatus.CANCELLED])
    ).limit(300)).all()
    task_ids = {row.id for row in tasks}
    dependencies = session.scalars(select(TaskDependency).where(TaskDependency.task_id.in_(task_ids))).all() if task_ids else []
    existing = {row.id: row for row in tasks}
    findings = list(briefing.get("findings", []))
    unresolved = [row for row in dependencies if row.depends_on_task_id in existing and existing[row.depends_on_task_id].status != TaskStatus.DONE]
    if unresolved:
        findings.append({"kind": "dependency", "confidence": "confirmed", "title": "Unresolved task dependencies",
            "detail": f"{len(unresolved)} open task relationship(s) still depend on unfinished work.",
            "evidence": [{"task_id": str(row.task_id), "depends_on_task_id": str(row.depends_on_task_id)} for row in unresolved[:5]],
            "suggested_action": "Review the dependency order before scheduling downstream work."})
    undated = [row for row in tasks if row.due_at is None and row.priority.value in {"urgent", "high"}]
    if undated:
        findings.append({"kind": "commitment", "confidence": "possible concern", "title": "Important work without a decision date",
            "detail": f"{len(undated)} high-priority open task(s) have no recorded date.",
            "evidence": [{"task_id": str(row.id), "title": row.title} for row in undated[:5]],
            "suggested_action": "Decide whether each item needs time reserved, a date, or release."})
    normalized = []
    for item in findings[:5]:
        normalized.append({**item, "confidence": item.get("confidence", "confirmed"),
                           "suggested_action": item.get("suggested_action") or item.get("suggested_prompt")})
    return {"findings": normalized, "scope": {"open_tasks": len(tasks), "dependencies": len(dependencies)},
            "changes_applied": False}


@router.get("/reflection")
def personal_reflection(period: Literal["daily", "weekly"] = "weekly", user: User = Depends(get_current_user),
                        session: Session = Depends(get_session)) -> dict[str, object]:
    now = datetime.now(timezone.utc); start = now - timedelta(days=1 if period == "daily" else 7)
    completed = session.scalars(select(Task).where(
        Task.owner_id == user.id, Task.status == TaskStatus.DONE, Task.completed_at >= start
    ).order_by(Task.completed_at.desc()).limit(100)).all()
    activities = session.scalars(select(Activity).where(
        Activity.user_id == user.id, Activity.created_at >= start
    ).order_by(Activity.created_at.desc()).limit(200)).all()
    decisions = session.scalars(select(Memory).where(
        Memory.user_id == user.id, Memory.memory_type == "decision", Memory.updated_at >= start,
        Memory.archived.is_(False)).limit(50)).all()
    advanced_ids = {row.project_id for row in completed if row.project_id}
    projects = session.scalars(select(Project).where(Project.owner_id == user.id, Project.id.in_(advanced_ids))).all() if advanced_ids else []
    return {"period": period, "start": start.isoformat(), "end": now.isoformat(),
            "accomplishments": [{"task_id": str(row.id), "title": row.title} for row in completed],
            "projects_advanced": [{"project_id": str(row.id), "name": row.name} for row in projects],
            "decisions": [{"memory_id": str(row.id), "title": row.title} for row in decisions],
            "activity_count": len(activities),
            "reflection": (f"You completed {len(completed)} task(s) and advanced {len(projects)} project(s)."
                           if completed else "No completed tasks were recorded in this period. Review open work without treating missing records as failure."),
            "evidence_only": True}


@router.post("/brain-dump")
def organize_brain_dump(data: BrainDumpRequest, user: User = Depends(get_current_user),
                        session: Session = Depends(get_session)) -> dict[str, object]:
    fragments = [part.strip(" .-\t") for part in re.split(r"[\n;]+|(?<=[.!?])\s+", data.text) if part.strip(" .-\t")][:20]
    if not fragments:
        raise HTTPException(status_code=422, detail="The brain dump does not contain an actionable item.")
    items: list[dict[str, str]] = []
    steps: list[PlanStep] = []
    for index, text in enumerate(fragments):
        lowered = text.casefold()
        kind = "idea" if any(word in lowered for word in ("idea", "maybe", "could")) else "project" if lowered.startswith(("project ", "start a project", "create a project")) else "task"
        items.append({"text": text, "kind": kind, "confidence": "rule-based suggestion"})
        if kind == "idea":
            steps.append(PlanStep(id=f"item_{index + 1}", action="save_memory", inputs={"memory_type": "knowledge", "memory_title": text[:180], "memory_content": text}))
        elif kind == "project":
            title = re.sub(r"^(?:create|start)\s+(?:a\s+)?project\s+(?:for\s+|to\s+)?", "", text, flags=re.I).strip() or text
            steps.append(PlanStep(id=f"item_{index + 1}", action="create_project", inputs={"name": title[:160]}))
        else:
            steps.append(PlanStep(id=f"item_{index + 1}", action="create_task", inputs={"title": text[:240]}))
    plan = ActionPlanRequest(title="Organize brain dump", steps=steps, stop_on_failure=False)
    preview = _preview(plan, session, user)
    if not data.execute:
        return {"items": items, "preview": preview, "changes_applied": False, "plan": plan.model_dump(mode="json")}
    parent = Command(user_id=user.id, text="Brain dump action plan", status=CommandStatus.SUBMITTED, response_intent="ACTION_PLAN")
    session.add(parent); session.flush()
    result = _run_plan(parent, plan, session, user)
    return {"items": items, "preview": preview, "changes_applied": result["completed_steps"] > 0, "execution": result}
