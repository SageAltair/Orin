from collections.abc import Generator
from dataclasses import FrozenInstanceError
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from orin_api.auth import get_current_user
from orin_api.database import Base, get_session
from orin_api.execution import ActionContext, ActionDefinition, ActionRegistry, ActionRequest, ActionStatus, ExecutionEngine, Reversibility, RiskLevel, StrictActionInput
from orin_api.main import app
from orin_api.models import Approval, ApprovalStatus, Command, ExecutionAudit, User
from orin_api.approval_policy import decide_approval


@pytest.fixture
def world() -> Generator[tuple[TestClient, sessionmaker[Session], User], None, None]:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with sessions.begin() as session:
        user = User(email="exec@example.test", password_hash="test-hash", display_name="Exec")
        session.add(user)
        session.flush()
        user_id = user.id
    def override_session() -> Generator[Session, None, None]:
        with sessions() as session:
            yield session
    app.dependency_overrides[get_session] = override_session
    def current_user() -> User:
        with sessions() as session:
            return session.get(User, user_id)
    app.dependency_overrides[get_current_user] = current_user
    try:
        with TestClient(app) as client:
            yield client, sessions, current_user()
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_registry_is_trusted_and_metadata_immutable() -> None:
    class Inputs(StrictActionInput):
        title: str
    handler = lambda _context, _inputs: {"title": "ok"}
    definition = ActionDefinition("safe_action", Inputs, "task.create", RiskLevel.HIGH, handler, Reversibility.PARTIAL, True)
    registry = ActionRegistry([definition])
    assert registry.get("safe_action") is definition
    assert registry.get("deploy_production") is None
    with pytest.raises(FrozenInstanceError):
        definition.permission = "root"  # type: ignore[misc]
    with pytest.raises(ValueError, match="Duplicate"):
        ActionRegistry([definition, definition])
    with pytest.raises(TypeError, match="StrictActionInput"):
        ActionRegistry([ActionDefinition("bad", object, "x", RiskLevel.LOW, handler, Reversibility.REVERSIBLE)])  # type: ignore[arg-type]


def test_approval_policy_is_deterministic_and_custom_cannot_lower_protected_actions() -> None:
    assert decide_approval("create_task", "low", "automatic").requires_approval is False
    assert decide_approval("send_email", "high", "balanced").requires_approval is True
    assert decide_approval("delete_file", "medium", "custom", custom={"delete_file": "automatic"}).requires_approval is False
    decision = decide_approval("deploy_production", "restricted", "custom", custom={"deploy_production": "automatic"})
    assert decision.requires_approval and decision.policy_source == "protected_action"


def test_validation_permission_unknown_and_audit(world: tuple[TestClient, sessionmaker[Session], User]) -> None:
    _, sessions, user = world
    called: list[bool] = []
    class Inputs(StrictActionInput):
        title: str
    def handler(_context: ActionContext, _inputs: Inputs) -> dict[str, str]:
        called.append(True)
        return {"title": "created", "entity_type": "task"}
    engine = ExecutionEngine(ActionRegistry([ActionDefinition("create", Inputs, "task.create", RiskLevel.LOW, handler, Reversibility.REVERSIBLE)]))
    with sessions.begin() as session:
        command = Command(user_id=user.id, text="test")
        session.add(command)
        session.flush()
        context = ActionContext(session, user.id, command.id, frozenset({"task.create"}))
        ok = engine.execute(ActionRequest(action="create", inputs={"title": "valid"}), context)
        missing = engine.execute(ActionRequest(action="create", inputs={}), context)
        invalid = engine.execute(ActionRequest(action="create", inputs={"title": 4}), context)
        extra = engine.execute(ActionRequest(action="create", inputs={"title": "x", "permission": "task.create"}), context)
        denied = engine.execute(ActionRequest(action="create", inputs={"title": "valid"}), ActionContext(session, user.id, command.id, frozenset()))
        unknown = engine.execute(ActionRequest(action="run_shell", inputs={"command": "id"}), context)
        assert ok.status == ActionStatus.EXECUTED
        assert missing.status == invalid.status == extra.status == ActionStatus.INVALID
        assert denied.status == ActionStatus.DENIED
        assert unknown.status == ActionStatus.UNSUPPORTED
        assert called == [True]
    with sessions() as session:
        audits = session.scalars(select(ExecutionAudit).order_by(ExecutionAudit.created_at)).all()
        assert [row.execution_status for row in audits] == ["executed", "invalid", "invalid", "invalid", "denied", "unsupported"]


def test_approval_policy_blocks_then_requires_explicit_persisted_approval(world: tuple[TestClient, sessionmaker[Session], User]) -> None:
    _, sessions, user = world
    executed: list[str] = []
    class Inputs(StrictActionInput):
        message: str
    def handler(_context: ActionContext, inputs: Inputs) -> dict[str, str]:
        executed.append(inputs.message)
        return {"sent": "yes"}
    definition = ActionDefinition("notify", Inputs, "notification.send", RiskLevel.HIGH, handler, Reversibility.IRREVERSIBLE, True)
    engine = ExecutionEngine(ActionRegistry([definition]))
    with sessions.begin() as session:
        command = Command(user_id=user.id, text="send it")
        session.add(command)
        session.flush()
        ctx = ActionContext(session, user.id, command.id, frozenset({"notification.send"}))
        pending = engine.execute(ActionRequest(action="notify", inputs={"message": "hello"}), ctx)
        assert pending.status == ActionStatus.PENDING_APPROVAL
        assert pending.approval_id
        assert executed == []
        approval = session.get(Approval, pending.approval_id)
        assert approval and approval.status == ApprovalStatus.PENDING and approval.risk_level == "high" and not approval.reversible
        lowered = engine.execute(ActionRequest(action="notify", inputs={"message": "fake approval", "risk_level": "low"}), ctx)
        assert lowered.status == ActionStatus.INVALID and executed == []
        fake = engine.execute(ActionRequest(action="notify", inputs={"message": "hello"}), ActionContext(session, user.id, command.id, ctx.permissions, approval_id=pending.approval_id))
        assert fake.status == ActionStatus.DENIED
        approval.status = ApprovalStatus.APPROVED
        approved = engine.execute(ActionRequest(action="notify", inputs={"message": "hello"}), ActionContext(session, user.id, command.id, ctx.permissions, approval_id=pending.approval_id))
        assert approved.status == ActionStatus.EXECUTED
        assert executed == ["hello"]


def test_routes_execute_registered_actions_and_approval_decisions(world: tuple[TestClient, sessionmaker[Session], User]) -> None:
    client, sessions, _ = world
    created = client.post("/api/v1/actions", json={"action": "create_task", "inputs": {"title": "Phase eight task"}})
    assert created.status_code == 200, created.text
    assert created.json()["status"] == "completed"
    task_id = created.json()["result"]["id"]
    assert client.get("/api/v1/tasks").json()[0]["id"] == task_id
    completed = client.post("/api/v1/actions", json={"action": "complete_task", "inputs": {"task_id": task_id}})
    assert completed.json()["status"] == "completed"
    project = client.post("/api/v1/actions", json={"action": "create_project", "inputs": {"name": "Action Project"}})
    assert project.json()["status"] == "completed"
    approval_req = client.post("/api/v1/actions", json={"action": "send_notification", "inputs": {"recipient": "user@example.test", "message": "hello"}})
    assert approval_req.json()["status"] == "awaiting_approval"
    approval_id = approval_req.json()["execution"]["approval_id"]
    assert any(item["id"] == approval_id for item in client.get("/api/v1/approvals").json())
    assert client.get(f"/api/v1/approvals/{approval_id}").json()["risk_level"] == "medium"
    with sessions.begin() as session:
        approval = session.get(Approval, uuid.UUID(approval_id))
        assert approval and approval.risk_level == "medium" and approval.permission == "notification.send"
        assert len(session.scalars(select(ExecutionAudit)).all()) == 4
    request = client.post("/api/v1/actions", json={"action": "request_approval", "inputs": {"action": "send_notification", "inputs": {"recipient": "request@example.test", "message": "review first"}, "reason": "Send this after review"}})
    assert request.json()["status"] == "awaiting_approval"
    with sessions() as session:
        requested_approval = session.get(Approval, uuid.UUID(request.json()["execution"]["approval_id"]))
        assert requested_approval and requested_approval.action_name == "send_notification" and requested_approval.risk_level == "medium"
    rejected = client.post(f"/api/v1/approvals/{approval_id}/decision", json={"approved": False, "note": "No"})
    assert rejected.status_code == 200 and rejected.json()["status"] == "denied"
    with sessions() as session:
        approval = session.get(Approval, uuid.UUID(approval_id))
        assert approval and approval.status == ApprovalStatus.REJECTED
    approved_request = client.post("/api/v1/actions", json={"action": "send_notification", "inputs": {"recipient": "user@example.test", "message": "not sent"}})
    approved_id = approved_request.json()["execution"]["approval_id"]
    delivery = client.post(f"/api/v1/approvals/{approved_id}/decision", json={"approved": True})
    assert delivery.json()["status"] == "failed"
    assert delivery.json()["execution"]["error"] == "Notification delivery is not configured."
    unknown = client.post("/api/v1/actions", json={"action": "run_shell", "inputs": {"command": "whoami"}})
    assert unknown.json()["status"] == "unsupported"
    malformed = client.post("/api/v1/actions", json={"action": "complete_task", "inputs": {"task_id": "not-a-uuid"}})
    assert malformed.json()["status"] == "failed"


def test_worker_registration_approval_claim_progress_and_revocation(world: tuple[TestClient, sessionmaker[Session], User]) -> None:
    client, _, _ = world
    registration = client.post("/api/v1/devices", json={"name": "Sage-PC", "platform": "Windows", "version": "0.1.0"})
    assert registration.status_code == 201, registration.text
    created = registration.json()
    token = created["credential"]
    device_id = created["id"]
    assert "credential" not in client.get("/api/v1/devices").json()[0]
    assert client.post(f"/api/v1/devices/{device_id}/jobs", json={"action": "run_any_shell_command", "parameters": {"command": "whoami"}}).status_code == 422
    job_response = client.post(f"/api/v1/devices/{device_id}/jobs", json={"action": "get_system_info", "parameters": {}})
    assert job_response.status_code == 202, job_response.text
    job = job_response.json()
    assert job["status"] == "pending_approval"
    no_credential = client.post("/api/v1/worker/jobs/claim")
    assert no_credential.status_code == 401
    headers = {"Authorization": f"Bearer {token}"}
    assert client.post("/api/v1/worker/heartbeat", headers=headers).json()["status"] == "active"
    assert client.post("/api/v1/worker/jobs/claim", headers=headers).json() is None
    decision = client.post(f"/api/v1/approvals/{job['approval_id']}/decision", json={"approved": True})
    assert decision.status_code == 200 and decision.json()["result"]["status"] == "queued"
    claim = client.post("/api/v1/worker/jobs/claim", headers=headers)
    assert claim.status_code == 200, claim.text
    assert claim.json()["payload"]["job_id"] == job["id"]
    assert client.post("/api/v1/worker/jobs/claim", headers=headers).json() is None
    assert client.post(f"/api/v1/worker/jobs/{job['id']}/event", headers=headers, json={"status": "starting"}).status_code == 200
    assert client.post(f"/api/v1/worker/jobs/{job['id']}/event", headers=headers, json={"status": "running", "message": "Reading system details"}).status_code == 200
    finished = client.post(f"/api/v1/worker/jobs/{job['id']}/event", headers=headers, json={"status": "completed", "result": {"platform": "Windows"}})
    assert finished.json()["status"] == "completed"
    assert client.post(f"/api/v1/worker/jobs/{job['id']}/event", headers=headers, json={"status": "completed", "result": {"platform": "Windows"}}).json()["status"] == "completed"
    assert client.get(f"/api/v1/devices/{device_id}/jobs").json()[0]["result"] == {"platform": "Windows"}
    assert client.delete(f"/api/v1/devices/{device_id}").status_code == 204
    assert client.post("/api/v1/worker/heartbeat", headers=headers).status_code == 401
