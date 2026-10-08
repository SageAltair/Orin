from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from orin_api.auth import REFRESH_COOKIE_NAME
from orin_api.config import get_settings
from orin_api.database import Base, get_session
from orin_api.main import app

PASSWORD = "correct horse battery staple 2026"


@pytest.fixture
def auth_client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("AUTH_SECRET_KEY", "test-auth-signing-key-" + "q" * 64)
    monkeypatch.setenv("AUTH_REFRESH_COOKIE_SECURE", "false")
    monkeypatch.setenv("APP_ENV", "development")
    get_settings.cache_clear()

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_session() -> Generator[Session, None, None]:
        with test_sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()
        get_settings.cache_clear()


def register(client: TestClient, email: str, password: str = PASSWORD) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "display_name": "Test User"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def login(client: TestClient, email: str, password: str = PASSWORD) -> dict[str, object]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def authenticate(client: TestClient, access_token: str) -> None:
    client.headers["Authorization"] = f"Bearer {access_token}"


def test_registration_validation_and_login_errors_never_echo_password(auth_client: TestClient) -> None:
    client = auth_client
    password = "plain text password that must not be echoed"
    rejected = client.post(
        "/api/v1/auth/register",
        json={"email": "invalid", "password": password, "display_name": "Test User"},
    )
    assert rejected.status_code == 422
    assert password not in rejected.text
    assert "input" not in rejected.text
    short_password = "short-password"
    short_password_response = client.post(
        "/api/v1/auth/register",
        json={"email": "valid@example.com", "password": short_password, "display_name": "Test User"},
    )
    assert short_password_response.status_code == 422
    assert short_password not in short_password_response.text

    user = register(client, "Person@Example.com")
    assert "password_hash" not in user
    assert "password" not in user
    assert user["email"] == "person@example.com"

    duplicate = client.post(
        "/api/v1/auth/register",
        json={"email": "PERSON@example.com", "password": password, "display_name": "Another User"},
    )
    assert duplicate.status_code == 409
    assert password not in duplicate.text

    wrong_password = client.post(
        "/api/v1/auth/login",
        json={"email": "person@example.com", "password": password},
    )
    assert wrong_password.status_code == 401
    assert password not in wrong_password.text
    assert wrong_password.json() == {"detail": "Invalid email or password"}
    unknown_email = client.post(
        "/api/v1/auth/login",
        json={"email": "unknown@example.com", "password": password},
    )
    assert unknown_email.status_code == wrong_password.status_code
    assert unknown_email.json() == wrong_password.json()


def test_access_token_requires_auth_and_refresh_rotation_detects_reuse(auth_client: TestClient) -> None:
    client = auth_client
    user = register(client, "person@example.com")
    unauthenticated = client.get("/api/v1/auth/me")
    assert unauthenticated.status_code == 401

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "person@example.com", "password": PASSWORD},
    )
    assert login_response.status_code == 200
    assert login_response.headers["cache-control"] == "no-store"
    access = login_response.json()
    set_cookie = login_response.headers.get("set-cookie", "").lower()
    assert "httponly" in set_cookie
    assert "samesite=strict" in set_cookie
    authenticate(client, str(access["access_token"]))
    assert client.get("/api/v1/auth/me").json()["id"] == user["id"]
    original_refresh = client.cookies.get(REFRESH_COOKIE_NAME)
    assert original_refresh

    rotated = client.post("/api/v1/auth/refresh")
    assert rotated.status_code == 200
    replacement_refresh = client.cookies.get(REFRESH_COOKIE_NAME)
    assert replacement_refresh and replacement_refresh != original_refresh
    authenticate(client, str(rotated.json()["access_token"]))
    assert client.get("/api/v1/auth/me").status_code == 200

    client.cookies.set(REFRESH_COOKIE_NAME, original_refresh, path="/api/v1/auth")
    replay = client.post("/api/v1/auth/refresh")
    assert replay.status_code == 401
    assert client.get("/api/v1/auth/me").status_code == 401


def test_logout_revokes_current_access_and_refresh_tokens(auth_client: TestClient) -> None:
    client = auth_client
    register(client, "person@example.com")
    access = login(client, "person@example.com")
    authenticate(client, str(access["access_token"]))

    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_profile_update_and_password_change_revoke_sessions(auth_client: TestClient) -> None:
    client = auth_client
    register(client, "profile@example.com")
    authenticated = login(client, "profile@example.com")
    authenticate(client, str(authenticated["access_token"]))
    assert client.patch("/api/v1/auth/me", json={"display_name": "Updated Name"}).json()["display_name"] == "Updated Name"
    listed = client.get("/api/v1/auth/sessions")
    assert listed.status_code == 200 and listed.json()[0]["current"] is True
    assert client.post("/api/v1/auth/password", json={"current_password": "wrong password", "new_password": "new password sufficiently long"}).status_code == 400
    changed = client.post("/api/v1/auth/password", json={"current_password": PASSWORD, "new_password": "a new password sufficiently long"})
    assert changed.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "profile@example.com", "password": "a new password sufficiently long"}).status_code == 200


def test_email_change_requires_password_and_invalidates_sessions(auth_client: TestClient) -> None:
    client = auth_client
    register(client, "email-before@example.com")
    token = login(client, "email-before@example.com")
    authenticate(client, str(token["access_token"]))
    assert client.post("/api/v1/auth/email", json={"current_password": "incorrect", "new_email": "email-after@example.com"}).status_code == 400
    changed = client.post("/api/v1/auth/email", json={"current_password": PASSWORD, "new_email": "Email-After@example.com"})
    assert changed.status_code == 200 and changed.json()["email"] == "email-after@example.com"
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "email-after@example.com", "password": PASSWORD}).status_code == 200


def test_user_can_list_and_revoke_another_owned_session(auth_client: TestClient) -> None:
    client = auth_client
    register(client, "sessions@example.com")
    first = login(client, "sessions@example.com")
    second = login(client, "sessions@example.com")
    authenticate(client, str(second["access_token"]))
    sessions = client.get("/api/v1/auth/sessions").json()
    old_session = next(row for row in sessions if not row["current"])
    assert client.delete(f"/api/v1/auth/sessions/{old_session['id']}").status_code == 204
    authenticate(client, str(first["access_token"]))
    assert client.get("/api/v1/auth/me").status_code == 401
    authenticate(client, str(second["access_token"]))
    assert client.get("/api/v1/auth/me").status_code == 200


def test_user_cannot_list_or_modify_another_users_data(auth_client: TestClient) -> None:
    client = auth_client
    first_user = register(client, "first@example.com")
    first_token = login(client, "first@example.com")
    authenticate(client, str(first_token["access_token"]))
    project = client.post("/api/v1/projects", json={"name": "Private project"})
    assert project.status_code == 201
    task = client.post("/api/v1/tasks", json={"title": "Private task", "project_id": project.json()["id"]})
    assert task.status_code == 201

    register(client, "second@example.com")
    second_token = login(client, "second@example.com")
    authenticate(client, str(second_token["access_token"]))

    assert client.get("/api/v1/projects").json() == []
    assert client.get("/api/v1/tasks").json() == []
    assert client.get("/api/v1/activity").json() == []
    # Supplying the first user's ID as a query parameter cannot change the authenticated scope.
    assert client.get(f"/api/v1/projects?user_id={first_user['id']}").json() == []
    assert client.get(f"/api/v1/activity?user_id={first_user['id']}").json() == []
    assert client.patch(f"/api/v1/projects/{project.json()['id']}", json={"name": "Stolen"}).status_code == 404
    assert client.patch(f"/api/v1/tasks/{task.json()['id']}", json={"title": "Stolen"}).status_code == 404
    assert client.post(
        "/api/v1/tasks",
        json={"title": "Cross-user link", "project_id": project.json()["id"]},
    ).status_code == 422
