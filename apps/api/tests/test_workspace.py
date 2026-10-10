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
from orin_api.models import TaskDependency, User
from orin_api.config import Settings, get_settings
from orin_api.ai import AIIntent


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with sessions.begin() as session:
        user = User(email="workspace@example.test", password_hash="test-hash", display_name="Workspace")
        session.add(user)
        session.flush()

    def override_session() -> Generator[Session, None, None]:
        with sessions() as session:
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


def _project(client: TestClient, *, name: str = "The Small Voice") -> dict[str, object]:
    response = client.post("/api/v1/projects", json={"name": name, "objective": "Help people grow"})
    assert response.status_code == 201
    return response.json()


def test_project_context_uses_real_task_activity_and_memory_data(client: TestClient) -> None:
    project = _project(client)
    project_id = project["id"]
    client.post("/api/v1/tasks", json={"title": "Prepare presentation cards", "project_id": project_id})
    task = client.post("/api/v1/tasks", json={"title": "Review final cards", "project_id": project_id})
    client.patch(f"/api/v1/tasks/{task.json()['id']}", json={"status": "blocked"})
    saved = client.post("/api/v1/memories", json={"project_id": project_id, "memory_type": "decision", "title": "Database", "content": "Use PostgreSQL for consistency.", "source": "user"})
    assert saved.status_code == 201

    context = client.get(f"/api/v1/projects/{project_id}/context").json()
    assert context["project"]["objective"] == "Help people grow"
    assert context["progress"] == {"completed_tasks": 0, "total_tasks": 2, "percentage": 0}
    assert context["blockers"] == [{"id": task.json()["id"], "title": "Review final cards"}]
    assert context["knowledge"][0]["title"] == "Database"
    assert context["agents"] == [] and context["files"] == []


def test_memory_lifecycle_is_owned_searchable_and_rejects_secret_like_content(client: TestClient) -> None:
    project = _project(client)
    payload = {"memory_type": "preference", "title": "Concise", "content": "Prefer concise summaries.", "source": "user"}
    assert client.post("/api/v1/memories", json={**payload, "content": "api_key=not-a-real-key"}).status_code == 422
    created = client.post("/api/v1/memories", json={**payload, "project_id": project["id"]}).json()
    assert client.get("/api/v1/memories?search=concise").json()[0]["id"] == created["id"]
    archived = client.patch(f"/api/v1/memories/{created['id']}", json={"archived": True})
    assert archived.json()["archived"] is True
    assert client.get("/api/v1/memories").json() == []
    assert client.get("/api/v1/memories?include_archived=true").json()[0]["id"] == created["id"]
    assert client.delete(f"/api/v1/memories/{created['id']}").status_code == 204
    assert client.get(f"/api/v1/memories?project_id={uuid.uuid4()}").status_code == 404


def test_environment_preferences_are_explicit_and_resettable(client: TestClient) -> None:
    saved = client.put("/api/v1/environment/preferences", json={"surface": "navigation", "item": "projects", "visibility": "hidden", "priority": 0})
    assert saved.status_code == 200 and saved.json()["source"] == "explicit"
    assert client.get("/api/v1/environment/preferences").json()[0]["visibility"] == "hidden"
    assert "projects" in client.get("/api/v1/users/me/preferences").json()["hidden_capabilities"]
    assert client.put("/api/v1/environment/preferences", json={"surface": "navigation", "item": "projects", "visibility": "prioritized", "priority": 10}).status_code == 200
    assert "projects" in client.get("/api/v1/users/me/preferences").json()["pinned_capabilities"]
    assert client.delete("/api/v1/environment/preferences").status_code == 204
    assert client.get("/api/v1/environment/preferences").json() == []
    assert client.get("/api/v1/users/me/preferences").json()["visible_capabilities"] == ["activity", "focus", "home", "memories", "projects", "tasks"]


def test_focus_session_is_server_owned_pauseable_and_audited(client: TestClient) -> None:
    project = _project(client)
    response = client.post("/api/v1/focus-sessions", json={"project_id": project["id"], "objective": "Review cards", "duration_minutes": 120})
    assert response.status_code == 201
    focus = response.json()
    assert focus["status"] == "active"
    assert client.patch(f"/api/v1/focus-sessions/{focus['id']}", json={"action": "pause"}).json()["status"] == "paused"
    assert client.patch(f"/api/v1/focus-sessions/{focus['id']}", json={"action": "resume"}).json()["status"] == "active"
    assert client.patch(f"/api/v1/focus-sessions/{focus['id']}", json={"action": "complete"}).json()["status"] == "completed"
    assert client.patch(f"/api/v1/focus-sessions/{focus['id']}", json={"action": "resume"}).status_code == 409
    context = client.get(f"/api/v1/projects/{project['id']}/context").json()
    assert context["active_focus"] is None
    activity = client.get("/api/v1/activity").json()
    assert any("Focus session completed" in entry["summary"] for entry in activity)


def test_project_context_rejects_other_or_missing_project(client: TestClient) -> None:
    assert client.get(f"/api/v1/projects/{uuid.uuid4()}/context").status_code == 404


def test_project_questions_send_only_matching_structured_context_to_ai(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import orin_api.domain_router as domain_router
    project = _project(client)
    client.post("/api/v1/memories", json={"project_id": project["id"], "memory_type": "decision", "title": "Database", "content": "Use PostgreSQL", "source": "user"})
    captured: dict[str, str] = {}
    class FakeInterpreter:
        def __init__(self, provider: object, model: str):
            pass
        def interpret(self, command: str, *, context: str | None = None) -> AIIntent:
            captured["command"] = command
            captured["context"] = context or ""
            return AIIntent.model_validate_json('{"intent":"RESPOND","confidence":0.95,"parameters":{"response":"The project is active."}}')
    monkeypatch.setattr(domain_router, "AIInterpreter", FakeInterpreter)
    app.dependency_overrides[get_settings] = lambda: Settings(ai_provider="openai", ai_model="test", openai_api_key="fake")
    result = client.post("/api/v1/commands", json={"text": "What decisions have we made about The Small Voice?"})
    assert result.status_code == 200
    assert '"name": "The Small Voice"' in captured["context"]
    assert '"content": "Use PostgreSQL"' in captured["context"]
    assert "unrelated" not in captured["context"]


def test_planning_context_includes_live_status_decisions_and_task_dependencies(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import orin_api.domain_router as domain_router
    from orin_api.database import get_session

    project = _project(client, name="Voice Platform")
    complete = client.post("/api/v1/tasks", json={"title": "Approve first story", "project_id": project["id"]}).json()
    blocked = client.post("/api/v1/tasks", json={"title": "Prepare story cards", "project_id": project["id"]}).json()
    next_task = client.post("/api/v1/tasks", json={"title": "Publish reviewed cards", "project_id": project["id"]}).json()
    client.patch(f"/api/v1/tasks/{complete['id']}", json={"status": "done"})
    client.patch(f"/api/v1/tasks/{blocked['id']}", json={"status": "blocked"})
    client.post("/api/v1/memories", json={
        "project_id": project["id"], "memory_type": "decision", "title": "Release scope",
        "content": "Keep the initial release focused on the story library.", "source": "user",
    })
    session_factory = app.dependency_overrides[get_session]
    with next(session_factory()) as session:
        session.add(TaskDependency(task_id=uuid.UUID(next_task["id"]), depends_on_task_id=uuid.UUID(blocked["id"])))
        session.commit()

    captured: dict[str, str] = {}
    class FakeInterpreter:
        def __init__(self, provider: object, model: str):
            pass
        def interpret(self, command: str, *, context: str | None = None) -> AIIntent:
            captured["context"] = context or ""
            return AIIntent.model_validate_json('{"intent":"RESPOND","confidence":0.95,"parameters":{"response":"Use the existing blocker as the next action."}}')
    monkeypatch.setattr(domain_router, "AIInterpreter", FakeInterpreter)
    app.dependency_overrides[get_settings] = lambda: Settings(ai_provider="openai", ai_model="test", openai_api_key="fake")
    response = client.post("/api/v1/commands", json={"text": "Help me plan the Voice Platform workstream"})
    assert response.status_code == 200
    assert "Approve first story" in captured["context"]
    assert '"status": "done"' in captured["context"]
    assert "Prepare story cards" in captured["context"]
    assert "Publish reviewed cards" in captured["context"]
    assert '"task": "Prepare story cards", "status": "blocked"' in captured["context"]
    assert "Keep the initial release focused on the story library" in captured["context"]


def test_unrelated_reasoning_does_not_send_workspace_records_to_the_model(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import orin_api.domain_router as domain_router

    project = _project(client)
    client.post("/api/v1/tasks", json={"title": "Review story library", "project_id": project["id"]})
    captured: dict[str, str] = {}

    class FakeInterpreter:
        def __init__(self, provider: object, model: str):
            pass
        def interpret(self, command: str, *, context: str | None = None) -> AIIntent:
            captured["context"] = context or ""
            return AIIntent.model_validate_json('{"intent":"RESPOND","confidence":0.95,"parameters":{"response":"Photosynthesis converts light energy into chemical energy."}}')

    monkeypatch.setattr(domain_router, "AIInterpreter", FakeInterpreter)
    app.dependency_overrides[get_settings] = lambda: Settings(ai_provider="openai", ai_model="test", openai_api_key="fake")
    response = client.post("/api/v1/commands", json={"text": "Explain photosynthesis in one sentence."})
    assert response.status_code == 200
    assert "Explain photosynthesis" in captured["context"]
    assert "Review story library" not in captured["context"]


def test_planning_uses_stated_workstreams_without_inserting_unrelated_records(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import orin_api.domain_router as domain_router

    unrelated = _project(client, name="Healing")
    client.post("/api/v1/tasks", json={"title": "Call three named contacts", "project_id": unrelated["id"]})
    client.post("/api/v1/tasks", json={"title": "Offline use improvements"})
    captured: dict[str, str] = {}

    class FakeInterpreter:
        def __init__(self, provider: object, model: str):
            pass
        def interpret(self, command: str, *, context: str | None = None) -> AIIntent:
            captured["context"] = context or ""
            return AIIntent.model_validate_json('{"intent":"RESPOND","confidence":0.95,"parameters":{"response":"I will use the six workstreams you named."}}')

    monkeypatch.setattr(domain_router, "AIInterpreter", FakeInterpreter)
    app.dependency_overrides[get_settings] = lambda: Settings(ai_provider="openai", ai_model="test", openai_api_key="fake")
    prompt = "Organize The Small Voice, Orin, AI automation, storytelling videos, income opportunities, and ministry responsibilities into priorities."
    response = client.post("/api/v1/commands", json={"text": prompt})
    assert response.status_code == 200
    assert all(term in captured["context"] for term in ("The Small Voice", "storytelling videos", "ministry responsibilities"))
    assert "Healing" not in captured["context"]
    assert "Call three named contacts" not in captured["context"]
    assert "Offline use improvements" not in captured["context"]


@pytest.mark.parametrize(("command", "intent"), [
    ("Remember that we use PostgreSQL for The Small Voice", '{"intent":"SAVE_MEMORY","confidence":0.95,"parameters":{"memory_type":"decision","memory_title":"Database choice","memory_content":"Use PostgreSQL","project_reference":"The Small Voice"}}'),
    ("I want to work on The Small Voice for two hours", '{"intent":"START_FOCUS","confidence":0.95,"parameters":{"project_reference":"The Small Voice","objective":"Work on the project","duration_minutes":120}}'),
])
def test_explicit_memory_and_focus_commands_update_their_structured_models(client: TestClient, monkeypatch: pytest.MonkeyPatch, command: str, intent: str) -> None:
    import orin_api.domain_router as domain_router
    project = _project(client)
    class FakeInterpreter:
        def __init__(self, provider: object, model: str):
            pass
        def interpret(self, _command: str, *, context: str | None = None) -> AIIntent:
            return AIIntent.model_validate_json(intent)
    monkeypatch.setattr(domain_router, "AIInterpreter", FakeInterpreter)
    app.dependency_overrides[get_settings] = lambda: Settings(ai_provider="openai", ai_model="test", openai_api_key="fake")
    result = client.post("/api/v1/commands", json={"text": command})
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "completed"
    if "Remember" in command:
        memories = client.get(f"/api/v1/memories?project_id={project['id']}").json()
        assert memories[0]["content"] == "Use PostgreSQL"
        assert any("Saved memory" in event["summary"] for event in client.get("/api/v1/activity").json())
    else:
        sessions = client.get("/api/v1/focus-sessions").json()
        assert sessions[0]["project_id"] == project["id"]
        assert sessions[0]["duration_minutes"] == 120


def test_secret_like_ai_memory_is_rejected(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import orin_api.domain_router as domain_router
    _project(client)
    class FakeInterpreter:
        def __init__(self, provider: object, model: str):
            pass
        def interpret(self, _command: str, *, context: str | None = None) -> AIIntent:
            return AIIntent.model_validate_json('{"intent":"SAVE_MEMORY","confidence":0.95,"parameters":{"memory_type":"fact","memory_title":"Key","memory_content":"api_key=not-a-real-value","project_reference":"The Small Voice"}}')
    monkeypatch.setattr(domain_router, "AIInterpreter", FakeInterpreter)
    app.dependency_overrides[get_settings] = lambda: Settings(ai_provider="openai", ai_model="test", openai_api_key="fake")
    result = client.post("/api/v1/commands", json={"text": "Remember this key for The Small Voice"})
    assert result.json()["status"] == "denied"
    assert client.get("/api/v1/memories").json() == []


def test_explicit_hide_tool_command_changes_the_saved_layout(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import orin_api.domain_router as domain_router
    class FakeInterpreter:
        def __init__(self, provider: object, model: str):
            pass
        def interpret(self, _command: str, *, context: str | None = None) -> AIIntent:
            return AIIntent.model_validate_json('{"intent":"SET_TOOL_VISIBILITY","confidence":0.95,"parameters":{"tool":"projects","visibility":"hidden"}}')
    monkeypatch.setattr(domain_router, "AIInterpreter", FakeInterpreter)
    app.dependency_overrides[get_settings] = lambda: Settings(ai_provider="openai", ai_model="test", openai_api_key="fake")
    result = client.post("/api/v1/commands", json={"text": "Hide the Projects tool"})
    assert result.json()["status"] == "completed"
    assert "projects" in client.get("/api/v1/users/me/preferences").json()["hidden_capabilities"]
