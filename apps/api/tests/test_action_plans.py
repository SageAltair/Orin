from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from orin_api.auth import get_current_user
from orin_api.database import Base, get_session
from orin_api.main import app
from orin_api.models import User, UserPreferences


@pytest.fixture
def world() -> Generator[tuple[TestClient, sessionmaker[Session], User], None, None]:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with sessions.begin() as session:
        user = User(email="plans@example.test", password_hash="test-hash", display_name="Plans")
        session.add(user); session.flush(); user_id = user.id
    def override_session() -> Generator[Session, None, None]:
        with sessions() as session: yield session
    app.dependency_overrides[get_session] = override_session
    def current_user() -> User:
        with sessions() as session: return session.get(User, user_id)
    app.dependency_overrides[get_current_user] = current_user
    try:
        with TestClient(app) as client: yield client, sessions, current_user()
    finally:
        app.dependency_overrides.clear(); Base.metadata.drop_all(engine); engine.dispose()


def test_action_plan_preview_rejects_unknown_actions(world) -> None:
    client, _, _ = world
    response = client.post("/api/v1/action-plans/preview", json={"title": "Unsafe", "steps": [
        {"id": "shell", "action": "run_shell", "inputs": {"command": "whoami"}},
    ]})
    assert response.status_code == 200
    assert response.json()["valid"] is False
    assert response.json()["steps"][0]["errors"] == ["Unsupported action"]


def test_cross_module_plan_resolves_dependencies_and_records_history(world) -> None:
    client, _, _ = world
    plan = {"title": "Launch documentary", "steps": [
        {"id": "project", "action": "create_project", "inputs": {"name": "Documentary"}},
        {"id": "task", "action": "create_task", "depends_on": ["project"], "inputs": {
            "title": "Draft treatment", "project_id": {"$from": "project", "path": "id"}}},
    ]}
    preview = client.post("/api/v1/action-plans/preview", json=plan)
    assert preview.status_code == 200 and preview.json()["valid"] is True
    executed = client.post("/api/v1/action-plans/execute", json=plan)
    assert executed.status_code == 200, executed.text
    payload = executed.json()
    assert payload["status"] == "completed" and payload["completed_steps"] == 2
    project_id = payload["steps"][0]["result"]["id"]
    assert payload["steps"][1]["result"]["project_id"] == project_id
    assert client.get("/api/v1/action-plans/history").json()[0]["plan_id"] == payload["plan_id"]


def test_plan_reports_partial_failure_without_claiming_full_success(world) -> None:
    client, _, _ = world
    response = client.post("/api/v1/action-plans/execute", json={"title": "Partial", "stop_on_failure": False, "steps": [
        {"id": "first", "action": "create_task", "inputs": {"title": "Saved"}},
        {"id": "bad", "action": "complete_task", "inputs": {"task_id": "00000000-0000-0000-0000-000000000001"}},
    ]})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "partial_success"
    assert payload["completed_steps"] == 1 and payload["failed_steps"] == 1
    assert payload["steps"][1]["status"] in {"failed", "denied"}


def test_plan_execution_is_idempotent(world) -> None:
    client, _, _ = world
    plan = {"title": "Once", "steps": [{"id": "task", "action": "create_task", "inputs": {"title": "Only once"}}]}
    first = client.post("/api/v1/action-plans/execute", json=plan, headers={"Idempotency-Key": "plan-once"})
    second = client.post("/api/v1/action-plans/execute", json=plan, headers={"Idempotency-Key": "plan-once"})
    assert first.status_code == second.status_code == 200
    assert first.json()["plan_id"] == second.json()["plan_id"]
    assert len([task for task in client.get("/api/v1/tasks").json() if task["title"] == "Only once"]) == 1


def test_plan_pauses_for_approval_and_resumes_remaining_steps(world) -> None:
    client, sessions, _ = world
    client.post("/api/v1/action-plans/preview", json={"title": "Initialize", "steps": [
        {"id": "task", "action": "create_task", "inputs": {"title": "Preview only"}},
    ]})
    with sessions.begin() as session:
        preferences = session.scalar(select(UserPreferences))
        assert preferences is not None
        preferences.autonomy_mode = "conservative"
    plan = {"title": "Approved plan", "steps": [
        {"id": "project", "action": "create_project", "inputs": {"name": "Reviewed project"}},
        {"id": "task", "action": "create_task", "depends_on": ["project"], "inputs": {
            "title": "Reviewed task", "project_id": {"$from": "project", "path": "id"}}},
    ]}
    pending = client.post("/api/v1/action-plans/execute", json=plan).json()
    assert pending["status"] == "awaiting_approval" and pending["completed_steps"] == 0
    approval_id = pending["steps"][0]["approval_id"]
    approved = client.post(f"/api/v1/approvals/{approval_id}/decision", json={"approved": True})
    assert approved.json()["status"] == "completed"
    resumed = client.post(f"/api/v1/action-plans/{pending['plan_id']}/resume").json()
    assert resumed["status"] == "awaiting_approval"
    second_approval = resumed["steps"][1]["approval_id"]
    assert client.post(f"/api/v1/approvals/{second_approval}/decision", json={"approved": True}).json()["status"] == "completed"
    finished = client.post(f"/api/v1/action-plans/{pending['plan_id']}/resume").json()
    assert finished["status"] == "completed" and finished["completed_steps"] == 2


def test_specialists_share_evidence_and_automation_uses_validated_action_plan(world) -> None:
    client, _, _ = world
    project = client.post("/api/v1/projects", json={"name": "Launch"}).json()
    client.post("/api/v1/tasks", json={"title": "Prepare release", "project_id": project["id"]})
    coordinated = client.post("/api/v1/intelligence/specialists/coordinate", json={
        "objective": "Prepare a safe launch", "project_id": project["id"],
        "specialties": ["planning", "risk", "development"],
    })
    assert coordinated.status_code == 200, coordinated.text
    assert len(coordinated.json()["specialists"]) == 3
    assert coordinated.json()["evidence"]["open_tasks"][0]["title"] == "Prepare release"

    created = client.post("/api/v1/intelligence/automations", json={
        "title": "Weekly review", "objective": "Keep the release moving", "cadence": "weekly",
        "plan": {"title": "Review action", "steps": [
            {"id": "task", "action": "create_task", "inputs": {"title": "Review launch progress", "project_id": project["id"]}},
        ]},
    })
    assert created.status_code == 201, created.text
    automation = created.json()
    assert automation["enabled"] is False and automation["preview"]["valid"] is True
    enabled = client.patch(f"/api/v1/intelligence/automations/{automation['id']}", json={"enabled": True}).json()
    assert enabled["next_run_at"] is not None
    executed = client.post(f"/api/v1/intelligence/automations/{automation['id']}/run")
    assert executed.status_code == 200, executed.text
    assert executed.json()["run"]["status"] == "completed"
    assert any(row["title"] == "Review launch progress" for row in client.get("/api/v1/tasks").json())
