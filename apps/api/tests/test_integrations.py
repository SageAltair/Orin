from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from collections.abc import Generator
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from orin_api.auth import get_current_user
from orin_api.config import Settings, get_settings
from orin_api.database import Base, get_session
from orin_api.integration_secrets import IntegrationSecretError, decrypt_credential, encrypt_credential, rotate_credential
from orin_api.integrations import GitHubAppClient, ProviderCredentials
from orin_api.main import app
from orin_api.models import User

_TEST_ENCRYPTION_KEY = Fernet.generate_key().decode("ascii")


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    test_sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with test_sessions.begin() as session:
        user = User(email="integrations@example.test", password_hash="test-hash", display_name="Integration Test")
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


class FakeGitHub:
    from orin_api.integrations import ProviderCapabilities
    capabilities = ProviderCapabilities("github", ("repositories.read", "issues.read", "pull_requests.read"))

    def __init__(self, *, expired_access: bool = False) -> None:
        self.revoked: list[str] = []
        self.expired_access = expired_access

    def exchange_code(self, code: str, callback_url: str) -> ProviderCredentials:
        assert code == "oauth-code"
        assert callback_url.endswith("/callback")
        return ProviderCredentials("access-private", "refresh-private",
            datetime.now(timezone.utc) + (timedelta(seconds=-1) if self.expired_access else timedelta(hours=8)),
            datetime.now(timezone.utc) + timedelta(days=180), ())

    def refresh_credentials(self, refresh_token: str) -> ProviderCredentials:
        assert refresh_token == "refresh-private"
        return ProviderCredentials("access-refreshed", "refresh-rotated",
            datetime.now(timezone.utc) + timedelta(hours=8),
            datetime.now(timezone.utc) + timedelta(days=180), ())

    def revoke(self, access_token: str) -> None:
        self.revoked.append(access_token)

    def account(self, access_token: str) -> dict[str, str]:
        assert access_token in {"access-private", "access-refreshed"}
        return {"id": "123", "login": "orin-test"}

    def list_repositories(self, access_token: str) -> list[dict[str, object]]:
        assert access_token in {"access-private", "access-refreshed"}
        return [{"id": "42", "full_name": "octo/private", "owner": "octo", "name": "private",
                 "private": True, "html_url": "https://github.com/octo/private", "default_branch": "main"}]

    def list_issues(self, access_token: str, owner: str, repository: str) -> list[dict[str, object]]:
        assert access_token in {"access-private", "access-refreshed"}
        return [{"number": 8, "title": "Issue title", "state": "open", "url": "https://github.com/octo/private/issues/8"}]

    def list_pull_requests(self, access_token: str, owner: str, repository: str) -> list[dict[str, object]]:
        assert access_token in {"access-private", "access-refreshed"}
        return [{"number": 9, "title": "Pull title", "state": "open", "url": "https://github.com/octo/private/pull/9", "draft": False}]


def _integration_settings() -> Settings:
    return Settings(_env_file=None, app_env="development", github_app_client_id="client-id",
        github_app_client_secret=SecretStr("client-secret"),
        github_app_callback_url="http://localhost:8100/api/v1/integrations/github/callback",
        integration_encryption_key=SecretStr(_TEST_ENCRYPTION_KEY))


def test_credential_encryption_rejects_tampering() -> None:
    key = Fernet.generate_key().decode("ascii")
    ciphertext = encrypt_credential(key, "private-token")
    assert "private-token" not in ciphertext
    assert decrypt_credential(key, ciphertext) == "private-token"
    with pytest.raises(IntegrationSecretError):
        decrypt_credential(Fernet.generate_key().decode("ascii"), ciphertext)


def test_credential_key_rotation_reads_old_key_and_reencrypts_with_new_key() -> None:
    old_key = Fernet.generate_key().decode("ascii")
    new_key = Fernet.generate_key().decode("ascii")
    ciphertext = encrypt_credential(old_key, "private-token")
    keyring = f"{new_key},{old_key}"
    rotated = rotate_credential(keyring, ciphertext)
    assert decrypt_credential(keyring, rotated) == "private-token"
    with pytest.raises(IntegrationSecretError):
        decrypt_credential(new_key, ciphertext)


def test_github_oauth_repository_context_and_disconnect_are_scoped(client: TestClient, monkeypatch) -> None:
    import orin_api.integration_router as integration_router

    fake = FakeGitHub(expired_access=True)
    monkeypatch.setattr(integration_router, "_provider", lambda _settings: fake)
    app.dependency_overrides[get_settings] = _integration_settings

    begin = client.post("/api/v1/integrations/github/connect")
    assert begin.status_code == 200
    authorization = begin.json()["authorization_url"]
    assert "client_secret" not in authorization
    assert "scope=repo" not in authorization
    state = parse_qs(urlparse(authorization).query)["state"][0]

    callback = client.get("/api/v1/integrations/github/callback", params={"code": "oauth-code", "state": state}, follow_redirects=False)
    assert callback.status_code == 303
    assert "github_connected" in callback.headers["location"]
    assert "access-private" not in callback.headers["location"]

    status_response = client.get("/api/v1/integrations/github")
    assert status_response.status_code == 200
    assert status_response.json()["connected"] is True
    assert status_response.json()["account_login"] == "orin-test"
    assert "credential" not in status_response.text
    assert "access-private" not in status_response.text

    replay = client.get("/api/v1/integrations/github/callback", params={"code": "oauth-code", "state": state})
    assert replay.status_code == 400
    repositories = client.get("/api/v1/integrations/github/repositories")
    assert repositories.status_code == 200
    assert repositories.json()[0]["private"] is True

    project = client.post("/api/v1/projects", json={"name": "GitHub context"}).json()
    selection = client.put(f"/api/v1/integrations/github/projects/{project['id']}/repository",
        json={"provider_resource_id": "42"})
    assert selection.status_code == 200
    context = client.get(f"/api/v1/integrations/github/projects/{project['id']}/issues")
    assert context.status_code == 200
    assert context.json()["issues"][0]["number"] == 8
    assert context.json()["pull_requests"][0]["number"] == 9

    disconnected = client.delete("/api/v1/integrations/github")
    assert disconnected.status_code == 204
    assert fake.revoked == ["access-refreshed"]
    assert client.get("/api/v1/integrations/github").json()["connected"] is False
    assert client.get("/api/v1/activity", params={"event_type": "integration_operation"}).json()


def test_github_connection_fails_safely_when_server_credentials_are_missing(client: TestClient) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    response = client.post("/api/v1/integrations/github/connect")
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]


def test_github_app_adapter_filters_issues_and_uses_fixed_api_origin() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.host in {"api.github.com", "github.com"}
        if request.url.path.endswith("/access_token"):
            assert request.headers["accept"] == "application/json"
            return httpx.Response(200, json={"access_token": "access", "refresh_token": "refresh",
                "expires_in": 28000, "refresh_token_expires_in": 15000000})
        if request.url.path == "/repos/octo/repo/issues":
            return httpx.Response(200, json=[
                {"number": 1, "title": "Issue", "state": "open", "html_url": "https://github.com/octo/repo/issues/1"},
                {"number": 2, "title": "PR from issue endpoint", "state": "open", "pull_request": {}}])
        if request.url.path == "/repos/octo/repo/pulls":
            return httpx.Response(200, json=[{"number": 3, "title": "Pull", "state": "open", "draft": True}])
        raise AssertionError(f"Unexpected provider path: {request.url.path}")

    provider = GitHubAppClient("client-id", "client-secret", transport=httpx.MockTransport(respond))
    credentials = provider.exchange_code("code", "http://localhost/callback")
    assert credentials.access_token == "access"
    assert credentials.refresh_token == "refresh"
    assert credentials.access_expires_at is not None
    assert provider.list_issues("access", "octo", "repo") == [{
        "number": 1, "title": "Issue", "state": "open",
        "url": "https://github.com/octo/repo/issues/1", "updated_at": None, "draft": False}]
    assert provider.list_pull_requests("access", "octo", "repo")[0]["draft"] is True
