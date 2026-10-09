import uuid
import sqlite3
import json
from pathlib import Path
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from orin_api.auth import get_current_user
from orin_api.ai import AIIntent, AIProviderError
from orin_api.config import Settings, get_settings
from orin_api.domain_router import AIInterpreter
from orin_api.database import Base, get_session
from orin_api.main import app
from orin_api.models import Command, User


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection: sqlite3.Connection, _: object) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

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


def test_activity_filter_and_detail_are_user_scoped(client: TestClient) -> None:
    project = client.post("/api/v1/projects", json={"name": "Activity project"}).json()
    rows = client.get("/api/v1/activity", params={"project_id": project["id"]})
    assert rows.status_code == 200
    assert len(rows.json()) == 1
    event = rows.json()[0]
    assert event["activity_type"] == "project_created"
    assert event["severity"] == "info"
    assert event["metadata"] == {}
    assert client.get(f"/api/v1/activity/{event['id']}").json()["id"] == event["id"]
    assert client.get(f"/api/v1/activity/{uuid.uuid4()}").status_code == 404
    assert client.get("/api/v1/activity", params={"since": "2026-01-02T00:00:00Z", "until": "2026-01-01T00:00:00Z"}).status_code == 422


def test_command_history_returns_only_owned_persisted_requests(client: TestClient) -> None:
    session_factory = app.dependency_overrides[get_session]
    # The test fixture's session override shares the same in-memory database.
    with next(session_factory()) as session:
        owner = session.query(User).filter_by(email="morgan@example.test").one()
        other = User(email="other@example.test", password_hash="test-hash", display_name="Other")
        session.add(other)
        session.flush()
        session.add_all([
            Command(user_id=owner.id, text="My request", response_message="My answer"),
            Command(user_id=other.id, text="Private request", response_message="Private answer"),
        ])
        session.commit()
    response = client.get("/api/v1/commands")
    assert response.status_code == 200
    assert [item["text"] for item in response.json()] == ["My request"]
    assert response.json()[0]["message"] == "My answer"


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

        def interpret(self, command: str, *, context: str | None = None) -> AIIntent:
            return AIIntent.model_validate_json('{"intent":"CREATE_TASK","confidence":0.9,"parameters":{"title":"Call John"}}')

    monkeypatch.setattr(domain_router, "AIInterpreter", FakeInterpreter)
    app.dependency_overrides[get_settings] = lambda: Settings(ai_provider="openai", ai_model="test", openai_api_key="fake")
    response = client.post("/api/v1/commands", json={"text": "Remind me to call John"})
    assert response.status_code == 200
    assert response.json()["intent"] == "CREATE_TASK"
    assert response.json()["result"]["title"] == "Call John"
    assert client.get("/api/v1/tasks").json()[0]["title"] == "Call John"
    timeline = client.get("/api/v1/activity", params={"command_id": response.json()["command_id"]}).json()
    assert {item["activity_type"] for item in timeline} >= {
        "command_received", "intent_interpreted", "plan_created", "policy_decision", "command_completed"}


def test_greeting_command_returns_safe_conversation_without_creating_work(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import orin_api.domain_router as domain_router

    class FakeInterpreter:
        def __init__(self, provider: object, model: str):
            pass

        def interpret(self, command: str, *, context: str | None = None) -> AIIntent:
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
    event_types = {row["activity_type"] for row in client.get("/api/v1/activity", params={"command_id": response.json()["command_id"]}).json()}
    assert event_types == {"command_received", "intent_interpreted", "command_completed"}


def test_original_planning_request_uses_general_reasoning_and_existing_workspace_records(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json
    import orin_api.domain_router as domain_router

    client.post("/api/v1/projects", json={"name": "The Small Voice", "description": "Storytelling platform"})
    client.post("/api/v1/projects", json={"name": "Orin", "description": "Personal operating system"})
    captured: dict[str, str] = {}

    class PlanningProvider:
        def structured_output(self, **kwargs: object) -> str:
            captured["system"] = str(kwargs["system"])
            captured["user"] = str(kwargs["user"])
            return json.dumps({"intent": "RESPOND", "confidence": 0.96, "parameters": {
                "response": "## Overview\n\nStart with a provisional sequence.\n\n| Project | Desired outcome | Next action | Dependencies | Priority |\n|---|---|---|---|---|\n| The Small Voice | A clearer platform | Identify its largest unresolved issue | None known | 2 |\n| Orin | A useful release | Define the smallest release | None known | 3 |\n\nWhat fixed ministry commitments and weekly hours should I protect?"
            }})

    monkeypatch.setattr(domain_router, "create_provider", lambda settings: PlanningProvider())
    app.dependency_overrides[get_settings] = lambda: Settings(ai_provider="openai", ai_model="test", openai_api_key="fake")
    prompt = "I need to improve The Small Voice, finish Orin, learn AI automation, create Christian storytelling videos, find income opportunities, and stay consistent with my ministry responsibilities. I feel like there are too many things competing for my attention. Organize these into projects, desired outcomes, next actions, dependencies, and a realistic priority order. Do not invent deadlines. Identify what information you still need from me."
    response = client.post("/api/v1/commands", json={"text": prompt})
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "completed"
    assert result["intent"] == "RESPOND"
    answer = result["result"]["response"]
    assert "| Project | Desired outcome |" in answer
    assert "What fixed ministry commitments" in answer
    assert "not supported" not in answer.lower()
    assert "The Small Voice" in captured["user"] and "Orin" in captured["user"]
    assert "Otherwise use UNSUPPORTED" not in captured["system"]
    assert client.get("/api/v1/projects").json() and client.get("/api/v1/tasks").json() == []


def test_genuine_unsupported_operation_explains_limitation_and_alternative(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import orin_api.domain_router as domain_router

    class FakeInterpreter:
        def __init__(self, provider: object, model: str):
            pass

        def interpret(self, command: str, *, context: str | None = None) -> AIIntent:
            return AIIntent.model_validate_json('{"intent":"UNSUPPORTED","confidence":0.95,"parameters":{"response":"Orin has no travel booking integration. I can help compare options and prepare an itinerary for you to book."}}')

    monkeypatch.setattr(domain_router, "AIInterpreter", FakeInterpreter)
    app.dependency_overrides[get_settings] = lambda: Settings(ai_provider="openai", ai_model="test", openai_api_key="fake")
    result = client.post("/api/v1/commands", json={"text": "Book my flights"})
    assert result.status_code == 200
    assert result.json()["status"] == "unsupported"
    assert "no travel booking integration" in result.json()["result"]["response"]
    assert "prepare an itinerary" in result.json()["message"]


def test_work_session_preserves_objective_pending_question_and_short_answer(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import orin_api.domain_router as domain_router
    contexts: list[str] = []

    class FakeInterpreter:
        def __init__(self, provider: object, model: str):
            pass

        def interpret(self, command: str, *, context: str | None = None) -> AIIntent:
            contexts.append(context or "")
            response = "How much time can you allocate to ministry work and other projects?" if len(contexts) == 1 else "I will use those as allocations, not assume they are today's availability."
            return AIIntent.model_validate_json('{"intent":"RESPOND","confidence":0.95,"parameters":{"response":' + json.dumps(response) + '}}')

    monkeypatch.setattr(domain_router, "AIInterpreter", FakeInterpreter)
    app.dependency_overrides[get_settings] = lambda: Settings(ai_provider="openai", ai_model="test", openai_api_key="fake")
    first = client.post("/api/v1/commands", json={"text": "Organize The Small Voice, Orin, AI automation, videos, income, and ministry."})
    assert first.status_code == 200
    conversation_id = first.json()["conversation_id"]
    second = client.post("/api/v1/commands", json={"text": "3 hours in ministry related work, and 4 on other projects.", "conversation_id": conversation_id})
    assert second.status_code == 200
    assert second.json()["conversation_id"] == conversation_id
    assert "Organize The Small Voice" in contexts[1]
    assert "How much time can you allocate" in contexts[1]
    assert '"status": "pending"' in contexts[1]
    history = client.get(f"/api/v1/commands?conversation_id={conversation_id}").json()
    assert len(history) == 2
    assert history[-1]["text"].startswith("Organize The Small Voice")
    results = client.get("/api/v1/search?q=ministry%20related").json()
    assert len(results) == 1
    assert results[0]["conversation_id"] == conversation_id


def test_attachments_are_private_bounded_and_available_as_model_context(client: TestClient,
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import orin_api.domain_router as domain_router
    captured: dict[str, str] = {}

    class FakeInterpreter:
        def __init__(self, provider: object, model: str):
            pass

        def interpret(self, command: str, *, context: str | None = None) -> AIIntent:
            captured["context"] = context or ""
            return AIIntent.model_validate_json('{"intent":"RESPOND","confidence":0.95,"parameters":{"response":"I reviewed the provided notes."}}')

    monkeypatch.setattr(domain_router, "AIInterpreter", FakeInterpreter)
    settings = Settings(_env_file=None, ai_provider="openai", ai_model="test", openai_api_key="fake",
        attachment_storage_path=str(tmp_path))
    app.dependency_overrides[get_settings] = lambda: settings
    uploaded = client.post("/api/v1/attachments", files=[("files", ("notes.md", b"First line\nSecond line", "text/markdown"))])
    assert uploaded.status_code == 201, uploaded.text
    file = uploaded.json()[0]
    project = client.post("/api/v1/projects", json={"name": "Content project"}).json()
    task = client.post("/api/v1/tasks", json={"title": "Review the notes", "project_id": project["id"]}).json()
    result = client.post("/api/v1/commands", json={"text": "Summarize the attached notes.",
        "attachment_ids": [file["id"]], "project_id": project["id"], "task_id": task["id"]})
    assert result.status_code == 200, result.text
    assert "First line\\nSecond line" in captured["context"]
    conversation_id = result.json()["conversation_id"]
    assert client.get(f"/api/v1/attachments?conversation_id={conversation_id}").json()[0]["filename"] == "notes.md"
    assert client.get(f"/api/v1/attachments/{file['id']}/content").content == b"First line\nSecond line"
    assert client.delete(f"/api/v1/attachments/{file['id']}").status_code == 409
    assert client.post("/api/v1/attachments", files=[("files", ("script.exe", b"bad", "application/octet-stream"))]).status_code == 415

    session_factory = app.dependency_overrides[get_session]
    with next(session_factory()) as session:
        stranger = User(email="stranger@example.test", password_hash="test-hash", display_name="Stranger")
        session.add(stranger)
        session.commit()
    app.dependency_overrides[get_current_user] = lambda: stranger
    assert client.get(f"/api/v1/attachments/{file['id']}/content").status_code == 404
    assert client.get(f"/api/v1/attachments?conversation_id={conversation_id}").status_code == 404


def test_workspace_search_returns_matching_task_and_project_records(client: TestClient) -> None:
    project = client.post("/api/v1/projects", json={"name": "Story archive", "objective": "Organize public stories"}).json()
    task = client.post("/api/v1/tasks", json={"title": "Review story archive export", "project_id": project["id"]}).json()
    task_results = client.get("/api/v1/search", params={"q": "archive export"}).json()
    project_results = client.get("/api/v1/search", params={"q": "public stories"}).json()
    assert any(item["kind"] == "task" and item["task_id"] == task["id"] for item in task_results)
    assert any(item["kind"] == "project" and item["project_id"] == project["id"] for item in project_results)


def test_long_work_session_builds_a_structured_continuity_summary(client: TestClient,
    monkeypatch: pytest.MonkeyPatch) -> None:
    import orin_api.domain_router as domain_router
    contexts: list[str] = []

    class SummaryProvider:
        def generate(self, **kwargs: object) -> str:
            return "Decision: use image and video content. Constraint: keep the time allocation as stated."

    class FakeInterpreter:
        def __init__(self, provider: object, model: str):
            self.provider = SummaryProvider()

        def interpret(self, command: str, *, context: str | None = None) -> AIIntent:
            contexts.append(context or "")
            return AIIntent.model_validate_json('{"intent":"RESPOND","confidence":0.95,"parameters":{"response":"Continuing the active objective."}}')

    monkeypatch.setattr(domain_router, "AIInterpreter", FakeInterpreter)
    app.dependency_overrides[get_settings] = lambda: Settings(ai_provider="openai", ai_model="test", openai_api_key="fake")
    response = client.post("/api/v1/commands", json={"text": "Plan a content workflow."})
    conversation_id = response.json()["conversation_id"]
    for index in range(13):
        response = client.post("/api/v1/commands", json={"text": f"Follow-up detail {index}.", "conversation_id": conversation_id})
        assert response.status_code == 200
    conversations = client.get("/api/v1/conversations").json()
    assert conversations[0]["summary"].startswith("Decision: use image and video")
    response = client.post("/api/v1/commands", json={"text": "Continue.", "conversation_id": conversation_id})
    assert response.status_code == 200
    assert "structured_summary" in contexts[-1]
    assert "keep the time allocation as stated" in contexts[-1]


def test_command_idempotency_replays_cached_result_and_rejects_key_reuse(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import orin_api.domain_router as domain_router
    calls = 0

    class FakeInterpreter:
        def __init__(self, provider: object, model: str):
            pass

        def interpret(self, command: str, *, context: str | None = None) -> AIIntent:
            nonlocal calls
            calls += 1
            return AIIntent.model_validate_json('{"intent":"RESPOND","confidence":0.9,"parameters":{"response":"Hello"}}')

    monkeypatch.setattr(domain_router, "AIInterpreter", FakeInterpreter)
    app.dependency_overrides[get_settings] = lambda: Settings(ai_provider="openai", ai_model="test", openai_api_key="fake")
    headers = {"Idempotency-Key": "mobile-request-001"}
    first = client.post("/api/v1/commands", json={"text": "hello"}, headers=headers)
    replay = client.post("/api/v1/commands", json={"text": "hello"}, headers=headers)
    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    assert calls == 1
    assert client.get(f"/api/v1/commands/{first.json()['command_id']}").json() == first.json()
    assert client.get(f"/api/v1/commands/{uuid.uuid4()}").status_code == 404
    assert client.post("/api/v1/commands", json={"text": "different"}, headers=headers).status_code == 409


def test_command_pipeline_never_interprets_without_ai_configuration(client: TestClient) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(ai_provider="", ai_model="")
    response = client.post("/api/v1/commands", json={"text": "create a task"})
    assert response.status_code == 503
    events = client.get("/api/v1/activity").json()
    failure = next(row for row in events if row["activity_type"] == "command_failed")
    command = client.get(f"/api/v1/commands/{failure['command_id']}").json()
    assert command["status"] == "failed"


def test_command_submission_has_a_shared_per_user_rate_limit(client: TestClient) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(ai_provider="", ai_model="")
    for _ in range(20):
        assert client.post("/api/v1/commands", json={"text": "hello"}).status_code == 503
    limited = client.post("/api/v1/commands", json={"text": "hello"})
    assert limited.status_code == 429
    assert 1 <= int(limited.headers["retry-after"]) <= 60


def test_command_pipeline_returns_provider_availability_message(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import orin_api.domain_router as domain_router

    class FailedInterpreter:
        def __init__(self, provider: object, model: str):
            pass

        def interpret(self, command: str, *, context: str | None = None) -> AIIntent:
            raise AIProviderError("The AI provider is temporarily unavailable. Please retry shortly.", category="provider_unavailable")

    monkeypatch.setattr(domain_router, "AIInterpreter", FailedInterpreter)
    app.dependency_overrides[get_settings] = lambda: Settings(
        ai_provider="openai", ai_model="test", openai_api_key="fake"
    )
    response = client.post("/api/v1/commands", json={"text": "How are you?"})
    assert response.status_code == 503
    assert response.json()["detail"] == "The AI provider is temporarily unavailable. Please retry shortly."
    events = client.get("/api/v1/activity").json()
    assert {row["activity_type"] for row in events} == {"command_received", "command_failed"}
    failure = next(row for row in events if row["activity_type"] == "command_failed")
    assert client.get(f"/api/v1/commands/{failure['command_id']}").json()["status"] == "failed"


def test_command_completion_resolves_only_the_users_exact_task_name(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import orin_api.domain_router as domain_router
    from orin_api.models import Task

    task_response = client.post("/api/v1/tasks", json={"title": "Website"})
    assert task_response.status_code == 201

    class FakeInterpreter:
        def __init__(self, provider: object, model: str):
            pass

        def interpret(self, command: str, *, context: str | None = None) -> AIIntent:
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

        def interpret(self, command: str, *, context: str | None = None) -> AIIntent:
            return AIIntent.model_validate_json(
                '{"intent":"COMPLETE_TASK","confidence":0.9,"parameters":{"task_id":"' + str(task_id) + '"}}'
            )

    monkeypatch.setattr(domain_router, "AIInterpreter", FakeInterpreter)
    app.dependency_overrides[get_settings] = lambda: Settings(ai_provider="openai", ai_model="test", openai_api_key="fake")
    response = client.post("/api/v1/commands", json={"text": "complete private task"})
    assert response.status_code == 200
    assert response.json()["status"] == "denied"
    assert response.json()["execution"]["status"] == "denied"
    assert client.get("/api/v1/tasks").json() == []
