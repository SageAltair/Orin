import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from orin_api.auth import get_current_user
from orin_api.ai import AIIntent, AIProviderError
from orin_api.config import Settings, get_settings
from orin_api.domain_router import AIInterpreter
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


def test_command_pipeline_uses_validated_proposal_and_records_activity(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import orin_api.domain_router as domain_router

    class FakeInterpreter:
        def __init__(self, provider: object, model: str):
            pass

        def interpret(self, command: str) -> AIIntent:
            return AIIntent.model_validate_json('{"intent":"CREATE_TASK","confidence":0.9,"parameters":{"title":"Call John"}}')

    monkeypatch.setattr(domain_router, "AIInterpreter", FakeInterpreter)
    app.dependency_overrides[get_settings] = lambda: Settings(ai_provider="openai", ai_model="test", openai_api_key="fake")
    response = client.post("/api/v1/commands", json={"text": "Remind me to call John"})
    assert response.status_code == 200
    assert response.json()["intent"] == "CREATE_TASK"
    assert response.json()["result"]["title"] == "Call John"
    assert client.get("/api/v1/tasks").json()[0]["title"] == "Call John"


def test_greeting_command_returns_safe_conversation_without_creating_work(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import orin_api.domain_router as domain_router

    class FakeInterpreter:
        def __init__(self, provider: object, model: str):
            pass

        def interpret(self, command: str) -> AIIntent:
            assert command == "hey"
            return AIIntent.model_validate_json(
                '{"intent":"RESPOND","confidence":0.9,"parameters":{"response":"Hey! What can I help you with?"}}'
            )

    monkeypatch.setattr(domain_router, "AIInterpreter", FakeInterpreter)
    app.dependency_overrides[get_settings] = lambda: Settings(ai_provider="openai", ai_model="test", openai_api_key="fake")
    response = client.post("/api/v1/commands", json={"text": "hey"})
    assert response.status_code == 200
    assert response.json()["intent"] == "RESPOND"
    assert response.json()["result"] == {"response": "Hey! What can I help you with?"}
    assert client.get("/api/v1/tasks").json() == []


def test_command_pipeline_never_interprets_without_ai_configuration(client: TestClient) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(ai_provider="", ai_model="")
    response = client.post("/api/v1/commands", json={"text": "create a task"})
    assert response.status_code == 503


def test_command_pipeline_returns_provider_availability_message(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import orin_api.domain_router as domain_router

    class FailedInterpreter:
        def __init__(self, provider: object, model: str):
            pass

        def interpret(self, command: str) -> AIIntent:
            raise AIProviderError("The AI provider is temporarily unavailable. Please retry shortly.", category="provider_unavailable")

    monkeypatch.setattr(domain_router, "AIInterpreter", FailedInterpreter)
    app.dependency_overrides[get_settings] = lambda: Settings(
        ai_provider="openai", ai_model="test", openai_api_key="fake"
    )
    response = client.post("/api/v1/commands", json={"text": "How are you?"})
    assert response.status_code == 503
    assert response.json()["detail"] == "The AI provider is temporarily unavailable. Please retry shortly."


def test_command_completion_resolves_only_the_users_exact_task_name(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import orin_api.domain_router as domain_router
    from orin_api.models import Task

    task_response = client.post("/api/v1/tasks", json={"title": "Website"})
    assert task_response.status_code == 201

    class FakeInterpreter:
        def __init__(self, provider: object, model: str):
            pass

        def interpret(self, command: str) -> AIIntent:
            return AIIntent.model_validate_json(
                '{"intent":"COMPLETE_TASK","confidence":0.9,"parameters":{"task_reference":"Website"}}'
            )

    monkeypatch.setattr(domain_router, "AIInterpreter", FakeInterpreter)
    app.dependency_overrides[get_settings] = lambda: Settings(ai_provider="openai", ai_model="test", openai_api_key="fake")
    response = client.post("/api/v1/commands", json={"text": "Mark the website task as complete"})
    assert response.status_code == 200
    assert response.json()["result"]["status"] == "done"
    assert client.get("/api/v1/tasks").json()[0]["status"] == "done"
    activities = client.get("/api/v1/activity").json()
    activity = next(item for item in activities if item["summary"] == "Completed task: Website")
    assert activity["intent"] == "COMPLETE_TASK"
    assert activity["result_status"] == "succeeded"
    assert activity["command_id"] == response.json()["command_id"]


def test_task_reference_normalization_ignores_conversational_wrappers() -> None:
    from orin_api.domain_router import _normalize_task_reference

    assert _normalize_task_reference("the Website task") == _normalize_task_reference("Website")
    assert _normalize_task_reference('Task called "Website"') == _normalize_task_reference("Website")


def test_command_rejects_task_id_owned_by_another_user(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import orin_api.domain_router as domain_router
    from orin_api.database import get_session
    from orin_api.models import Task, User

    session_override = app.dependency_overrides[get_session]
    with next(session_override()) as session:
        other = User(email="other@example.test", password_hash="test-hash", display_name="Other")
        session.add(other)
        session.flush()
        foreign_task = Task(owner_id=other.id, title="Private task")
        session.add(foreign_task)
        session.commit()
        task_id = foreign_task.id

    class FakeInterpreter:
        def __init__(self, provider: object, model: str):
            pass

        def interpret(self, command: str) -> AIIntent:
            return AIIntent.model_validate_json(
                '{"intent":"COMPLETE_TASK","confidence":0.9,"parameters":{"task_id":"' + str(task_id) + '"}}'
            )

    monkeypatch.setattr(domain_router, "AIInterpreter", FakeInterpreter)
    app.dependency_overrides[get_settings] = lambda: Settings(ai_provider="openai", ai_model="test", openai_api_key="fake")
    response = client.post("/api/v1/commands", json={"text": "complete private task"})
    assert response.status_code == 404
    assert client.get("/api/v1/tasks").json() == []
