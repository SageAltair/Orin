"""Secret-redacted security audit events stored in the existing admin audit ledger."""
from __future__ import annotations

import logging
import uuid

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from orin_api.models import AdminAuditEvent

logger = logging.getLogger("orin_api.security")


def record_security_event(
    session: Session,
    *,
    action: str,
    outcome: str,
    request_id: str | None = None,
    actor_user_id: uuid.UUID | None = None,
    target_type: str = "auth",
    target_id: str | None = None,
    reason: str | None = None,
) -> None:
    """Persist an allowlisted security event without credentials or submitted PII."""
    detail: dict[str, str] = {"outcome": outcome}
    if request_id:
        detail["request_id"] = request_id
    if reason:
        detail["reason"] = reason
    session.add(AdminAuditEvent(
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail_json=detail,
    ))
    try:
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        logger.error(
            "security_event_persist_failed action=%s request_id=%s",
            action,
            request_id or "-",
        )
