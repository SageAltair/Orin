"""Coherent specialist planning and approval-aware reusable automations."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from orin_api.action_plan_router import ActionPlanRequest, _preview, _run_plan
from orin_api.auth import get_current_user
from orin_api.database import get_session
from orin_api.models import Command, CommandStatus, Memory, Opportunity, Project, Risk, Task, TaskStatus, User


router = APIRouter(prefix="/api/v1/intelligence", tags=["specialist coordination"])
Specialty = Literal["planning", "research", "writing", "development", "risk"]
Cadence = Literal["manual", "daily", "weekly"]
SPECIALTIES: dict[str, tuple[str, str]] = {
    "planning": ("Planning", "Sequence the work around current commitments and dependencies."),
    "research": ("Research", "Identify questions that need evidence before a decision."),
    "writing": ("Writing", "Turn the objective and existing knowledge into a clear deliverable."),
    "development": ("Development", "Translate the objective into testable implementation increments."),
    "risk": ("Risk", "Check failure modes, constraints, and mitigations before execution."),
}


class CoordinationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    objective: str = Field(min_length=3, max_length=1200)
    project_id: uuid.UUID | None = None
    specialties: list[Specialty] = Field(default_factory=lambda: ["planning", "risk"], min_length=1, max_length=5)


class AutomationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=160)
    objective: str = Field(min_length=3, max_length=1200)
    cadence: Cadence = "manual"
    plan: ActionPlanRequest


class AutomationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat() if value else None


def _next_run(cadence: str, now: datetime) -> datetime | None:
    return now + timedelta(days=1 if cadence == "daily" else 7) if cadence != "manual" else None


def _owned_project(session: Session, user: User, project_id: uuid.UUID | None) -> Project | None:
    if project_id is None:
        return None
    project = session.scalar(select(Project).where(Project.id == project_id, Project.owner_id == user.id))
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


@router.post("/specialists/coordinate")
def coordinate_specialists(data: CoordinationRequest, user: User = Depends(get_current_user),
                           session: Session = Depends(get_session)) -> dict[str, object]:
    project = _owned_project(session, user, data.project_id)
    tasks = session.scalars(select(Task).where(
        Task.owner_id == user.id,
        Task.project_id == data.project_id if data.project_id else Task.project_id.is_(None),
        Task.status.notin_([TaskStatus.DONE, TaskStatus.CANCELLED]),
    ).order_by(Task.updated_at.desc()).limit(25)).all()
    risks = session.scalars(select(Risk).where(
        Risk.user_id == user.id, Risk.project_id == data.project_id, Risk.status.in_(["open", "watching"])
    ).limit(15)).all() if data.project_id else []
    opportunities = session.scalars(select(Opportunity).where(
        Opportunity.user_id == user.id, Opportunity.project_id == data.project_id,
        Opportunity.stage.notin_(["won", "lost", "declined"]),
    ).limit(15)).all() if data.project_id else []
    memories = session.scalars(select(Memory).where(
        Memory.user_id == user.id, Memory.project_id == data.project_id,
    ).order_by(Memory.updated_at.desc()).limit(12)).all() if data.project_id else []
    evidence = {
        "project": {"id": str(project.id), "name": project.name} if project else None,
        "open_tasks": [{"id": str(row.id), "title": row.title, "status": row.status.value} for row in tasks],
        "risks": [{"id": str(row.id), "title": row.title, "impact": row.impact, "likelihood": row.likelihood} for row in risks],
        "opportunities": [{"id": str(row.id), "title": row.title, "stage": row.stage} for row in opportunities],
        "relevant_memories": [{"id": str(row.id), "title": row.title, "type": row.memory_type} for row in memories],
    }
    outputs: list[dict[str, object]] = []
    for specialty in dict.fromkeys(data.specialties):
        name, mandate = SPECIALTIES[specialty]
        observations: list[str] = []
        if specialty == "planning":
            observations.append(f"{len(tasks)} open task(s) are in the selected scope.")
        elif specialty == "risk":
            observations.append(f"{len(risks)} recorded open risk(s) require consideration.")
        elif specialty == "research":
            observations.append(f"{len(memories)} relevant knowledge record(s) are available; unanswered questions remain unknown.")
        elif specialty == "writing":
            observations.append("Use the stated objective and linked knowledge as source material; no unwritten content is assumed.")
        else:
            observations.append("Implementation should be split into verifiable increments before any action is executed.")
        outputs.append({"specialty": specialty, "name": name, "mandate": mandate, "observations": observations})
    return {"objective": data.objective, "project": evidence["project"], "specialists": outputs,
            "evidence": evidence, "unknowns": ["Capacity, budget, and external dependencies are unknown unless recorded."],
            "execution_boundary": "This coordination result is advisory. Create or run a validated action plan to change workspace data."}


def _automation_view(row: Command) -> dict[str, Any]:
    payload = dict(row.response_json) if isinstance(row.response_json, dict) else {}
    return {"id": str(row.id), **payload, "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat()}


@router.get("/automations")
def list_automations(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    rows = session.scalars(select(Command).where(
        Command.user_id == user.id, Command.response_intent == "AUTOMATION"
    ).order_by(Command.updated_at.desc()).limit(100)).all()
    return [_automation_view(row) for row in rows]


@router.post("/automations", status_code=201)
def create_automation(data: AutomationCreate, user: User = Depends(get_current_user),
                      session: Session = Depends(get_session)) -> dict[str, Any]:
    preview = _preview(data.plan, session, user)
    if not preview["valid"]:
        raise HTTPException(status_code=422, detail={"message": "The automation plan is invalid.", "preview": preview})
    row = Command(user_id=user.id, text=f"Automation: {data.title}", status=CommandStatus.COMPLETED,
                  response_intent="AUTOMATION", response_message="Automation saved disabled until enabled.",
                  response_json={"title": data.title, "objective": data.objective, "cadence": data.cadence,
                                 "enabled": False, "next_run_at": None, "last_run_at": None,
                                 "last_status": "never_run", "plan": data.plan.model_dump(mode="json"), "preview": preview})
    session.add(row); session.commit(); session.refresh(row)
    return _automation_view(row)


@router.patch("/automations/{automation_id}")
def update_automation(automation_id: uuid.UUID, data: AutomationUpdate,
                      user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict[str, Any]:
    row = session.scalar(select(Command).where(Command.id == automation_id, Command.user_id == user.id,
                                                Command.response_intent == "AUTOMATION").with_for_update())
    if row is None:
        raise HTTPException(status_code=404, detail="Automation not found.")
    payload = dict(row.response_json) if isinstance(row.response_json, dict) else {}
    payload["enabled"] = data.enabled
    payload["next_run_at"] = _iso(_next_run(str(payload.get("cadence", "manual")), datetime.now(timezone.utc))) if data.enabled else None
    row.response_json = payload; session.commit(); session.refresh(row)
    return _automation_view(row)


def run_automation_record(row: Command, session: Session, user: User, *, now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    payload = dict(row.response_json) if isinstance(row.response_json, dict) else {}
    plan = ActionPlanRequest.model_validate(payload.get("plan"))
    run = Command(user_id=user.id, text=f"Automation run: {payload.get('title', 'Untitled')}",
                  status=CommandStatus.SUBMITTED, response_intent="ACTION_PLAN")
    session.add(run); session.flush()
    result = _run_plan(run, plan, session, user)
    payload["last_run_at"], payload["last_status"] = _iso(current), result["status"]
    if result["status"] == "awaiting_approval":
        payload["enabled"], payload["next_run_at"] = False, None
    else:
        payload["next_run_at"] = _iso(_next_run(str(payload.get("cadence", "manual")), current)) if payload.get("enabled") else None
    row.response_json = payload; session.commit()
    return {"automation": _automation_view(row), "run": result}


@router.post("/automations/{automation_id}/run")
def run_automation(automation_id: uuid.UUID, user: User = Depends(get_current_user),
                   session: Session = Depends(get_session)) -> dict[str, Any]:
    row = session.scalar(select(Command).where(Command.id == automation_id, Command.user_id == user.id,
                                                Command.response_intent == "AUTOMATION").with_for_update())
    if row is None:
        raise HTTPException(status_code=404, detail="Automation not found.")
    return run_automation_record(row, session, user)


def run_due_automations(session: Session, now: datetime) -> None:
    rows = session.scalars(select(Command).where(Command.response_intent == "AUTOMATION").limit(500)).all()
    for row in rows:
        payload = row.response_json if isinstance(row.response_json, dict) else {}
        due = payload.get("next_run_at")
        if not payload.get("enabled") or not isinstance(due, str):
            continue
        try:
            due_at = datetime.fromisoformat(due)
        except ValueError:
            continue
        if due_at > now:
            continue
        user = session.get(User, row.user_id)
        if user is not None:
            run_automation_record(row, session, user, now=now)
