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
from orin_api.models import AIProviderConnection, User


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with sessions.begin() as session:
        user = User(email="ai-settings@example.test", password_hash="test-hash", display_name="AI Settings")
        session.add(user)
        session.flush()

    def override_session() -> Generator[Session, None, None]:
        with sessions() as session:
            yield session

    settings = Settings(_env_file=None, integration_encryption_key=SecretStr(Fernet.generate_key().decode("ascii")))
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings] = lambda: settings
    app.state.ai_settings_sessions = sessions
    try:
        with TestClient(app) as test_client:
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
    assert "fallback model" in response.json()["result"]["model_notice"].lower()
    usage = client.get("/api/v1/intelligence/usage").json()
    assert usage["requests"] == 2 and usage["failed_requests"] == 1
    assert any(row["fallbacks"] == 1 for row in usage["by_model"])


def test_routing_policy_rejects_another_users_model(client: TestClient) -> None:
    response = client.put("/api/v1/intelligence/routing-policy", json={
        "fallback_model_ids": ["00000000-0000-0000-0000-000000000001"],
    })
    assert response.status_code == 422
