from collections.abc import Generator

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from orin_api.auth import get_current_user
from orin_api.config import Settings, get_settings
from orin_api.database import Base, get_session
from orin_api.main import app
from orin_api.integration_secrets import IntegrationSecretError, decrypt_credential, encrypt_credential, rotate_credential
from orin_api.models import AIProviderConnection, AIUserPolicy, User


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with sessions.begin() as session:
        user = User(email="ai-settings@example.test", password_hash="test-hash", display_name="AI Settings")
        other_user = User(email="ai-other@example.test", password_hash="test-hash", display_name="Other User")
        session.add_all([user, other_user])
        session.flush()

    def override_session() -> Generator[Session, None, None]:
        with sessions() as session:
            yield session

    settings = Settings(_env_file=None, integration_encryption_key=SecretStr(Fernet.generate_key().decode("ascii")))
    app.dependency_overrides[get_session] = override_session
    acting_user = {"value": user}
    app.dependency_overrides[get_current_user] = lambda: acting_user["value"]
    app.dependency_overrides[get_settings] = lambda: settings
    app.state.ai_settings_sessions = sessions
    try:
        with TestClient(app) as test_client:
            test_client.security_context = {"owner": user, "other": other_user, "acting": acting_user}  # type: ignore[attr-defined]
            yield test_client
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_provider_secret_is_masked_and_models_can_be_selected(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    created = client.post("/api/v1/intelligence/providers", json={
        "provider": "openai", "display_name": "My OpenAI", "api_key": "sk-secret-value",
    })
    assert created.status_code == 201
    provider = created.json()
    assert provider["credential_hint"] == "••••alue"
    assert "api_key" not in provider
    with app.state.ai_settings_sessions() as session:
        stored = session.query(AIProviderConnection).one()
        assert "sk-secret-value" not in stored.credential_ciphertext

    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        request = httpx.Request("GET", url)
        assert kwargs["headers"] == {"Authorization": "Bearer sk-secret-value"}
        return httpx.Response(200, request=request, json={"data": [{"id": "gpt-test"}]})

    monkeypatch.setattr(httpx, "get", fake_get)
    discovered = client.post(f"/api/v1/intelligence/providers/{provider['id']}/discover")
    assert discovered.status_code == 200
    model = discovered.json()[0]
    assert model["model_id"] == "gpt-test"
    selected = client.patch(f"/api/v1/intelligence/models/{model['id']}", json={"is_default": True})
    assert selected.status_code == 200
    assert selected.json()["is_default"] is True


def test_google_model_discovery_sends_api_key_in_header_not_url(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    api_key = "google-secret-value"
    created = client.post("/api/v1/intelligence/providers", json={
        "provider": "google", "display_name": "Google", "api_key": api_key,
    })
    assert created.status_code == 201, created.text
    observed: dict[str, object] = {}

    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        observed["url"] = url
        observed["headers"] = kwargs.get("headers")
        observed["params"] = kwargs.get("params")
        request = httpx.Request("GET", url, headers=kwargs.get("headers"))
        return httpx.Response(200, request=request, json={"models": [{"name": "models/gemini-test"}]})

    monkeypatch.setattr(httpx, "get", fake_get)
    response = client.post(f"/api/v1/intelligence/providers/{created.json()['id']}/discover")

    assert response.status_code == 200, response.text
    assert response.json()[0]["model_id"] == "gemini-test"
    assert observed["headers"] == {"x-goog-api-key": api_key}
    assert observed["params"] is None
    assert api_key not in str(observed["url"])


def test_capability_registry_is_authenticated_product_evidence(client: TestClient) -> None:
    response = client.get("/api/v1/intelligence/capabilities")
    assert response.status_code == 200
    payload = response.json()
    assert payload["identity"]["name"] == "Orin"
    assert any(item["name"] == "Ask Orin drawer" for item in payload["screens"])


def test_routing_policy_favorites_usage_and_fallback_are_user_controlled(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    providers = []
    for provider in ("openai", "anthropic"):
        created = client.post("/api/v1/intelligence/providers", json={
            "provider": provider, "display_name": provider.title(), "api_key": f"secret-{provider}",
        }).json()
        providers.append(created)
    models = []
    for connection, model_id in zip(providers, ("primary-test", "fallback-test")):
        model = client.post("/api/v1/intelligence/models", json={
            "connection_id": connection["id"], "model_id": model_id,
        }).json()
        model = client.patch(f"/api/v1/intelligence/models/{model['id']}", json={
            "is_default": model_id == "primary-test", "is_favorite": True,
            "capabilities": {"tools": True, "input_cost_per_million": 1.0, "output_cost_per_million": 2.0},
        }).json()
        assert model["is_favorite"] is True
        models.append(model)
    policy = client.put("/api/v1/intelligence/routing-policy", json={
        "auto_enabled": True, "fallback_model_ids": [models[1]["id"]],
        "task_model_ids": {"command_interpretation": models[0]["id"]}, "monthly_budget_cents": 1000,
    })
    assert policy.status_code == 200, policy.text

    import orin_api.domain_router as domain_router
    from orin_api.ai import AIIntent, AIProviderError
    monkeypatch.setattr(domain_router, "create_provider_from_config", lambda *args, **kwargs: object())
    class FakeInterpreter:
        def __init__(self, provider: object, model: str): self.model = model; self.provider = provider
        def interpret(self, command: str, *, context: str | None = None, images=None) -> AIIntent:
            if self.model == "primary-test": raise AIProviderError("Primary unavailable", category="provider_unavailable")
            return AIIntent.model_validate_json('{"intent":"RESPOND","confidence":0.95,"parameters":{"response":"Fallback answer"}}')
    monkeypatch.setattr(domain_router, "AIInterpreter", FakeInterpreter)
    response = client.post("/api/v1/commands", json={"text": "Help me plan this"})
    assert response.status_code == 200, response.text
    assert response.json()["message"] == "Fallback answer"
    assert "model_notice" not in response.json()["result"]
    usage = client.get("/api/v1/intelligence/usage").json()
    assert usage["requests"] == 2 and usage["failed_requests"] == 1
    assert any(row["fallbacks"] == 1 for row in usage["by_model"])


def test_automatic_routing_silently_recovers_from_quota_with_a_free_model(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    paid_provider = client.post("/api/v1/intelligence/providers", json={
        "provider": "openai", "display_name": "Paid", "api_key": "secret-openai",
    }).json()
    free_provider = client.post("/api/v1/intelligence/providers", json={
        "provider": "openrouter", "display_name": "Free", "api_key": "secret-openrouter",
    }).json()
    paid = client.post("/api/v1/intelligence/models", json={
        "connection_id": paid_provider["id"], "model_id": "paid-model",
    }).json()
    free = client.post("/api/v1/intelligence/models", json={
        "connection_id": free_provider["id"], "model_id": "community-model:free",
    }).json()
    client.patch(f"/api/v1/intelligence/models/{free['id']}", json={
        "capabilities": {"input_cost_per_million": 0, "output_cost_per_million": 0},
    })

    import orin_api.domain_router as domain_router
    from orin_api.ai import AIIntent, AIProviderError
    attempted: list[str] = []
    monkeypatch.setattr(domain_router, "create_provider_from_config", lambda *args, **kwargs: object())

    class FakeInterpreter:
        def __init__(self, provider: object, model: str):
            self.model = model
            self.provider = provider

        def interpret(self, command: str, *, context: str | None = None, images=None) -> AIIntent:
            attempted.append(self.model)
            if self.model == "paid-model":
                raise AIProviderError("Quota exhausted", category="quota_exceeded")
            return AIIntent.model_validate_json('{"intent":"RESPOND","confidence":0.95,"parameters":{"response":"Completed"}}')

    monkeypatch.setattr(domain_router, "AIInterpreter", FakeInterpreter)
    response = client.post("/api/v1/commands", json={
        "text": "Help me", "model_configuration_id": paid["id"],
    })

    assert response.status_code == 200, response.text
    assert response.json()["message"] == "Completed"
    assert "model_notice" not in response.json()["result"]
    assert attempted == ["paid-model", "community-model:free"]
    usage = client.get("/api/v1/intelligence/usage").json()
    assert usage["requests"] == 2
    assert usage["rate_limit_events"] == 1
    assert any(row["model_id"] == "community-model:free" and row["fallbacks"] == 1 for row in usage["by_model"])



def test_routing_policy_first_read_recovers_from_concurrent_insert(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Another request committed the owner row after this request's initial read.
    existing = client.get("/api/v1/intelligence/routing-policy")
    assert existing.status_code == 200, existing.text

    original_get = Session.get
    stale_read_seen = False

    def stale_first_policy_read(session, entity, ident, *args, **kwargs):
        nonlocal stale_read_seen
        if entity is AIUserPolicy and not stale_read_seen:
            stale_read_seen = True
            return None
        return original_get(session, entity, ident, *args, **kwargs)

    monkeypatch.setattr(Session, "get", stale_first_policy_read)
    response = client.get("/api/v1/intelligence/routing-policy")
    assert stale_read_seen
    assert response.status_code == 200, response.text
    assert response.json() == existing.json()

    # The unique-key collision must not poison the surrounding transaction.
    updated = client.put("/api/v1/intelligence/routing-policy", json={
        "auto_enabled": False, "fallback_model_ids": [], "task_model_ids": {},
    })
    assert updated.status_code == 200, updated.text
    assert updated.json()["auto_enabled"] is False

def test_provider_connections_and_models_are_isolated_between_accounts(client: TestClient) -> None:
    context = client.security_context  # type: ignore[attr-defined]
    owner = context["owner"]
    other = context["other"]
    acting = context["acting"]

    created = client.post("/api/v1/intelligence/providers", json={
        "provider": "openai", "display_name": "Owner private provider", "api_key": "owner-secret-value",
    })
    assert created.status_code == 201, created.text
    connection_id = created.json()["id"]
    model = client.post("/api/v1/intelligence/models", json={
        "connection_id": connection_id, "model_id": "owner-private-model",
    })
    assert model.status_code == 201, model.text
    model_id = model.json()["id"]

    # The second account must not discover, update, delete, enumerate or attach
    # models to the first account's provider connection.
    acting["value"] = other
    assert client.get("/api/v1/intelligence/providers").json() == []
    assert client.get("/api/v1/intelligence/models").json() == []
    assert client.post(f"/api/v1/intelligence/providers/{connection_id}/discover").status_code == 404
    assert client.patch(
        f"/api/v1/intelligence/providers/{connection_id}", json={"display_name": "Hijacked"},
    ).status_code == 404
    assert client.delete(f"/api/v1/intelligence/providers/{connection_id}").status_code == 404
    assert client.post("/api/v1/intelligence/models", json={
        "connection_id": connection_id, "model_id": "foreign-model",
    }).status_code == 404
    assert client.patch(
        f"/api/v1/intelligence/models/{model_id}", json={"is_default": True},
    ).status_code == 404
    assert client.put("/api/v1/intelligence/routing-policy", json={
        "fallback_model_ids": [model_id],
    }).status_code == 422

    # Failed foreign operations must not alter the owner's stored resources.
    acting["value"] = owner
    assert [row["id"] for row in client.get("/api/v1/intelligence/providers").json()] == [connection_id]
    assert [row["id"] for row in client.get("/api/v1/intelligence/models").json()] == [model_id]
    assert client.get("/api/v1/intelligence/providers").json()[0]["display_name"] == "Owner private provider"


def test_routing_policy_rejects_another_users_model(client: TestClient) -> None:
    response = client.put("/api/v1/intelligence/routing-policy", json={
        "fallback_model_ids": ["00000000-0000-0000-0000-000000000001"],
    })
    assert response.status_code == 422



def test_cloudflare_account_id_must_be_32_ascii_alphanumeric_characters(
    client: TestClient,
) -> None:
    invalid_ids = (None, "short", "a" * 31, "a" * 33, "a" * 31 + "\x00", "a" * 31 + "é")
    for account_id in invalid_ids:
        payload = {
            "provider": "cloudflare",
            "display_name": "Cloudflare",
            "api_key": "cloudflare-test-token",
            "account_id": account_id,
        }
        response = client.post("/api/v1/intelligence/providers", json=payload)
        assert response.status_code == 422, (account_id, response.text)
        assert response.json()["detail"] == (
            "Cloudflare account ID must be exactly 32 printable ASCII characters."
        )


def test_cloudflare_discovery_uses_validated_account_id_and_never_calls_live_provider(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account_id = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
    created = client.post("/api/v1/intelligence/providers", json={
        "provider": "cloudflare",
        "display_name": "Cloudflare",
        "api_key": "cloudflare-test-token",
        "account_id": account_id,
    })
    assert created.status_code == 201, created.text
    observed: dict[str, object] = {}

    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        observed["url"] = url
        observed["headers"] = kwargs.get("headers")
        request = httpx.Request("GET", url, headers=kwargs.get("headers"))
        return httpx.Response(200, request=request, json={
            "result": [{"id": "@cf/meta/llama-3.1-8b-instruct"}],
        })

    monkeypatch.setattr(httpx, "get", fake_get)
    discovered = client.post(
        f"/api/v1/intelligence/providers/{created.json()['id']}/discover",
    )
    assert discovered.status_code == 200, discovered.text
    assert discovered.json()[0]["model_id"] == "@cf/meta/llama-3.1-8b-instruct"
    assert observed["url"] == (
        f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/models/search"
    )
    assert observed["headers"] == {"Authorization": "Bearer cloudflare-test-token"}


def test_cloudflare_discovery_revalidates_legacy_persisted_account_ids(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = client.post("/api/v1/intelligence/providers", json={
        "provider": "cloudflare",
        "display_name": "Cloudflare",
        "api_key": "cloudflare-test-token",
        "account_id": "a1b2c3d4e5f60718293a4b5c6d7e8f90",
    })
    assert created.status_code == 201, created.text
    with app.state.ai_settings_sessions() as session:
        row = session.query(AIProviderConnection).one()
        row.account_id = "a" * 31 + "\n"
        session.commit()

    def unexpected_provider_call(*_args: object, **_kwargs: object) -> httpx.Response:
        pytest.fail("Invalid persisted account ID must be rejected before any provider request")

    monkeypatch.setattr(httpx, "get", unexpected_provider_call)
    response = client.post(
        f"/api/v1/intelligence/providers/{created.json()['id']}/discover",
    )
    assert response.status_code == 422, response.text



def test_cloudflare_account_id_is_encoded_as_one_url_path_segment(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account_id = "a" * 31 + "/"
    created = client.post("/api/v1/intelligence/providers", json={
        "provider": "cloudflare",
        "display_name": "Cloudflare",
        "api_key": "cloudflare-test-token",
        "account_id": account_id,
    })
    assert created.status_code == 201, created.text
    observed: dict[str, object] = {}

    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        observed["url"] = url
        request = httpx.Request("GET", url, headers=kwargs.get("headers"))
        return httpx.Response(200, request=request, json={"result": []})

    monkeypatch.setattr(httpx, "get", fake_get)
    response = client.post(f"/api/v1/intelligence/providers/{created.json()['id']}/discover")
    assert response.status_code == 200, response.text
    assert observed["url"] == (
        f"https://api.cloudflare.com/client/v4/accounts/{'a' * 31}%2F/ai/models/search"
    )


def test_integration_credential_rotation_uses_current_key_and_keeps_legacy_key_readable() -> None:
    old_key = Fernet.generate_key().decode("ascii")
    current_key = Fernet.generate_key().decode("ascii")
    plaintext = "provider-credential-rotation-sentinel"
    legacy_ciphertext = encrypt_credential(old_key, plaintext)
    keyring = f"{current_key},{old_key}"

    assert decrypt_credential(keyring, legacy_ciphertext) == plaintext
    rotated = rotate_credential(keyring, legacy_ciphertext)

    assert decrypt_credential(current_key, rotated) == plaintext
    assert plaintext not in rotated
    with pytest.raises(IntegrationSecretError):
        decrypt_credential(old_key, rotated)


def test_integration_credential_rotation_rejects_invalid_ciphertext() -> None:
    key = Fernet.generate_key().decode("ascii")
    with pytest.raises(IntegrationSecretError, match="cannot be rotated"):
        rotate_credential(key, "not-a-fernet-token")
