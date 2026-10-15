"""Validated, dependency-aware execution plans over Orin's trusted action registry."""
from __future__ import annotations

import json
import re
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from orin_api.approval_policy import decide_approval
from orin_api.auth import get_current_user
from orin_api.database import get_session
from orin_api.domain_router import ACTION_REGISTRY, EXECUTION_ENGINE, _commit_execution_result, _user_action_permissions
from orin_api.execution import ActionContext, ActionRequest
from orin_api.models import Command, CommandStatus, User, UserPreferences
from orin_api.services import ensure_user_preferences


router = APIRouter(prefix="/api/v1/action-plans", tags=["action-plans"])
_STEP_ID = re.compile(r"^[a-z][a-z0-9_-]{0,39}$")


class PlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=40)
    action: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    inputs: dict[str, Any]
    depends_on: list[str] = Field(default_factory=list, max_length=20)


class ActionPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=160)
    steps: list[PlanStep] = Field(min_length=1, max_length=20)
    stop_on_failure: bool = True

    @model_validator(mode="after")
    def validate_graph(self) -> "ActionPlanRequest":
        seen: set[str] = set()
        for step in self.steps:
            if not _STEP_ID.fullmatch(step.id) or step.id in seen:
                raise ValueError("Plan step IDs must be unique lowercase identifiers")
            if any(dependency not in seen for dependency in step.depends_on):
                raise ValueError("A step may depend only on earlier steps")
            seen.add(step.id)
        return self


def _contains_reference(value: Any) -> bool:
    if isinstance(value, dict):
        return set(value) == {"$from", "path"} or any(_contains_reference(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_reference(item) for item in value)
    return False


def _resolve(value: Any, results: dict[str, Any]) -> Any:
    if isinstance(value, dict) and set(value) == {"$from", "path"}:
        source, path = value["$from"], value["path"]
        if source not in results or not isinstance(path, str) or not path:
            raise ValueError("A plan reference could not be resolved")
        current = results[source]
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                raise ValueError("A plan reference could not be resolved")
            current = current[part]
        return current
    if isinstance(value, dict):
        return {key: _resolve(item, results) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve(item, results) for item in value]
    return value


def _preview(plan: ActionPlanRequest, session: Session, user: User) -> dict[str, Any]:
    ensure_user_preferences(session, user)
    preferences = session.scalar(select(UserPreferences).where(UserPreferences.user_id == user.id))
    permissions = _user_action_permissions(session, user.id)
    rows: list[dict[str, Any]] = []
    valid = True
    for step in plan.steps:
        definition = ACTION_REGISTRY.get(step.action)
        errors: list[str] = []
        if definition is None:
            errors.append("Unsupported action")
        elif definition.permission not in permissions:
            errors.append("Permission is not available")
        elif not _contains_reference(step.inputs):
            try:
                definition.input_schema.model_validate_json(json.dumps(step.inputs, default=str))
            except ValidationError:
                errors.append("Inputs are invalid")
        approval = bool(definition and decide_approval(
            definition.name, definition.risk_level.value,
            preferences.autonomy_mode if preferences else "balanced",
            definition.requires_approval,
            preferences.custom_autonomy if preferences else {},
        ).requires_approval)
        valid = valid and not errors
        rows.append({"id": step.id, "action": step.action, "depends_on": step.depends_on,
            "status": "invalid" if errors else "ready", "errors": errors,
            "approval_required": approval, "risk": definition.risk_level.value if definition else None,
            "reversibility": definition.reversibility.value if definition else None})
    return {"title": plan.title, "valid": valid, "steps": rows,
        "approval_required": any(row["approval_required"] for row in rows)}


@router.post("/preview")
def preview_action_plan(plan: ActionPlanRequest, user: User = Depends(get_current_user),
                        session: Session = Depends(get_session)) -> dict[str, Any]:
    preview = _preview(plan, session, user)
    session.commit()
    return preview


def _run_plan(parent: Command, plan: ActionPlanRequest, session: Session, user: User,
              prior_outcomes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    ensure_user_preferences(session, user)
    preferences = session.scalar(select(UserPreferences).where(UserPreferences.user_id == user.id))
    permissions = _user_action_permissions(session, user.id)
    completed_results: dict[str, Any] = {}
    outcomes: list[dict[str, Any]] = []
    prior = {str(item.get("id")): item for item in (prior_outcomes or [])}
    for step in plan.steps:
        previous = prior.get(step.id)
        if previous:
            if previous.get("status") == "completed":
                outcomes.append(previous); completed_results[step.id] = previous.get("result"); continue
            if previous.get("status") == "awaiting_approval" and previous.get("command_id"):
                child = session.scalar(select(Command).where(
                    Command.id == uuid.UUID(str(previous["command_id"])), Command.user_id == user.id))
                if child and child.status == CommandStatus.COMPLETED:
                    previous = {**previous, "status": "completed", "message": child.response_message,
                        "result": child.response_json}
                    outcomes.append(previous); completed_results[step.id] = child.response_json; continue
                if child and child.status == CommandStatus.AWAITING_APPROVAL:
                    outcomes.append(previous); break
                previous = {**previous, "status": "failed", "message": child.response_message if child else "The approval step is unavailable."}
                outcomes.append(previous)
                if plan.stop_on_failure: break
                continue
        if any(outcome["id"] in step.depends_on and outcome["status"] != "completed" for outcome in outcomes):
            outcomes.append({"id": step.id, "action": step.action, "status": "skipped", "message": "A dependency did not complete."})
            continue
        try:
            inputs = _resolve(step.inputs, completed_results)
        except ValueError as exc:
            outcomes.append({"id": step.id, "action": step.action, "status": "failed", "message": str(exc)})
            if plan.stop_on_failure: break
            continue
        child = Command(user_id=user.id, text=f"Plan step {step.id}: {step.action}", status=CommandStatus.SUBMITTED)
        session.add(child); session.flush()
        result = EXECUTION_ENGINE.execute(ActionRequest(action=step.action, inputs=inputs), ActionContext(
            session=session, user_id=user.id, command_id=child.id, permissions=permissions,
            command_text=child.text, autonomy_mode=preferences.autonomy_mode if preferences else "balanced",
            custom_autonomy=preferences.custom_autonomy if preferences else {}))
        response = _commit_execution_result(session, child, step.action.upper(), result)
        outcome = {"id": step.id, "action": step.action, "status": response.status,
            "message": response.message, "command_id": str(child.id), "result": response.result,
            "approval_id": response.execution.get("approval_id") if response.execution else None}
        outcomes.append(outcome)
        if response.status == "completed": completed_results[step.id] = response.result
        elif response.status == "awaiting_approval":
            parent.status = CommandStatus.AWAITING_APPROVAL
            break
        elif plan.stop_on_failure:
            break
    completed = sum(item["status"] == "completed" for item in outcomes)
    failed = sum(item["status"] in {"failed", "denied", "unsupported", "unverified"} for item in outcomes)
    pending = any(item["status"] == "awaiting_approval" for item in outcomes)
    status = "awaiting_approval" if pending else "completed" if completed == len(plan.steps) else "partial_success" if completed else "failed"
    parent.status = CommandStatus.AWAITING_APPROVAL if pending else CommandStatus.COMPLETED if completed else CommandStatus.FAILED
    payload = {"plan_id": str(parent.id), "title": plan.title, "status": status,
        "completed_steps": completed, "failed_steps": failed, "steps": outcomes,
        "specification": plan.model_dump(mode="json")}
    parent.response_intent = "ACTION_PLAN"; parent.response_json = payload
    parent.response_message = f"Plan {status.replace('_', ' ')}: {completed} of {len(plan.steps)} steps completed."
    session.commit()
    return payload


@router.post("/execute")
def execute_action_plan(plan: ActionPlanRequest, user: User = Depends(get_current_user),
                        session: Session = Depends(get_session),
                        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=1, max_length=160)) -> dict[str, Any]:
    if idempotency_key:
        existing = session.scalar(select(Command).where(
            Command.user_id == user.id, Command.idempotency_key == idempotency_key))
        if existing:
            stored = existing.response_json if isinstance(existing.response_json, dict) else {}
            if stored.get("specification") != plan.model_dump(mode="json"):
                raise HTTPException(status_code=409, detail="Idempotency-Key was already used for a different plan.")
            return stored
    preview = _preview(plan, session, user)
    if not preview["valid"]:
        raise HTTPException(status_code=422, detail={"message": "The plan is invalid.", "preview": preview})
    parent = Command(user_id=user.id, text=f"Action plan: {plan.title}", status=CommandStatus.SUBMITTED,
                     response_intent="ACTION_PLAN", idempotency_key=idempotency_key)
    session.add(parent); session.flush()
    return _run_plan(parent, plan, session, user)


@router.post("/{plan_id}/resume")
def resume_action_plan(plan_id: uuid.UUID, user: User = Depends(get_current_user),
                       session: Session = Depends(get_session)) -> dict[str, Any]:
    parent = session.scalar(select(Command).where(
        Command.id == plan_id, Command.user_id == user.id, Command.response_intent == "ACTION_PLAN"))
    if parent is None or not isinstance(parent.response_json, dict):
        raise HTTPException(status_code=404, detail="Action plan not found.")
    stored = parent.response_json
    if stored.get("status") != "awaiting_approval":
        raise HTTPException(status_code=409, detail="This action plan is not waiting for approval.")
    plan = ActionPlanRequest.model_validate(stored.get("specification"))
    return _run_plan(parent, plan, session, user, list(stored.get("steps", [])))


@router.get("/history")
def action_plan_history(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    rows = session.scalars(select(Command).where(Command.user_id == user.id, Command.response_intent == "ACTION_PLAN")
                           .order_by(Command.created_at.desc()).limit(50)).all()
    return [row.response_json for row in rows if isinstance(row.response_json, dict)]
