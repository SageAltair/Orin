from collections.abc import Generator
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from orin_api.auth import get_current_user
from orin_api.database import Base, get_session
from orin_api.main import app
from orin_api.models import SystemSetting, User, Workspace


@pytest.fixture
def admin_world() -> Generator[tuple[TestClient, sessionmaker[Session], uuid.UUID, uuid.UUID], None, None]:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with sessions.begin() as session:
        admin = User(email="admin@example.test", password_hash="unused", display_name="Admin", is_admin=True)
        member = User(email="member@example.test", password_hash="unused", display_name="Member")
        session.add_all([admin, member]); session.flush()
        session.add(Workspace(owner_id=member.id, name="Editorial"))
        admin_id, member_id = admin.id, member.id
    acting_id = {"value": admin_id}

    def override_session() -> Generator[Session, None, None]:
        with sessions() as session:
            yield session
    def current_user() -> User:
        with sessions() as session:
            user = session.get(User, acting_id["value"])
            assert user is not None
            return user
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = current_user
    try:
        with TestClient(app) as client:
            client.acting_id = acting_id  # type: ignore[attr-defined]
            yield client, sessions, admin_id, member_id
    finally:
        app.dependency_overrides.clear(); Base.metadata.drop_all(engine); engine.dispose()


def test_admin_overview_and_workspace_insight(admin_world) -> None:
    client, _, _, _ = admin_world
    overview = client.get("/api/v1/admin/overview")
    assert overview.status_code == 200
    assert overview.json()["totals"]["users"] == 2
    assert overview.json()["totals"]["workspaces"] == 1
    spaces = client.get("/api/v1/admin/workspaces").json()
    assert spaces[0]["name"] == "Editorial"
    assert "owner_email" in spaces[0]


def test_regular_user_is_denied_and_admin_can_disable_account(admin_world) -> None:
    client, sessions, admin_id, member_id = admin_world
    acting = client.acting_id  # type: ignore[attr-defined]
    acting["value"] = member_id
    assert client.get("/api/v1/admin/overview").status_code == 403
    acting["value"] = admin_id
    response = client.patch(f"/api/v1/admin/users/{member_id}", json={"is_disabled": True})
    assert response.status_code == 200
    with sessions() as session:
        assert session.get(User, member_id).is_disabled is True


def test_admin_cannot_disable_self(admin_world) -> None:
    client, _, admin_id, _ = admin_world
    response = client.patch(f"/api/v1/admin/users/{admin_id}", json={"is_disabled": True})
    assert response.status_code == 409


def test_admin_can_manage_roles_and_registration_policy(admin_world) -> None:
    client, sessions, _, member_id = admin_world
    promoted = client.patch(f"/api/v1/admin/users/{member_id}", json={"is_admin": True})
    assert promoted.status_code == 200
    assert promoted.json()["is_admin"] is True
    closed = client.put("/api/v1/admin/settings", json={"registration_enabled": False})
    assert closed.status_code == 200
    assert client.get("/api/v1/admin/settings").json() == {"registration_enabled": False}
    audit = client.get("/api/v1/admin/audit").json()
    assert audit[0]["action"] == "access.registration_changed"
    with sessions() as session:
        assert session.get(SystemSetting, "access").value_json["registration_enabled"] is False


def test_admin_can_delete_only_empty_workspaces(admin_world) -> None:
    client, sessions, _, member_id = admin_world
    with sessions.begin() as session:
        empty = Workspace(owner_id=member_id, name="Temporary")
        session.add(empty); session.flush(); empty_id = empty.id
    assert client.delete(f"/api/v1/admin/workspaces/{empty_id}").status_code == 204
    with sessions() as session:
        assert session.get(Workspace, empty_id) is None
