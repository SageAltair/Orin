"""Read-only, owner-authorized cross-workspace task inventory for priority planning.

This intentionally excludes shared project members' tasks and does not send
notifications, mutate tasks, or bypass workspace permissions. Clients should
apply the user's visible-workspace policy before rendering suggestions.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from orin_api.auth import get_current_user
from orin_api.database import get_session
from orin_api.models import Task, TaskStatus, User
from orin_api.schemas import TaskRead

router = APIRouter(prefix="/api/v1/priority", tags=["priority"])


@router.get("/tasks", response_model=list[TaskRead])
def list_owner_priority_tasks(
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[Task]:
    """Stable paginated owner-only inventory, including every owned workspace.

    The existing /tasks endpoint remains scoped to the active workspace.
    Explicit owner filtering is mandatory: shared project membership alone
    never authorizes cross-workspace visibility.
    """
    return list(session.scalars(
        select(Task)
        .where(
            Task.owner_id == user.id,
            Task.status.notin_((TaskStatus.DONE, TaskStatus.CANCELLED)),
        )
        .order_by(Task.due_at.asc().nulls_last(), Task.created_at.desc(), Task.id.asc())
        .limit(limit).offset(offset)
    ).all())
