"""Private, durable in-app reminders."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from orin_api.auth import get_current_user
from orin_api.database import get_session
from orin_api.models import Notification, User

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@router.get("")
def list_notifications(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[dict]:
    return [{"id": row.id, "title": row.title, "message": row.message, "event_id": row.event_id,
             "due_at": row.due_at, "read_at": row.read_at} for row in session.scalars(
                 select(Notification).where(Notification.user_id == user.id)
                 .order_by(Notification.due_at.desc()).limit(100)).all()]


@router.patch("/{notification_id}/read")
def read_notification(notification_id: uuid.UUID, user: User = Depends(get_current_user),
                      session: Session = Depends(get_session)) -> dict:
    row = session.scalar(select(Notification).where(Notification.id == notification_id, Notification.user_id == user.id))
    if row is None:
        raise HTTPException(status_code=404, detail="Reminder not found")
    row.read_at = row.read_at or datetime.now(timezone.utc)
    session.commit()
    return {"status": "read"}
