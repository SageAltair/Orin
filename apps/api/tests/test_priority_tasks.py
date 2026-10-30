"""Isolated security and pagination tests for cross-workspace priority inventory."""
import sqlite3
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from orin_api.auth import get_current_user
from orin_api.database import Base, get_session
from orin_api.main import app
from orin_api.models import Task, User


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    engine = create_engine("sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection: sqlite3.Connection, _: object) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with sessions.begin() as session:
        owner = User(email="priority-owner@example.test", password_hash="test-hash", display_name="Owner")
        other = User(email="priority-other@example.test", password_hash="test-hash", display_name="Other")
        session.add_all([owner, other])
        session.flush()
        session.add(Task(owner_id=other.id, title="Other user's private commitment"))

    def override_session() -> Generator[Session, None, None]:
        with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: owner
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_priority_inventory_is_owner_only_and_cross_workspace(client: TestClient) -> None:
    work = client.post("/api/v1/workspaces", json={"name": "Work"}).json()
    personal = client.post("/api/v1/tasks", json={
        "title": "Personal commitment", "due_at": "2026-11-01T12:00:00Z",
    })
    assert personal.status_code == 201
    work_task = client.post("/api/v1/tasks", headers={"X-Orin-Workspace-Id": work["id"]}, json={
        "title": "Team commitment", "priority": "high", "due_at": "2026-10-31T12:00:00Z",
    })
    assert work_task.status_code == 201
    completed = client.post("/api/v1/tasks", json={"title": "Already done", "status": "done"})
    assert completed.status_code == 201

    response = client.get("/api/v1/priority/tasks")
    assert response.status_code == 200
    rows = response.json()
    assert [item["title"] for item in rows] == ["Team commitment", "Personal commitment"]
    assert rows[0]["workspace_id"] == work["id"]
    assert rows[1]["workspace_id"] != work["id"]
    assert all("Other user's" not in item["title"] for item in rows)

    # Existing /tasks behavior is preserved; the new inventory never switches
    # active workspaces or modifies user-owned records.
    scoped = client.get("/api/v1/tasks", headers={"X-Orin-Workspace-Id": work["id"]})
    assert [item["title"] for item in scoped.json()] == ["Team commitment"]


def test_priority_inventory_pagination_and_validation(client: TestClient) -> None:
    for index in range(5):
        response = client.post("/api/v1/tasks", json={
            "title": f"Same deadline {index}", "due_at": "2026-12-01T12:00:00Z",
        })
        assert response.status_code == 201

    full = client.get("/api/v1/priority/tasks").json()
    pages = []
    for offset in (0, 2, 4):
        response = client.get("/api/v1/priority/tasks", params={"limit": 2, "offset": offset})
        assert response.status_code == 200
        pages.extend(response.json())
    assert [row["id"] for row in pages] == [row["id"] for row in full]
    assert len({row["id"] for row in pages}) == 5
    assert client.get("/api/v1/priority/tasks", params={"limit": 101}).status_code == 422
    assert client.get("/api/v1/priority/tasks", params={"offset": -1}).status_code == 422


def test_priority_mode_persists_without_legacy_put_reset(client: TestClient) -> None:
    initial = client.get("/api/v1/users/me/preferences")
    assert initial.status_code == 200
    assert initial.json()["priority_guidance_mode"] == "balanced"

    selected = client.put("/api/v1/users/me/preferences", json={
        "priority_guidance_mode": "planning-only",
    })
    assert selected.status_code == 200
    assert selected.json()["priority_guidance_mode"] == "planning-only"

    # Existing clients do not know this field; unrelated updates retain it.
    legacy = client.put("/api/v1/users/me/preferences", json={})
    assert legacy.status_code == 200
    assert legacy.json()["priority_guidance_mode"] == "planning-only"
    assert client.get("/api/v1/users/me/preferences").json()["priority_guidance_mode"] == "planning-only"
    invalid = client.put("/api/v1/users/me/preferences", json={
        "priority_guidance_mode": "persistent",
    })
    assert invalid.status_code == 422
    assert client.get("/api/v1/users/me/preferences").json()["priority_guidance_mode"] == "planning-only"
