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
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with sessions.begin() as session:
        user = User(email="templates@example.test", password_hash="test-hash", display_name="Templates")
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


def test_system_templates_are_contextual_searchable_and_pinnable(client: TestClient) -> None:
    project_templates = client.get("/api/v1/intelligence/templates", params={"page": "projects"})
    assert project_templates.status_code == 200
    titles = {item["title"] for item in project_templates.json()}
    assert {"Plan a New Project", "Project Health Check", "What Am I Missing?"} <= titles
    assert "Review My Writing" not in titles

    health = next(item for item in project_templates.json() if item["title"] == "Project Health Check")
    pinned = client.patch(f"/api/v1/intelligence/templates/{health['id']}", json={"is_pinned": True})
    assert pinned.status_code == 200
    assert pinned.json()["is_pinned"] is True
    assert client.patch(f"/api/v1/intelligence/templates/{health['id']}", json={"prompt": "Replace it"}).status_code == 409
    assert client.delete(f"/api/v1/intelligence/templates/{health['id']}").status_code == 409

    searched = client.get("/api/v1/intelligence/templates", params={"search": "risk"}).json()
    assert any(item["title"] == "Analyze Project Risks" for item in searched)


def test_custom_template_lifecycle(client: TestClient) -> None:
    created = client.post("/api/v1/intelligence/templates", json={
        "title": "Prepare interview", "description": "Build an interview plan", "category": "Research",
        "prompt": "Prepare an interview using the current project context.", "compatible_pages": ["projects"],
    })
    assert created.status_code == 201
    template = created.json()
    assert template["is_system"] is False
    updated = client.patch(f"/api/v1/intelligence/templates/{template['id']}", json={
        "description": "Build a focused interview plan", "is_favorite": True,
    })
    assert updated.status_code == 200
    assert updated.json()["is_favorite"] is True
    assert client.delete(f"/api/v1/intelligence/templates/{template['id']}").status_code == 204
    assert not any(item["id"] == template["id"] for item in client.get("/api/v1/intelligence/templates").json())
