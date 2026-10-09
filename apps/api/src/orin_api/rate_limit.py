"""Database-backed fixed-window limits for high-cost authenticated API routes."""
from datetime import datetime, timedelta, timezone
from typing import NamedTuple
import uuid

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from orin_api.models import RequestRateWindow


class RateLimitResult(NamedTuple):
    allowed: bool
    remaining: int
    retry_after: int


def consume_user_window(session: Session, *, user_id: uuid.UUID, route: str,
                        limit: int = 20, window_seconds: int = 60) -> RateLimitResult:
    """Atomically consume a user allowance; committed separately from command work."""
    now = datetime.now(timezone.utc)
    epoch = int(now.timestamp())
    start = datetime.fromtimestamp(epoch - epoch % window_seconds, tz=timezone.utc)
    dialect = session.bind.dialect.name if session.bind is not None else ""
    insert = pg_insert if dialect == "postgresql" else sqlite_insert if dialect == "sqlite" else None
    if insert is None:
        raise RuntimeError("Request limits require PostgreSQL or SQLite storage")
    table = RequestRateWindow.__table__
    statement = insert(table).values(id=uuid.uuid4(), user_id=user_id, route=route,
        window_start=start, request_count=1)
    statement = statement.on_conflict_do_update(
        index_elements=[table.c.user_id, table.c.route, table.c.window_start],
        set_={"request_count": table.c.request_count + 1},
        where=table.c.request_count < limit,
    ).returning(table.c.request_count)
    count = session.scalar(statement)
    if count is None:
        session.rollback()
        return RateLimitResult(False, 0, max(1, window_seconds - epoch % window_seconds))
    # Bound table growth without running a cleanup query on every request.
    if epoch % window_seconds < 2:
        session.execute(delete(table).where(table.c.window_start < start - timedelta(hours=24)))
    session.commit()
    return RateLimitResult(True, max(0, limit - count), max(1, window_seconds - epoch % window_seconds))
