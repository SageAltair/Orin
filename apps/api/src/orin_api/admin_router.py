"""Administrator-only operational insight and account controls."""

from datetime import datetime, timedelta, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from orin_api.auth import get_current_user
from orin_api.database import get_session
from orin_api.models import (
    AdminAuditEvent, AIUsageRecord, Approval, AuthSession, Command, DeviceStatus, FileAttachment, Project,
    RefreshToken, RequestRateWindow, SystemSetting, Task, User, WorkerDevice, WorkerJob,
    WorkerJobStatus, Workspace,
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def _audit(session: Session, actor: User, action: str, target_type: str,
           target_id: object | None = None, **detail: object) -> None:
    session.add(AdminAuditEvent(actor_user_id=actor.id, action=action, target_type=target_type,
                                target_id=None if target_id is None else str(target_id), detail_json=detail))


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required")
    return user


def _count(session: Session, model: type[object], *conditions: object) -> int:
    return int(session.scalar(select(func.count()).select_from(model).where(*conditions)) or 0)


@router.get("/overview")
def overview(
    _: User = Depends(require_admin), session: Session = Depends(get_session),
) -> dict[str, object]:
    now = datetime.now(timezone.utc)
    recent = now - timedelta(days=30)
    ai_requests = _count(session, AIUsageRecord, AIUsageRecord.created_at >= recent)
    ai_failures = _count(session, AIUsageRecord, AIUsageRecord.created_at >= recent, AIUsageRecord.status != "succeeded")
    storage_bytes = int(session.scalar(select(func.coalesce(func.sum(FileAttachment.size_bytes), 0))) or 0)
    return {
        "generated_at": now,
        "totals": {
            "users": _count(session, User),
            "active_users": _count(session, User, User.is_disabled.is_(False)),
            "workspaces": _count(session, Workspace),
            "projects": _count(session, Project),
            "tasks": _count(session, Task),
            "attachments": _count(session, FileAttachment),
            "storage_bytes": storage_bytes,
        },
        "operations": {
            "active_sessions": _count(session, AuthSession, AuthSession.revoked_at.is_(None), AuthSession.expires_at > now),
            "pending_approvals": _count(session, Approval, Approval.status == "pending"),
            "commands_30d": _count(session, Command, Command.created_at >= recent),
            "active_workers": _count(session, WorkerDevice, WorkerDevice.status == "active"),
        },
        "ai": {
            "requests_30d": ai_requests,
            "failures_30d": ai_failures,
            "fallbacks_30d": _count(session, AIUsageRecord, AIUsageRecord.created_at >= recent, AIUsageRecord.used_fallback.is_(True)),
            "estimated_cost_microusd_30d": int(session.scalar(select(func.coalesce(func.sum(AIUsageRecord.estimated_cost_microusd), 0)).where(AIUsageRecord.created_at >= recent)) or 0),
            "success_rate": round(((ai_requests - ai_failures) / ai_requests) * 100, 1) if ai_requests else 100.0,
        },
    }


@router.get("/users")
def list_users(
    query: str = Query(default="", max_length=120),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    statement = select(User)
    normalized = query.strip().casefold()
    if normalized:
        term = f"%{normalized}%"
        statement = statement.where(func.lower(User.email).like(term) | func.lower(User.display_name).like(term))
    total = int(session.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    users = session.scalars(statement.order_by(User.created_at.desc()).offset(offset).limit(limit)).all()
    rows = []
    now = datetime.now(timezone.utc)
    for item in users:
        rows.append({
            "id": item.id, "email": item.email, "display_name": item.display_name,
            "is_admin": item.is_admin, "is_disabled": item.is_disabled, "created_at": item.created_at,
            "workspace_count": _count(session, Workspace, Workspace.owner_id == item.id),
            "project_count": _count(session, Project, Project.owner_id == item.id),
            "task_count": _count(session, Task, Task.owner_id == item.id),
            "active_sessions": _count(session, AuthSession, AuthSession.user_id == item.id, AuthSession.revoked_at.is_(None), AuthSession.expires_at > now),
        })
    return {"items": rows, "total": total}


class AccountStateUpdate(BaseModel):
    is_disabled: bool | None = None
    is_admin: bool | None = None


@router.patch("/users/{user_id}")
def update_account_state(
    user_id: uuid.UUID, data: AccountStateUpdate,
    admin: User = Depends(require_admin), session: Session = Depends(get_session),
) -> dict[str, object]:
    target = session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == admin.id and (data.is_disabled is True or data.is_admin is False):
        raise HTTPException(status_code=409, detail="You cannot disable your own account")
    if data.is_admin is False and target.is_admin:
        admin_count = _count(session, User, User.is_admin.is_(True), User.is_disabled.is_(False))
        if admin_count <= 1:
            raise HTTPException(status_code=409, detail="The final active administrator cannot be demoted")
    if data.is_admin is not None:
        target.is_admin = data.is_admin
    if data.is_disabled is not None:
        target.is_disabled = data.is_disabled
    if data.is_disabled is True:
        now = datetime.now(timezone.utc)
        session.execute(update(AuthSession).where(AuthSession.user_id == target.id, AuthSession.revoked_at.is_(None)).values(revoked_at=now))
    _audit(session, admin, "account.updated", "user", target.id,
           is_admin=target.is_admin, is_disabled=target.is_disabled)
    session.commit()
    return {"id": target.id, "is_disabled": target.is_disabled, "is_admin": target.is_admin}


@router.post("/users/{user_id}/revoke-sessions", status_code=204)
def revoke_user_sessions(
    user_id: uuid.UUID, admin: User = Depends(require_admin), session: Session = Depends(get_session),
) -> None:
    target = session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == admin.id:
        raise HTTPException(status_code=409, detail="Use account security to manage your own sessions")
    session.execute(update(AuthSession).where(AuthSession.user_id == target.id, AuthSession.revoked_at.is_(None)).values(revoked_at=datetime.now(timezone.utc)))
    _audit(session, admin, "sessions.revoked", "user", target.id, email=target.email or "")
    session.commit()


@router.get("/workspaces")
def list_workspaces(
    _: User = Depends(require_admin), session: Session = Depends(get_session),
) -> list[dict[str, object]]:
    rows = session.execute(
        select(Workspace, User.email).join(User, User.id == Workspace.owner_id).order_by(Workspace.updated_at.desc()).limit(100)
    ).all()
    return [{
        "id": workspace.id, "name": workspace.name, "owner_email": email,
        "project_count": _count(session, Project, Project.workspace_id == workspace.id),
        "task_count": _count(session, Task, Task.workspace_id == workspace.id),
        "updated_at": workspace.updated_at,
    } for workspace, email in rows]


@router.delete("/workspaces/{workspace_id}", status_code=204)
def delete_empty_workspace(
    workspace_id: uuid.UUID, admin: User = Depends(require_admin), session: Session = Depends(get_session),
) -> None:
    workspace = session.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if _count(session, Project, Project.workspace_id == workspace.id) or _count(session, Task, Task.workspace_id == workspace.id):
        raise HTTPException(status_code=409, detail="Only empty workspaces can be deleted")
    _audit(session, admin, "workspace.deleted", "workspace", workspace.id, name=workspace.name)
    session.delete(workspace)
    session.commit()


@router.get("/devices")
def list_all_devices(
    _: User = Depends(require_admin), session: Session = Depends(get_session),
) -> list[dict[str, object]]:
    rows = session.execute(select(WorkerDevice, User.email).join(User, User.id == WorkerDevice.owner_id).order_by(WorkerDevice.updated_at.desc()).limit(100)).all()
    return [{"id": device.id, "name": device.name, "owner_email": email, "platform": device.platform,
             "version": device.version, "status": device.status.value, "last_seen_at": device.last_seen_at}
            for device, email in rows]


@router.post("/devices/{device_id}/revoke", status_code=204)
def revoke_device(
    device_id: uuid.UUID, admin: User = Depends(require_admin), session: Session = Depends(get_session),
) -> None:
    device = session.get(WorkerDevice, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    device.status = DeviceStatus.REVOKED
    session.execute(update(WorkerJob).where(
        WorkerJob.device_id == device.id,
        WorkerJob.status.in_([WorkerJobStatus.PENDING_APPROVAL, WorkerJobStatus.QUEUED, WorkerJobStatus.STARTING]),
    ).values(status=WorkerJobStatus.CANCELLED, finished_at=datetime.now(timezone.utc)))
    _audit(session, admin, "device.revoked", "device", device.id, name=device.name)
    session.commit()


class AccessSettingsUpdate(BaseModel):
    registration_enabled: bool


@router.get("/settings")
def get_admin_settings(
    _: User = Depends(require_admin), session: Session = Depends(get_session),
) -> dict[str, bool]:
    row = session.get(SystemSetting, "access")
    return {"registration_enabled": True if row is None else bool(row.value_json.get("registration_enabled", True))}


@router.put("/settings")
def update_admin_settings(
    data: AccessSettingsUpdate, admin: User = Depends(require_admin), session: Session = Depends(get_session),
) -> dict[str, bool]:
    row = session.get(SystemSetting, "access")
    if row is None:
        row = SystemSetting(key="access")
        session.add(row)
    row.value_json = {"registration_enabled": data.registration_enabled}
    row.updated_by_id = admin.id
    _audit(session, admin, "access.registration_changed", "system", "access",
           registration_enabled=data.registration_enabled)
    session.commit()
    return {"registration_enabled": data.registration_enabled}


@router.post("/maintenance/cleanup")
def run_cleanup(
    admin: User = Depends(require_admin), session: Session = Depends(get_session),
) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    refresh = session.execute(delete(RefreshToken).where(RefreshToken.expires_at <= now)).rowcount
    sessions = session.execute(delete(AuthSession).where(AuthSession.expires_at <= now)).rowcount
    windows = session.execute(delete(RequestRateWindow).where(RequestRateWindow.window_start < now - timedelta(days=2))).rowcount
    _audit(session, admin, "maintenance.cleanup", "system", "database",
           refresh_tokens_removed=refresh, sessions_removed=sessions, rate_windows_removed=windows)
    session.commit()
    return {"refresh_tokens_removed": refresh, "sessions_removed": sessions, "rate_windows_removed": windows}


@router.get("/audit")
def list_admin_audit(
    limit: int = Query(default=100, ge=1, le=200),
    _: User = Depends(require_admin), session: Session = Depends(get_session),
) -> list[dict[str, object]]:
    rows = session.execute(select(AdminAuditEvent, User.email).outerjoin(User, User.id == AdminAuditEvent.actor_user_id)
                           .order_by(AdminAuditEvent.created_at.desc()).limit(limit)).all()
    return [{"id": event.id, "action": event.action, "target_type": event.target_type,
             "target_id": event.target_id, "detail": event.detail_json,
             "actor_email": email or "Deleted administrator", "created_at": event.created_at}
            for event, email in rows]
