"""Trusted validation and persistence for explicitly registered worker actions."""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from orin_api.models import Approval, ApprovalStatus, Command, DeviceStatus, User, WorkerDevice, WorkerJob, WorkerJobStatus
from orin_api.target_selection import ExecutionTarget, select_target

DEVICE_SCOPES = {
    "get_system_info": ("system.info.read", "low"),
    "list_directory": ("filesystem.directory.read", "low"),
    "read_file": ("filesystem.file.read", "low"),
    "write_file": ("filesystem.file.write", "medium"),
    "run_allowed_command": ("process.command.execute", "high"),
}
ALLOWED_WORKER_COMMANDS = {"git_status", "git_version", "python_tests", "npm_tests"}


def validate_worker_action(action: str, parameters: dict[str, Any]) -> tuple[str, str]:
    policy = DEVICE_SCOPES.get(action)
    if policy is None:
        raise HTTPException(status_code=422, detail="Worker action is not supported")
    expected = {"get_system_info": set(), "list_directory": {"path"}, "read_file": {"path"},
                "write_file": {"path", "content"}, "run_allowed_command": {"command"}}[action]
    if set(parameters) != expected:
        raise HTTPException(status_code=422, detail="Worker action parameters are invalid")
    if action == "write_file" and not isinstance(parameters.get("content"), str):
        raise HTTPException(status_code=422, detail="Worker file content must be text")
    if action == "write_file" and len(parameters["content"].encode("utf-8")) > 1_000_000:
        raise HTTPException(status_code=422, detail="Worker file content exceeds the 1 MB limit")
    if action in {"list_directory", "read_file", "write_file"}:
        if not isinstance(parameters.get("path"), str):
            raise HTTPException(status_code=422, detail="Worker path must be text")
        if len(parameters["path"]) > 4096:
            raise HTTPException(status_code=422, detail="Worker path is too long")
    if action == "run_allowed_command" and parameters.get("command") not in ALLOWED_WORKER_COMMANDS:
        raise HTTPException(status_code=422, detail="Command is not on the worker allowlist")
    return policy


def queue_user_job(session: Session, *, user: User, device: WorkerDevice, command: Command,
                   action: str, parameters: dict[str, Any],
                   requested_target: ExecutionTarget = ExecutionTarget.AUTO) -> tuple[WorkerJob, Approval]:
    (scope, risk) = validate_worker_action(action, parameters)
    if device.owner_id != user.id or device.status == DeviceStatus.REVOKED:
        raise HTTPException(status_code=404, detail="Active device not found")
    decision = select_target(requested=ExecutionTarget(requested_target),
        # Pending devices may receive a queued job, but cannot claim it until authenticated heartbeat.
        local_worker_eligible=device.status in {DeviceStatus.ACTIVE, DeviceStatus.PENDING},
        user_authorized=True, required_capabilities=frozenset({scope}),
        local_capabilities=frozenset(required for required, _risk in DEVICE_SCOPES.values()))
    if decision.selected is None:
        raise HTTPException(status_code=409, detail=decision.reason)
    now = datetime.now(timezone.utc)
    approval = Approval(command_id=command.id, requested_by_id=user.id, status=ApprovalStatus.PENDING,
        action_name=f"worker_{action}", action_payload=parameters, risk_level=risk,
        permission=scope, reversible=action in {"get_system_info", "list_directory", "read_file"},
        decision_note="Worker action requires explicit user approval.", expires_at=now + timedelta(hours=24))
    session.add(approval)
    session.flush()
    job = WorkerJob(user_id=user.id, device_id=device.id, approval_id=approval.id, action=action,
        parameters=parameters, scopes=[scope], status=WorkerJobStatus.PENDING_APPROVAL,
        nonce=secrets.token_hex(32), expires_at=now + timedelta(hours=24),
        requested_target=ExecutionTarget(requested_target).value, selected_target=decision.selected.value)
    session.add(job)
    session.flush()
    return job, approval
