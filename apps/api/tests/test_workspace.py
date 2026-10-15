import uuid
from collections.abc import Generator
from datetime import datetime, timedelta, timezone

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
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
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


def test_task_return_points_are_persisted_idempotently_and_hidden_from_other_tasks(client: TestClient) -> None:
    first = client.post("/api/v1/tasks", json={"title": "Prepare the opening scene"}).json()
    second = client.post("/api/v1/tasks", json={"title": "Review the narration"}).json()
    payload = {"accomplished": "Chose the story", "stopped_at": "Drafting the first scene", "next_action": "Write the opening paragraph", "references": "outline.md", "blocker": None, "idempotency_key": "return-point-1"}

    saved = client.post(f"/api/v1/tasks/{first['id']}/return-points", json=payload)
    replay = client.post(f"/api/v1/tasks/{first['id']}/return-points", json=payload)

    assert saved.status_code == 201
    assert replay.status_code == 201
    assert replay.json()["id"] == saved.json()["id"]
    assert client.get(f"/api/v1/tasks/{first['id']}/return-points").json() == [saved.json()]
    assert client.get(f"/api/v1/tasks/{second['id']}/return-points").json() == []
    assert client.post(f"/api/v1/tasks/{first['id']}/return-points", json={**payload, "idempotency_key": "empty", "accomplished": None, "stopped_at": None, "next_action": None, "references": None}).status_code == 422


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


def test_inferred_memory_requires_evidence_and_retrieval_explains_relevance(client: TestClient) -> None:
    invalid = client.post("/api/v1/memories", json={
        "memory_type": "pattern", "title": "Afternoon rescheduling",
        "content": "Tasks scheduled after lunch are often moved.", "source": "inferred", "confidence": 0.8,
    })
    assert invalid.status_code == 422
    created = client.post("/api/v1/memories", json={
        "memory_type": "pattern", "title": "Afternoon rescheduling",
        "content": "Tasks scheduled after lunch are often moved.", "source": "inferred", "confidence": 0.8,
        "evidence": ["Three afternoon tasks were rescheduled"],
    })
    assert created.status_code == 201
    assert created.json()["provenance"] == "inferred"
    context = client.get("/api/v1/memories/context", params={"query": "Why do I often reschedule afternoon tasks?"})
    assert context.status_code == 200
    assert context.json()[0]["id"] == created.json()["id"]
    assert "inferred pattern" in context.json()[0]["reasons"]
    confirmed = client.patch(f"/api/v1/memories/{created.json()['id']}", json={"confirmed": True})
    assert confirmed.json()["provenance"] == "verified"
    assert confirmed.json()["confidence"] == 1.0


def test_proactive_briefing_chooses_one_move_and_reports_recovery_evidence(client: TestClient) -> None:
    project = _project(client, name="Documentary")
    now = datetime.now(timezone.utc)
    dated = client.post("/api/v1/tasks", json={
        "title": "Confirm interview", "project_id": project["id"], "priority": "urgent",
        "due_at": (now - timedelta(days=1)).isoformat(), "first_step": "Open the contact list",
    }).json()
    blocked = client.post("/api/v1/tasks", json={
        "title": "Edit footage", "project_id": project["id"], "status": "blocked",
    }).json()
    briefing = client.get("/api/v1/intelligence/briefing")
    assert briefing.status_code == 200
    payload = briefing.json()
    assert payload["one_move"]["task_id"] == dated["id"]
    assert payload["one_move"]["first_step"] == "Open the contact list"
    assert any(item["kind"] == "recovery" and item["evidence"][0]["task_id"] == dated["id"] for item in payload["findings"])
    assert any(item["kind"] == "blockers" and item["evidence"][0]["task_id"] == blocked["id"] for item in payload["findings"])
    assert payload["scope"]["open_tasks_reviewed"] == 2


def test_environment_preferences_are_explicit_and_resettable(client: TestClient) -> None:
    saved = client.put("/api/v1/environment/preferences", json={"surface": "navigation", "item": "projects", "visibility": "hidden", "priority": 0})
    assert saved.status_code == 200 and saved.json()["source"] == "explicit"
    assert client.get("/api/v1/environment/preferences").json()[0]["visibility"] == "hidden"
    assert "projects" in client.get("/api/v1/users/me/preferences").json()["hidden_capabilities"]


def test_knowledge_documents_versions_links_search_and_exclusion(client: TestClient) -> None:
    idea = client.post("/api/v1/knowledge/documents", json={"title": "Storytelling video idea", "content": "Create Christian storytelling videos.", "document_type": "idea"})
    research = client.post("/api/v1/knowledge/documents", json={"title": "AI assisted storytelling", "content": "Research narrative tools.", "document_type": "research", "exclude_from_ai": True})
    assert idea.status_code == 201 and research.status_code == 201
    idea_id, research_id = idea.json()["id"], research.json()["id"]

    edited = client.patch(f"/api/v1/knowledge/documents/{idea_id}", json={"content": "Plan Christian storytelling videos with a clear audience.", "expected_version": 1})
    assert edited.status_code == 200 and edited.json()["version"] == 2
    assert client.get(f"/api/v1/knowledge/documents/{idea_id}/versions").json()[0]["content"] == "Create Christian storytelling videos."
    assert client.post(f"/api/v1/knowledge/documents/{idea_id}/links", json={"target_id": research_id}).status_code == 201
    assert client.get(f"/api/v1/knowledge/documents/{research_id}/links").json()["backlinks"][0]["id"] == idea_id
    assert client.get("/api/v1/knowledge/documents?q=storytelling").status_code == 200
    search = client.get("/api/v1/search?q=storytelling").json()
    assert any(item["kind"] == "document" and item["result_id"] == idea_id for item in search)
    assert client.patch(f"/api/v1/knowledge/documents/{idea_id}", json={"title": "Stale edit", "expected_version": 1}).status_code == 409
    archived = client.patch(f"/api/v1/knowledge/documents/{idea_id}", json={"archived": True, "expected_version": 2})
    assert archived.json()["archived"] is True
    assert client.get("/api/v1/knowledge/documents").json() == [research.json()]
    assert client.put("/api/v1/environment/preferences", json={"surface": "navigation", "item": "projects", "visibility": "prioritized", "priority": 10}).status_code == 200
    assert "projects" in client.get("/api/v1/users/me/preferences").json()["pinned_capabilities"]
    assert client.delete("/api/v1/environment/preferences").status_code == 204
    assert client.get("/api/v1/environment/preferences").json() == []
    assert client.get("/api/v1/users/me/preferences").json()["visible_capabilities"] == ["activity", "calendar", "focus", "home", "memories", "opportunities", "projects", "tasks"]


def test_knowledge_intelligence_is_evidence_linked_filtered_and_actionable(client: TestClient) -> None:
    included = []
    for index in range(3):
        response = client.post("/api/v1/knowledge/documents", json={"title": f"Storytelling note {index}", "content": "Storytelling for thoughtful communities."})
        assert response.status_code == 201
        included.append(response.json())
    excluded = client.post("/api/v1/knowledge/documents", json={"title": "Private storytelling", "content": "Storytelling excluded text", "exclude_from_ai": True})
    journal = client.post("/api/v1/knowledge/documents", json={"title": "Storytelling journal", "content": "Storytelling personal entry", "document_type": "journal"})
    assert excluded.status_code == journal.status_code == 201

    result = client.post("/api/v1/knowledge/intelligence/evaluate")
    assert result.status_code == 200
    topics = client.get("/api/v1/knowledge/insights").json()
    topic = next(item for item in topics if item["title"] == "Recurring topic: storytelling")
    assert topic["frequency"] == 3
    assert {row["document_id"] for row in topic["evidence"]} == {row["id"] for row in included}
    assert topic["limitations"] and topic["suggested_next_step"]
    assert client.post("/api/v1/knowledge/intelligence/evaluate").json()["insights_created"] == 0

    snoozed = client.patch(f"/api/v1/knowledge/insights/{topic['id']}", json={"action": "snooze"})
    assert snoozed.status_code == 200 and snoozed.json()["status"] == "snoozed"
    assert client.post("/api/v1/knowledge/intelligence/evaluate").status_code == 200
    assert next(row for row in client.get("/api/v1/knowledge/insights").json() if row["id"] == topic["id"])["status"] == "snoozed"
    dismissed = client.patch(f"/api/v1/knowledge/insights/{topic['id']}", json={"action": "dismiss"})
    assert dismissed.status_code == 200 and dismissed.json()["status"] == "dismissed"
    assert all(row["id"] != topic["id"] for row in client.get("/api/v1/knowledge/insights").json())
    assert any(row["id"] == topic["id"] for row in client.get("/api/v1/knowledge/insights?include_dismissed=true").json())


def test_repeated_task_blockers_create_insight_with_task_evidence(client: TestClient) -> None:
    project = _project(client)
    tasks = [client.post("/api/v1/tasks", json={"title": title, "project_id": project["id"]}).json()
             for title in ["Prepare story outline", "Record story narration"]]
    for index, task in enumerate(tasks):
        saved = client.post(f"/api/v1/tasks/{task['id']}/return-points", json={
            "blocker": "Waiting for the shared review materials", "idempotency_key": f"blocker-{index}"})
        assert saved.status_code == 201
    assert client.post("/api/v1/knowledge/intelligence/evaluate").status_code == 200
    insight = next(item for item in client.get("/api/v1/knowledge/insights").json()
                   if item["type"] == "repeated_blocker")
    assert {item["task_id"] for item in insight["evidence"]} == {task["id"] for task in tasks}
    assert "may describe" in insight["explanation"]


def test_knowledge_reviews_are_due_owned_and_persist_actions(client: TestClient) -> None:
    document = client.post("/api/v1/knowledge/documents", json={
        "title": "Resume grant draft", "content": "Next paragraph", "document_type": "draft",
        "status": "developing", "review_at": "2020-01-01T00:00:00Z",
    })
    assert document.status_code == 201
    reviews = client.get("/api/v1/knowledge/reviews").json()
    assert len(reviews) == 1 and reviews[0]["document_id"] == document.json()["id"]
    review = reviews[0]
    snoozed = client.patch(f"/api/v1/knowledge/reviews/{review['id']}", json={"action": "snooze"})
    assert snoozed.status_code == 200 and snoozed.json()["status"] == "snoozed"
    resumed = client.patch(f"/api/v1/knowledge/reviews/{review['id']}", json={"action": "resume"})
    assert resumed.status_code == 200 and resumed.json()["status"] == "pending"
    done = client.patch(f"/api/v1/knowledge/reviews/{review['id']}", json={"action": "resolve"})
    assert done.status_code == 200 and done.json()["status"] == "resolved"
    assert client.get("/api/v1/knowledge/reviews").json() == []
    assert client.patch(f"/api/v1/knowledge/reviews/{uuid.uuid4()}", json={"action": "dismiss"}).status_code == 404


def test_knowledge_ask_retrieves_owned_nonexcluded_sources_with_graceful_fallback(client: TestClient) -> None:
    included = client.post("/api/v1/knowledge/documents", json={"title": "Storytelling research", "content": "AI can support Christian storytelling."}).json()
    client.post("/api/v1/knowledge/documents", json={"title": "Private storytelling", "content": "Private AI storytelling", "exclude_from_ai": True})
    response = client.post("/api/v1/knowledge/ask", json={"question": "Christian storytelling"})
    assert response.status_code == 200
    result = response.json()
    assert result["mode"] == "keyword_only"
    assert result["citations"][0]["document_id"] == included["id"]
    assert all(source["title"] != "Private storytelling" for source in result["sources"])
    assert "not configured" in result["answer"]
    assert client.post("/api/v1/knowledge/ask", json={"question": "nothing matches zzz"}).json()["citations"] == []


def test_knowledge_ask_uses_configured_provider_and_only_accepts_owned_citations(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from orin_api import workspace_router
    from orin_api.config import get_settings

    document = client.post("/api/v1/knowledge/documents", json={"title": "Storytelling notes", "content": "Christian storytelling."}).json()
    class FakeProvider:
        def generate(self, **kwargs: object) -> str:
            return f"The notes mention storytelling. [doc:{document['id']}] [doc:{uuid.uuid4()}]"
    monkeypatch.setattr(workspace_router, "create_provider", lambda settings: FakeProvider())
    app.dependency_overrides[get_settings] = lambda: Settings(ai_provider="openai", ai_model="gpt-4o-mini")

    response = client.post("/api/v1/knowledge/ask", json={"question": "Christian storytelling"})
    assert response.status_code == 200
    result = response.json()
    assert result["mode"] == "ai_synthesis"
    assert len(result["citations"]) == 1 and result["citations"][0]["document_id"] == document["id"]
    assert "[doc:" not in result["answer"].split(" ")[-1]


def test_weekly_knowledge_report_contains_observations_with_evidence(client: TestClient) -> None:
    document = client.post("/api/v1/knowledge/documents", json={"title": "Story outline", "content": "Outline changed this week."}).json()
    excluded = client.post("/api/v1/knowledge/documents", json={"title": "Private journal", "content": "Do not include this", "document_type": "journal"}).json()
    report = client.get("/api/v1/knowledge/reports/weekly")
    assert report.status_code == 200
    report_data = report.json()
    activity = next(item for item in report_data["observations"] if item["kind"] == "activity")
    assert activity["evidence"] == [{"document_id": document["id"], "title": "Story outline"}]
    assert all(row["document_id"] != excluded["id"] for observation in report_data["observations"] for row in observation["evidence"])
    assert report_data["limitations"]


def test_knowledge_report_variants_filter_records_and_keep_evidence(client: TestClient) -> None:
    draft = client.post("/api/v1/knowledge/documents", json={"title": "Story draft", "content": "A story about hope.", "document_type": "draft", "status": "developing"}).json()
    decision = client.post("/api/v1/knowledge/documents", json={"title": "Story format decision", "content": "Use short episodes.", "document_type": "decision"}).json()
    client.post("/api/v1/knowledge/documents", json={"title": "Private journal story", "content": "Story private.", "document_type": "journal"})
    for report_type, source in [("writing", draft), ("decisions", decision), ("topic?topic=hope", draft)]:
        response = client.get(f"/api/v1/knowledge/reports/{report_type}")
        assert response.status_code == 200
        evidence = [item for observation in response.json()["observations"] for item in observation["evidence"]]
        assert any(item["document_id"] == source["id"] for item in evidence)
        assert all("Private journal" not in item["title"] for item in evidence)
    assert client.get("/api/v1/knowledge/reports/topic").status_code == 422
    assert client.get("/api/v1/knowledge/reports/not-a-report").status_code == 404


def test_extraction_queue_is_versioned_idempotent_and_respects_exclusion(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import orin_api.workspace_router as workspace_router

    monkeypatch.setattr(workspace_router, "process_extraction_job", lambda *_: None)
    document = client.post("/api/v1/knowledge/documents", json={"title": "Idea", "content": "A candidate."}).json()
    first = client.post(f"/api/v1/knowledge/documents/{document['id']}/extract")
    duplicate = client.post(f"/api/v1/knowledge/documents/{document['id']}/extract")
    assert first.status_code == duplicate.status_code == 202
    assert first.json()["id"] == duplicate.json()["id"]
    assert client.get(f"/api/v1/knowledge/documents/{document['id']}/extraction").json()["status"] == "queued"
    excluded = client.patch(f"/api/v1/knowledge/documents/{document['id']}", json={"exclude_from_ai": True, "expected_version": 1})
    assert excluded.status_code == 200
    assert client.get(f"/api/v1/knowledge/documents/{document['id']}/extraction").json()["status"] == "excluded"
    assert client.post(f"/api/v1/knowledge/documents/{document['id']}/extract").status_code == 409


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
