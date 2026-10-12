import io
import json
import uuid
import zipfile
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from orin_api.auth import PASSWORD_HASHER, get_current_user
from orin_api.config import Settings, get_settings
from orin_api.database import Base, get_session
from orin_api.main import app
from orin_api.models import CalendarEvent, KnowledgeDocument, Notification, User, Task, Command, CommandStatus


@pytest.fixture
def workspace(tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def constraints(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as session:
        user = User(email="reliability@example.test", display_name="Writer",
                    password_hash=PASSWORD_HASHER.hash("test-account-passphrase"))
        other = User(email="other@example.test", display_name="Other", password_hash="fake")
        session.add_all([user, other]); session.flush()
        foreign = KnowledgeDocument(user_id=other.id, title="Other's private note", content="private",
                                    document_type="quick_note", status="inbox")
        session.add(foreign); session.flush()
        foreign_id = str(foreign.id)
    def sessions():
        with factory() as session:
            yield session
    settings = Settings(_env_file=None, attachment_storage_path=str(tmp_path / "attachments"))
    app.dependency_overrides[get_session] = sessions
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            yield client, factory, user, foreign_id, settings
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_creative_references_are_owned_and_partial_updates_preserve_fields(workspace):
    client, _, _, foreign, _ = workspace
    project = client.post("/api/v1/projects", json={"name": "Manuscript"}).json()
    path = f"/api/v1/creative/projects/{project['id']}"
    for kind in ("cards", "outline"):
        assert client.post(path + "/" + kind, json={"title": "Invalid", "document_id": foreign}).status_code == 404
    assert client.post(path + "/outline", json={"title": "Invalid parent", "parent_id": str(uuid.uuid4())}).status_code == 404
    card = client.post(path + "/cards", json={"title": "Opening", "purpose": "Introduce the conflict"}).json()
    result = client.patch(path + "/cards/" + card["id"], json={"status": "ready", "purpose": None})
    assert result.status_code == 200
    assert result.json()["title"] == "Opening"
    assert result.json()["purpose"] is None
    assert result.json()["status"] == "ready"


def test_excluded_notes_remove_all_derived_evidence_and_journals_are_private(workspace):
    client, _, _, _, _ = workspace
    docs = [client.post("/api/v1/knowledge/documents", json={"title": f"Note {i}", "content": "uniqueprivatetopic"}).json() for i in range(3)]
    client.post("/api/v1/knowledge/intelligence/evaluate")
    assert any("uniqueprivatetopic" in row["title"] for row in client.get("/api/v1/knowledge/insights").json())
    for doc in docs:
        assert client.patch("/api/v1/knowledge/documents/" + doc["id"],
            json={"exclude_from_ai": True, "expected_version": doc["version"]}).status_code == 200
    assert not any("uniqueprivatetopic" in row["title"] for row in client.get("/api/v1/knowledge/insights").json())
    report = client.get("/api/v1/knowledge/reports/weekly").json()
    assert "uniqueprivatetopic" not in json.dumps(report)
    client.post("/api/v1/knowledge/documents", json={"title": "Journal", "content": "journaluniquetoken", "document_type": "journal"})
    assert not client.post("/api/v1/knowledge/ask", json={"question": "journaluniquetoken"}).json()["sources"]


def test_stale_document_update_cannot_overwrite_newer_work(workspace):
    client, _, _, _, _ = workspace
    doc = client.post("/api/v1/knowledge/documents", json={"title": "Draft", "content": "first"}).json()
    assert client.patch("/api/v1/knowledge/documents/" + doc["id"],
        json={"content": "second", "expected_version": doc["version"]}).status_code == 200
    assert client.patch("/api/v1/knowledge/documents/" + doc["id"],
        json={"content": "stale", "expected_version": doc["version"]}).status_code == 409
    assert client.get("/api/v1/knowledge/documents/" + doc["id"]).json()["content"] == "second"


def test_reminders_survive_restart_and_are_delivered_once(workspace, monkeypatch):
    client, factory, user, _, settings = workspace
    from orin_api import background
    monkeypatch.setattr(background, "SessionLocal", factory)
    now = datetime.now(timezone.utc)
    with factory.begin() as session:
        session.add(CalendarEvent(user_id=user.id, title="Writing time", is_all_day=False, timezone="UTC",
            start_at=now + timedelta(minutes=10), end_at=now + timedelta(minutes=40), reminder_minutes=15))
    background.maintenance_tick(settings, now=now)
    background.maintenance_tick(settings, now=now + timedelta(seconds=30))
    items = client.get("/api/v1/notifications").json()
    assert len(items) == 1
    assert items[0]["title"] == "Writing time"
    assert client.patch("/api/v1/notifications/" + items[0]["id"] + "/read").status_code == 200
    assert client.get("/api/v1/notifications").json()[0]["read_at"] is not None


def test_export_contains_owned_content_without_credentials_and_delete_cascades(workspace):
    client, factory, user, _, _ = workspace
    client.post("/api/v1/knowledge/documents", json={"title": "My draft", "content": "portable writing"})
    response = client.get("/api/v1/privacy/export")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as bundle:
        data = bundle.read("account.json").decode()
    assert "portable writing" in data
    assert "Other's private note" not in data
    assert "password_hash" not in data
    assert client.request("DELETE", "/api/v1/privacy/account", json={
        "current_password": "incorrect", "confirmation": "DELETE"}).status_code == 400
    assert client.request("DELETE", "/api/v1/privacy/account", json={
        "current_password": "test-account-passphrase", "confirmation": "DELETE"}).status_code == 204
    with factory() as session:
        assert session.get(User, user.id) is None
        assert not session.scalars(select(KnowledgeDocument).where(KnowledgeDocument.user_id == user.id)).all()


def test_failed_registered_action_rolls_back_partial_mutation(workspace):
    _, factory, user, _, _ = workspace
    from orin_api.execution import ActionContext, ActionDefinition, ActionRegistry, ActionRequest, ExecutionEngine, Reversibility, RiskLevel, StrictActionInput
    def mutate_then_fail(context, _):
        context.session.add(Task(owner_id=user.id, title="Must not persist"))
        context.session.commit()  # Route adapters cannot commit outside the action savepoint.
        raise RuntimeError("failed after mutation")
    engine = ExecutionEngine(ActionRegistry([ActionDefinition("broken", StrictActionInput, "test",
        RiskLevel.LOW, mutate_then_fail, Reversibility.REVERSIBLE)]))
    with factory.begin() as session:
        command = Command(user_id=user.id, text="probe", status=CommandStatus.SUBMITTED)
        session.add(command); session.flush()
        result = engine.execute(ActionRequest(action="broken", inputs={}),
            ActionContext(session, user.id, command.id, frozenset({"test"})))
        assert not result.success
    with factory() as session:
        assert session.scalar(select(Task).where(Task.title == "Must not persist")) is None


def test_login_throttle_is_shared_and_does_not_store_ip(workspace):
    client, _, _, _, _ = workspace
    from orin_api.rate_limit import enforce_auth_limit
    from starlette.requests import Request
    _, factory, _, _, _ = workspace
    with factory() as session:
        request = Request({"type":"http", "client":("192.0.2.20",123)})
        enforce_auth_limit(request, session, route="test", limit=1)
        with pytest.raises(Exception) as error:
            enforce_auth_limit(request, session, route="test", limit=1)
        assert error.value.status_code == 429


def test_idea_archive_restore_and_required_note_fields(workspace):
    client, _, _, _, _ = workspace
    idea = client.post("/api/v1/creative/ideas", json={"text": "A recoverable idea"}).json()
    assert client.patch("/api/v1/creative/ideas/" + idea["id"], json={"status":"archived"}).json()["status"] == "archived"
    assert not client.get("/api/v1/creative/ideas?status=active").json()
    assert client.patch("/api/v1/creative/ideas/" + idea["id"], json={"status":"active"}).json()["status"] == "active"
    doc = client.post("/api/v1/knowledge/documents", json={"title":"A note"}).json()
    assert client.patch("/api/v1/knowledge/documents/" + doc["id"], json={"content":None}).status_code == 422
