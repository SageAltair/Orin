"""Deterministic PostgreSQL regression for concurrent first-workspace creation.

The barrier makes both transactions observe an empty workspace list before either
inserts. A uniqueness violation must not abort a legitimate first request.
Only run against the explicitly disposable PostgreSQL test database.
"""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from orin_api.database import Base
from orin_api.models import User
from orin_api.domain_router import ensure_personal_workspace
from orin_api.planning_router import workspace_for_request


@pytest.mark.parametrize("creator", ["domain", "planning"])
@pytest.mark.skipif(
    not os.getenv("ORIN_FOCUS_TEST_DATABASE_URL"),
    reason="requires an isolated PostgreSQL database",
)
def test_concurrent_first_workspace_creation_is_idempotent(creator):
    engine = create_engine(os.environ["ORIN_FOCUS_TEST_DATABASE_URL"])
    Base.metadata.create_all(engine)
    base_sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with base_sessions.begin() as session:
        user = User(
            email=f"workspace-race-{uuid.uuid4()}@example.test",
            display_name="Disposable workspace tester",
            password_hash="fake",
        )
        session.add(user)
        session.flush()
        user_id = user.id

    barrier = Barrier(2)

    class PausingSession(Session):
        def scalar(self, statement, *args, **kwargs):
            result = super().scalar(statement, *args, **kwargs)
            if (
                result is None
                and not self.info.get("workspace_read_paused")
                and "FROM workspaces" in str(statement)
            ):
                self.info["workspace_read_paused"] = True
                barrier.wait(timeout=10)
            return result

    sessions = sessionmaker(bind=engine, class_=PausingSession, expire_on_commit=False)

    def create_first():
        with sessions() as session:
            if creator == "domain":
                workspace = ensure_personal_workspace(session, user_id)
            else:
                workspace = workspace_for_request(session, user, None)
            session.commit()
            return workspace.id

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            workspace_ids = list(pool.map(lambda _: create_first(), range(2)))
        assert workspace_ids[0] == workspace_ids[1]
        with base_sessions() as session:
            from sqlalchemy import select
            from orin_api.models import Workspace
            rows = session.scalars(select(Workspace).where(Workspace.owner_id == user_id)).all()
            assert len(rows) == 1
            assert rows[0].name == "Personal"
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
