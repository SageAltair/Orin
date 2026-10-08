import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from orin_api.auth import get_current_user
from orin_api.database import Base, get_session
from orin_api.main import app
from orin_api.models import User


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with test_sessions.begin() as session:
        user = User(email="morgan@example.test", password_hash="test-hash", display_name="Morgan")
        session.add(user)
        session.flush()

    def override_session() -> Generator[Session, None, None]:
        with test_sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_preferences_and_capabilities_use_relational_assignments(client: TestClient) -> None:
    test_client = client
    assert all(item["granted"] for item in test_client.get("/api/v1/capabilities").json())
    response = test_client.get("/api/v1/users/me/preferences")
    assert response.status_code == 200
    assert response.json()["visible_capabilities"] == ["home", "tasks"]
    assert response.json()["hidden_capabilities"] == ["activity", "projects", "settings"]

    updated = test_client.put(
        "/api/v1/users/me/preferences",
        json={
            "density": "compact",
            "theme": "system",
            "locale": "en-GB",
            "visible_capabilities": ["home", "projects"],
            "pinned_capabilities": ["home"],
        },
    )
    assert updated.status_code == 200
    assert updated.json()["visible_capabilities"] == ["home", "projects"]
    assert updated.json()["pinned_capabilities"] == ["home"]
    project_capability = next(
        item for item in test_client.get("/api/v1/capabilities").json()
        if item["code"] == "projects"
    )
    assert project_capability["visible"] is True


def test_project_task_activity_flow_and_user_scoping(client: TestClient) -> None:
    test_client = client
    invalid_project = test_client.post("/api/v1/projects", json={"name": "   "})
    assert invalid_project.status_code == 422

    project_response = test_client.post(
        "/api/v1/projects",
        json={"name": "Website refresh", "description": "A focused update"},
    )
    assert project_response.status_code == 201
    project = project_response.json()

    task_response = test_client.post(
        "/api/v1/tasks",
        json={"title": "Review the first draft", "project_id": project["id"], "priority": "high"},
    )
    assert task_response.status_code == 201
    task = task_response.json()

    task_update = test_client.patch(
        f"/api/v1/tasks/{task['id']}",
        json={"status": "in_progress"},
    )
    assert task_update.status_code == 200
    assert task_update.json()["status"] == "in_progress"
    assert len(test_client.get("/api/v1/projects?user_id=" + str(uuid.uuid4())).json()) == 1
    assert len(test_client.get("/api/v1/tasks?status=in_progress").json()) == 1

    events = test_client.get("/api/v1/activity")
    assert events.status_code == 200
    assert {event["activity_type"] for event in events.json()} == {"task_updated", "task_created", "project_created"}


def test_preference_rejects_pinning_a_hidden_capability(client: TestClient) -> None:
    test_client = client
    response = test_client.put(
        "/api/v1/users/me/preferences",
        json={
            "visible_capabilities": ["home"],
            "pinned_capabilities": ["home", "tasks"],
        },
    )
    assert response.status_code == 422
