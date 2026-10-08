"""User device management and authenticated worker gateway."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import uuid
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from orin_api.auth import get_current_user
from orin_api.database import get_session
from orin_api.models import Approval, ApprovalStatus, Command, DeviceStatus, User, WorkerDevice, WorkerJob, WorkerJobStatus

router = APIRouter(prefix="/api/v1", tags=["devices and worker"])
_SECRET_PROGRESS = re.compile(r"(?i)(bearer\s+\S+|(?:password|token|secret|api[_-]?key)\s*[:=]\s*\S+)")
DEVICE_SCOPES = {
    "get_system_info": ("system.info.read", "low"),
    "list_directory": ("filesystem.directory.read", "low"),
    "read_file": ("filesystem.file.read", "low"),
    "write_file": ("filesystem.file.write", "medium"),
    "run_allowed_command": ("process.command.execute", "high"),
}


class DeviceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    platform: str = Field(min_length=1, max_length=80)
    version: str = Field(min_length=1, max_length=40)


class DeviceRename(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class JobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str
    parameters: dict[str, Any]


class JobEvent(BaseModel):
    status: str
    message: str | None = Field(default=None, max_length=240)
    result: dict[str, Any] | None = None


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _device_view(row: WorkerDevice) -> dict[str, object]:
    state = row.status.value
    last_seen = row.last_seen_at
    if row.status == DeviceStatus.ACTIVE and (last_seen is None or _utc(last_seen) < datetime.now(timezone.utc) - timedelta(minutes=2)):
        state = DeviceStatus.OFFLINE.value
    return {"id": row.id, "name": row.name, "platform": row.platform, "version": row.version,
            "status": state, "last_seen_at": row.last_seen_at, "created_at": row.created_at}


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _worker_device(authorization: Annotated[str | None, Header()] = None, session: Session = Depends(get_session)) -> WorkerDevice:
    scheme, _, credential = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or len(credential) < 32:
        raise HTTPException(status_code=401, detail="Worker authentication required")
    device = session.scalar(select(WorkerDevice).where(WorkerDevice.credential_hash == _hash(credential)))
    if device is None:
        raise HTTPException(status_code=401, detail="Worker credential is invalid or revoked")
    if device.status not in {DeviceStatus.ACTIVE, DeviceStatus.PENDING, DeviceStatus.REVOKED}:
        raise HTTPException(status_code=403, detail="Worker device is not active")
    session.info["worker_credential"] = credential
    return device


@router.get("/devices")
def list_devices(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[dict[str, object]]:
    return [_device_view(row) for row in session.scalars(select(WorkerDevice).where(WorkerDevice.owner_id == user.id).order_by(WorkerDevice.created_at.desc())).all()]


@router.post("/devices", status_code=status.HTTP_201_CREATED)
def register_device(data: DeviceCreate, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict[str, object]:
    credential = secrets.token_urlsafe(48)
    device = WorkerDevice(owner_id=user.id, name=data.name.strip(), platform=data.platform,
                          version=data.version, credential_hash=_hash(credential), status=DeviceStatus.PENDING)
    session.add(device)
    session.flush()
    view = _device_view(device)
    session.commit()
    # Returned exactly once; only a non-reversible hash is stored.
    return {**view, "credential": credential}


@router.patch("/devices/{device_id}")
def rename_device(device_id: uuid.UUID, data: DeviceRename, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict[str, object]:
    row = session.scalar(select(WorkerDevice).where(WorkerDevice.id == device_id, WorkerDevice.owner_id == user.id))
    if row is None:
        raise HTTPException(status_code=404, detail="Device not found")
    if row.status == DeviceStatus.REVOKED:
        raise HTTPException(status_code=409, detail="Revoked devices cannot be renamed")
    row.name = data.name.strip()
    session.commit()
    return _device_view(row)


@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, response_model=None)
def revoke_device(device_id: uuid.UUID, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> Response:
    row = session.scalar(select(WorkerDevice).where(WorkerDevice.id == device_id, WorkerDevice.owner_id == user.id).with_for_update())
    if row is None:
        raise HTTPException(status_code=404, detail="Device not found")
    row.status = DeviceStatus.REVOKED
    jobs = session.scalars(select(WorkerJob).where(WorkerJob.device_id == row.id, WorkerJob.status.in_([WorkerJobStatus.PENDING_APPROVAL, WorkerJobStatus.QUEUED])).with_for_update()).all()
    for job in jobs:
        job.status = WorkerJobStatus.CANCELLED
        job.finished_at = datetime.now(timezone.utc)
        approval = session.get(Approval, job.approval_id)
        if approval and approval.status in {ApprovalStatus.PENDING, ApprovalStatus.APPROVED}:
            approval.status = ApprovalStatus.CANCELLED
            approval.decided_at = datetime.now(timezone.utc)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/devices/{device_id}/jobs", status_code=status.HTTP_202_ACCEPTED)
def create_job(device_id: uuid.UUID, data: JobCreate, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict[str, object]:
    device = session.scalar(select(WorkerDevice).where(WorkerDevice.id == device_id, WorkerDevice.owner_id == user.id, WorkerDevice.status != DeviceStatus.REVOKED))
    if device is None:
        raise HTTPException(status_code=404, detail="Active device not found")
    policy = DEVICE_SCOPES.get(data.action)
    if policy is None:
        raise HTTPException(status_code=422, detail="Worker action is not supported")
    scope, risk = policy
    required_parameters = {"get_system_info": set(), "list_directory": {"path"}, "read_file": {"path"},
                          "write_file": {"path", "content"}, "run_allowed_command": {"command"}}[data.action]
    if set(data.parameters) != required_parameters:
        raise HTTPException(status_code=422, detail="Worker action parameters are invalid")
    if data.action == "write_file" and not isinstance(data.parameters.get("content"), str):
        raise HTTPException(status_code=422, detail="Worker file content must be text")
    if data.action == "write_file" and len(data.parameters["content"].encode("utf-8")) > 1_000_000:
        raise HTTPException(status_code=422, detail="Worker file content exceeds the 1 MB limit")
    if data.action in {"list_directory", "read_file", "write_file"} and not isinstance(data.parameters.get("path"), str):
        raise HTTPException(status_code=422, detail="Worker path must be text")
    if data.action in {"list_directory", "read_file", "write_file"} and len(data.parameters["path"]) > 4096:
        raise HTTPException(status_code=422, detail="Worker path is too long")
    if data.action == "run_allowed_command" and data.parameters.get("command") not in {"git_status", "git_version"}:
        raise HTTPException(status_code=422, detail="Command is not on the worker allowlist")
    now = datetime.now(timezone.utc)
    command = Command(user_id=user.id, text=f"Worker action request: {data.action}")
    session.add(command)
    session.flush()
    approval = Approval(command_id=command.id, requested_by_id=user.id, status=ApprovalStatus.PENDING,
        action_name=f"worker_{data.action}", action_payload=data.parameters, risk_level=risk,
        permission=scope, reversible=data.action in {"get_system_info", "list_directory", "read_file"},
        decision_note="Worker actions always require explicit approval.", expires_at=now + timedelta(hours=24))
    session.add(approval)
    session.flush()
    job = WorkerJob(user_id=user.id, device_id=device.id, approval_id=approval.id, action=data.action,
        parameters=data.parameters, scopes=[scope], status=WorkerJobStatus.PENDING_APPROVAL,
        nonce=secrets.token_hex(32), expires_at=now + timedelta(hours=24))
    session.add(job)
    session.commit()
    return {"id": job.id, "status": job.status.value, "approval_id": approval.id, "action": job.action,
            "risk_level": risk, "created_at": job.created_at, "expires_at": job.expires_at}


@router.get("/devices/{device_id}/jobs")
def list_user_jobs(device_id: uuid.UUID, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[dict[str, object]]:
    if session.scalar(select(WorkerDevice.id).where(WorkerDevice.id == device_id, WorkerDevice.owner_id == user.id)) is None:
        raise HTTPException(status_code=404, detail="Device not found")
    rows = session.scalars(select(WorkerJob).where(WorkerJob.user_id == user.id, WorkerJob.device_id == device_id).order_by(WorkerJob.created_at.desc()).limit(100)).all()
    now = datetime.now(timezone.utc)
    for row in rows:
        if row.status in {WorkerJobStatus.PENDING_APPROVAL, WorkerJobStatus.QUEUED, WorkerJobStatus.STARTING, WorkerJobStatus.RUNNING} and _utc(row.expires_at) <= now:
            row.status = WorkerJobStatus.EXPIRED
            row.finished_at = now
            approval = session.get(Approval, row.approval_id)
            if approval and approval.status == ApprovalStatus.PENDING:
                approval.status = ApprovalStatus.EXPIRED
    session.commit()
    return [{"id": row.id, "action": row.action, "status": row.status.value, "progress": row.progress,
             "result": row.result, "failure": row.failure, "created_at": row.created_at, "finished_at": row.finished_at} for row in rows]


@router.post("/worker/heartbeat")
def heartbeat(device: WorkerDevice = Depends(_worker_device), session: Session = Depends(get_session),
              worker_platform: Annotated[str | None, Header(alias="X-Worker-Platform")] = None,
              worker_version: Annotated[str | None, Header(alias="X-Worker-Version")] = None) -> dict[str, object]:
    if device.status == DeviceStatus.REVOKED:
        raise HTTPException(status_code=401, detail="Worker device is revoked")
    device.last_seen_at = datetime.now(timezone.utc)
    if device.status == DeviceStatus.PENDING:
        device.status = DeviceStatus.ACTIVE
    if worker_platform:
        device.platform = worker_platform[:80]
    if worker_version:
        device.version = worker_version[:40]
    session.commit()
    return {"device_id": str(device.id), "status": "active"}


@router.post("/worker/jobs/claim")
def claim_job(device: WorkerDevice = Depends(_worker_device), session: Session = Depends(get_session)) -> dict[str, object] | None:
    now = datetime.now(timezone.utc)
    locked_device = session.scalar(select(WorkerDevice).where(WorkerDevice.id == device.id).with_for_update())
    if locked_device is None or locked_device.status != DeviceStatus.ACTIVE:
        raise HTTPException(status_code=401, detail="Worker device is revoked")
    expired = session.scalars(select(WorkerJob).where(WorkerJob.device_id == device.id,
        WorkerJob.status == WorkerJobStatus.QUEUED, WorkerJob.expires_at <= now).with_for_update()).all()
    for stale in expired:
        stale.status = WorkerJobStatus.EXPIRED
        stale.finished_at = now
    device.last_seen_at = now
    job = session.scalar(select(WorkerJob).where(WorkerJob.device_id == device.id,
        WorkerJob.status == WorkerJobStatus.QUEUED, WorkerJob.expires_at > now).order_by(WorkerJob.created_at).with_for_update(skip_locked=True))
    if job is None:
        session.commit()
        return None
    approval = session.scalar(select(Approval).where(Approval.id == job.approval_id, Approval.requested_by_id == device.owner_id))
    if approval is None or approval.status != ApprovalStatus.APPROVED or approval.action_payload != job.parameters:
        job.status = WorkerJobStatus.CANCELLED
        session.commit()
        return None
    job.status = WorkerJobStatus.STARTING
    job.claimed_at = now
    job.progress = "Worker accepted the approved job"
    payload: dict[str, object] = {"job_id": str(job.id), "device_id": str(device.id),
        "expires_at": int(_utc(job.expires_at).timestamp()), "action": job.action,
        "parameters": job.parameters, "scopes": job.scopes, "approval_id": str(job.approval_id),
        "approved": True, "nonce": job.nonce}
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    credential = session.info.get("worker_credential")
    # The device credential is only available in this authenticated request; _worker_device stores it in request-local session info.
    if not isinstance(credential, str):
        raise HTTPException(status_code=401, detail="Worker authentication required")
    signature = hmac.new(credential.encode(), canonical, hashlib.sha256).hexdigest()
    session.commit()
    return {"payload": payload, "signature": signature}


@router.post("/worker/jobs/{job_id}/event")
def worker_event(job_id: uuid.UUID, event: JobEvent, device: WorkerDevice = Depends(_worker_device), session: Session = Depends(get_session)) -> dict[str, object]:
    if device.status not in {DeviceStatus.ACTIVE, DeviceStatus.REVOKED}:
        raise HTTPException(status_code=403, detail="Worker device is not active")
    job = session.scalar(select(WorkerJob).where(WorkerJob.id == job_id, WorkerJob.device_id == device.id).with_for_update())
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    now = datetime.now(timezone.utc)
    if _utc(job.expires_at) <= now:
        job.status = WorkerJobStatus.EXPIRED
        job.finished_at = now
        session.commit()
        raise HTTPException(status_code=409, detail="Job expired")
    allowed = {"starting": WorkerJobStatus.STARTING, "running": WorkerJobStatus.RUNNING,
               "completed": WorkerJobStatus.COMPLETED, "failed": WorkerJobStatus.FAILED}
    next_status = allowed.get(event.status)
    if next_status in {WorkerJobStatus.COMPLETED, WorkerJobStatus.FAILED} and job.status == next_status:
        if event.status == "completed" and job.result != event.result:
            raise HTTPException(status_code=409, detail="Duplicate result does not match the recorded result")
        return {"job_id": str(job.id), "status": job.status.value}
    if next_status is None or job.status not in {WorkerJobStatus.STARTING, WorkerJobStatus.RUNNING}:
        raise HTTPException(status_code=409, detail="Invalid job state transition")
    if device.status == DeviceStatus.REVOKED and event.status not in {"completed", "failed"}:
        raise HTTPException(status_code=403, detail="Revoked devices may only report an already claimed job")
    job.status = next_status
    if event.status in {"completed", "failed"}:
        if event.result is not None and len(json.dumps(event.result, ensure_ascii=True).encode("utf-8")) > 1_000_000:
            raise HTTPException(status_code=413, detail="Worker result exceeds the 1 MB limit")
        job.finished_at = now
        job.result = event.result if event.status == "completed" else None
        # Keep failure messages generic; never trust a worker to report secrets safely.
        job.failure = "Worker action failed." if event.status == "failed" else None
        if event.status == "completed":
            approval = session.get(Approval, job.approval_id)
            if approval:
                approval.status = ApprovalStatus.EXECUTED
    else:
        job.progress = _SECRET_PROGRESS.sub("[redacted]", event.message or event.status.capitalize())
    device.last_seen_at = now
    session.commit()
    return {"job_id": str(job.id), "status": job.status.value}
