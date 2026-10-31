from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from orin_api.ai import PROVIDER_BASE_URLS, ProviderName
from orin_api.auth import get_current_user
from orin_api.config import Settings, get_settings
from orin_api.database import get_session
from orin_api.integration_secrets import IntegrationSecretError, decrypt_credential, encrypt_credential
from orin_api.models import AIModelConfiguration, AIProviderConnection, AIUsageRecord, AIUserPolicy, User
from orin_api.product_context import product_capabilities

router = APIRouter(prefix="/api/v1/intelligence", tags=["intelligence"])
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=240)]


class ProviderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: ProviderName
    display_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    api_key: Annotated[str, StringConstraints(strip_whitespace=True, min_length=8, max_length=4096)]
    account_id: Annotated[str, StringConstraints(strip_whitespace=True, max_length=160)] | None = None


class ProviderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)] | None = None
    api_key: Annotated[str, StringConstraints(strip_whitespace=True, min_length=8, max_length=4096)] | None = None
    enabled: bool | None = None


class ModelCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())
    connection_id: uuid.UUID
    model_id: Name
    display_name: Name | None = None


class ModelUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool | None = None
    is_default: bool | None = None
    is_favorite: bool | None = None
    capabilities: dict[str, object] | None = None


class RoutingPolicyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    auto_enabled: bool = True
    fallback_model_ids: list[uuid.UUID] = Field(default_factory=list, max_length=10)
    task_model_ids: dict[str, uuid.UUID] = Field(default_factory=dict)
    monthly_budget_cents: int | None = Field(default=None, ge=100, le=10_000_000)
    warning_threshold_percent: int = Field(default=80, ge=1, le=100)


def _encryption_key(settings: Settings) -> str:
    if settings.integration_encryption_key is None:
        raise HTTPException(status_code=503, detail="Secure AI settings require INTEGRATION_ENCRYPTION_KEY.")
    return settings.integration_encryption_key.get_secret_value()


def _provider_read(row: AIProviderConnection) -> dict[str, object]:
    return {"id": row.id, "provider": row.provider, "display_name": row.display_name,
            "credential_hint": row.credential_hint, "account_id": row.account_id, "enabled": row.enabled,
            "verified_at": row.verified_at, "last_test_status": row.last_test_status}


def _model_read(row: AIModelConfiguration, provider: str, provider_enabled: bool = True) -> dict[str, object]:
    return {"id": row.id, "connection_id": row.connection_id, "provider": provider,
            "model_id": row.model_id, "display_name": row.display_name, "enabled": row.enabled,
            "is_default": row.is_default, "is_favorite": row.is_favorite,
            "provider_enabled": provider_enabled, "capabilities": row.capabilities}


def _connection(session: Session, user: User, connection_id: uuid.UUID) -> AIProviderConnection:
    row = session.scalar(select(AIProviderConnection).where(
        AIProviderConnection.id == connection_id, AIProviderConnection.user_id == user.id))
    if row is None:
        raise HTTPException(status_code=404, detail="AI provider connection not found.")
    return row


def _discover(connection: AIProviderConnection, api_key: str) -> list[str]:
    provider = connection.provider
    if provider == "cloudflare":
        if not connection.account_id:
            raise HTTPException(status_code=422, detail="Cloudflare account ID is required.")
        url = f"https://api.cloudflare.com/client/v4/accounts/{connection.account_id}/ai/models/search"
        headers = {"Authorization": f"Bearer {api_key}"}
        params = None
    elif provider == "google":
        url = f"{PROVIDER_BASE_URLS[provider]}/models"
        headers, params = {}, {"key": api_key}
    else:
        url = f"{PROVIDER_BASE_URLS[provider]}/models"
        headers = ({"x-api-key": api_key, "anthropic-version": "2023-06-01"} if provider == "anthropic"
                   else {"Authorization": f"Bearer {api_key}"})
        params = None
    try:
        response = httpx.get(url, headers=headers, params=params, timeout=15.0)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="The provider connection could not be verified.") from exc
    values = payload.get("data") or payload.get("models") or payload.get("result") or []
    discovered: list[str] = []
    for item in values if isinstance(values, list) else []:
        raw = item.get("id") or item.get("name") if isinstance(item, dict) else None
        if isinstance(raw, str):
            value = raw.removeprefix("models/")[:240]
            if value and value not in discovered:
                discovered.append(value)
    return discovered[:500]


@router.get("/capabilities")
def capabilities(_user: User = Depends(get_current_user)) -> dict[str, object]:
    return product_capabilities()


@router.get("/providers")
def list_providers(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[dict[str, object]]:
    rows = session.scalars(select(AIProviderConnection).where(AIProviderConnection.user_id == user.id)
                           .order_by(AIProviderConnection.created_at)).all()
    return [_provider_read(row) for row in rows]


@router.post("/providers", status_code=status.HTTP_201_CREATED)
def create_connection(data: ProviderCreate, user: User = Depends(get_current_user), session: Session = Depends(get_session),
                      settings: Settings = Depends(get_settings)) -> dict[str, object]:
    if data.provider == ProviderName.CLOUDFLARE and not data.account_id:
        raise HTTPException(status_code=422, detail="Cloudflare account ID is required.")
    if session.scalar(select(AIProviderConnection.id).where(
            AIProviderConnection.user_id == user.id, AIProviderConnection.provider == data.provider.value)):
        raise HTTPException(status_code=409, detail="This AI provider is already connected.")
    key = _encryption_key(settings)
    try:
        encrypted = encrypt_credential(key, data.api_key)
    except IntegrationSecretError as exc:
        raise HTTPException(status_code=503, detail="Secure AI settings are unavailable.") from exc
    row = AIProviderConnection(user_id=user.id, provider=data.provider.value, display_name=data.display_name,
                               credential_ciphertext=encrypted, credential_hint=f"••••{data.api_key[-4:]}",
                               account_id=data.account_id)
    session.add(row)
    session.commit()
    session.refresh(row)
    return _provider_read(row)


@router.post("/providers/{connection_id}/discover")
def discover_models(connection_id: uuid.UUID, user: User = Depends(get_current_user), session: Session = Depends(get_session),
                    settings: Settings = Depends(get_settings)) -> list[dict[str, object]]:
    connection = _connection(session, user, connection_id)
    try:
        credential = decrypt_credential(_encryption_key(settings), connection.credential_ciphertext)
    except IntegrationSecretError as exc:
        raise HTTPException(status_code=503, detail="Stored AI credentials cannot be decrypted.") from exc
    model_ids = _discover(connection, credential)
    existing = {row.model_id: row for row in session.scalars(select(AIModelConfiguration).where(
        AIModelConfiguration.connection_id == connection.id)).all()}
    for model_id in model_ids:
        if model_id not in existing:
            session.add(AIModelConfiguration(user_id=user.id, connection_id=connection.id,
                                              model_id=model_id, display_name=model_id, capabilities={}))
    connection.verified_at = datetime.now(timezone.utc)
    connection.last_test_status = "connected"
    session.commit()
    return list_models(user, session)


@router.patch("/providers/{connection_id}")
def update_connection(connection_id: uuid.UUID, data: ProviderUpdate, user: User = Depends(get_current_user),
                      session: Session = Depends(get_session), settings: Settings = Depends(get_settings)) -> dict[str, object]:
    connection = _connection(session, user, connection_id)
    if data.display_name is not None:
        connection.display_name = data.display_name
    if data.enabled is not None:
        connection.enabled = data.enabled
    if data.api_key is not None:
        try:
            connection.credential_ciphertext = encrypt_credential(_encryption_key(settings), data.api_key)
        except IntegrationSecretError as exc:
            raise HTTPException(status_code=503, detail="Secure AI settings are unavailable.") from exc
        connection.credential_hint = f"••••{data.api_key[-4:]}"
        connection.verified_at = None
        connection.last_test_status = None
    session.commit()
    return _provider_read(connection)


@router.delete("/providers/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection(connection_id: uuid.UUID, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> Response:
    connection = _connection(session, user, connection_id)
    session.delete(connection)
    session.commit()
    return Response(status_code=204)


@router.get("/models")
def list_models(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[dict[str, object]]:
    rows = session.execute(select(AIModelConfiguration, AIProviderConnection.provider, AIProviderConnection.enabled).join(
        AIProviderConnection, AIProviderConnection.id == AIModelConfiguration.connection_id).where(
        AIModelConfiguration.user_id == user.id).order_by(AIProviderConnection.provider, AIModelConfiguration.model_id)).all()
    return [_model_read(model, provider, provider_enabled) for model, provider, provider_enabled in rows]


@router.post("/models", status_code=status.HTTP_201_CREATED)
def add_model(data: ModelCreate, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict[str, object]:
    connection = _connection(session, user, data.connection_id)
    if session.scalar(select(AIModelConfiguration.id).where(
            AIModelConfiguration.connection_id == connection.id, AIModelConfiguration.model_id == data.model_id)):
        raise HTTPException(status_code=409, detail="This model is already configured.")
    row = AIModelConfiguration(user_id=user.id, connection_id=connection.id, model_id=data.model_id,
                               display_name=data.display_name or data.model_id, capabilities={})
    session.add(row)
    session.commit()
    session.refresh(row)
    return _model_read(row, connection.provider, connection.enabled)


@router.patch("/models/{model_id}")
def update_model(model_id: uuid.UUID, data: ModelUpdate, user: User = Depends(get_current_user),
                 session: Session = Depends(get_session)) -> dict[str, object]:
    row = session.scalar(select(AIModelConfiguration).where(
        AIModelConfiguration.id == model_id, AIModelConfiguration.user_id == user.id))
    if row is None:
        raise HTTPException(status_code=404, detail="AI model not found.")
    if data.enabled is not None:
        row.enabled = data.enabled
        if not data.enabled:
            row.is_default = False
    if data.is_default is True:
        row.enabled = True
        session.execute(update(AIModelConfiguration).where(
            AIModelConfiguration.user_id == user.id, AIModelConfiguration.id != row.id).values(is_default=False))
        row.is_default = True
    elif data.is_default is False:
        row.is_default = False
    if data.is_favorite is not None:
        row.is_favorite = data.is_favorite
    if data.capabilities is not None:
        allowed = {"tools", "vision", "reasoning", "streaming", "context_window", "input_cost_per_million", "output_cost_per_million"}
        if set(data.capabilities) - allowed:
            raise HTTPException(status_code=422, detail="Unsupported model capability metadata.")
        row.capabilities = data.capabilities
    session.commit()
    connection = _connection(session, user, row.connection_id)
    return _model_read(row, connection.provider, connection.enabled)


def _policy(session: Session, user: User) -> AIUserPolicy:
    row = session.get(AIUserPolicy, user.id)
    if row is None:
        try:
            # Concurrent first reads may both attempt to create the same owner policy.
            # Keep the outer transaction usable after the losing insert.
            with session.begin_nested():
                row = AIUserPolicy(user_id=user.id)
                session.add(row)
                session.flush()
        except IntegrityError:
            row = session.get(AIUserPolicy, user.id)
    return row


def _policy_read(row: AIUserPolicy) -> dict[str, object]:
    return {"auto_enabled": row.auto_enabled, "fallback_model_ids": row.fallback_model_ids,
            "task_model_ids": row.task_model_ids, "monthly_budget_cents": row.monthly_budget_cents,
            "warning_threshold_percent": row.warning_threshold_percent}


@router.get("/routing-policy")
def get_routing_policy(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict[str, object]:
    row = _policy(session, user); session.commit(); return _policy_read(row)


@router.put("/routing-policy")
def put_routing_policy(data: RoutingPolicyUpdate, user: User = Depends(get_current_user),
                       session: Session = Depends(get_session)) -> dict[str, object]:
    requested = {str(item) for item in data.fallback_model_ids} | {str(item) for item in data.task_model_ids.values()}
    owned = {str(item) for item in session.scalars(select(AIModelConfiguration.id).where(
        AIModelConfiguration.user_id == user.id, AIModelConfiguration.enabled.is_(True))).all()}
    if requested - owned:
        raise HTTPException(status_code=422, detail="Routing models must be enabled models owned by the user.")
    row = _policy(session, user); row.auto_enabled = data.auto_enabled
    row.fallback_model_ids = [str(item) for item in data.fallback_model_ids]
    row.task_model_ids = {key: str(value) for key, value in data.task_model_ids.items()}
    row.monthly_budget_cents = data.monthly_budget_cents; row.warning_threshold_percent = data.warning_threshold_percent
    session.commit(); return _policy_read(row)


@router.get("/usage")
def ai_usage(days: int = 30, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict[str, object]:
    if days < 1 or days > 365:
        raise HTTPException(status_code=422, detail="Usage range must be between 1 and 365 days.")
    start = datetime.now(timezone.utc) - timedelta(days=days)
    rows = session.scalars(select(AIUsageRecord).where(
        AIUsageRecord.user_id == user.id, AIUsageRecord.created_at >= start).order_by(AIUsageRecord.created_at.desc()).limit(5000)).all()
    cost = sum(row.estimated_cost_microusd or 0 for row in rows)
    policy = _policy(session, user); session.commit()
    groups: dict[str, dict[str, object]] = {}
    for row in rows:
        key = f"{row.provider}:{row.model_id}"; group = groups.setdefault(key, {"provider": row.provider, "model_id": row.model_id, "requests": 0, "failed": 0, "fallbacks": 0, "estimated_cost_microusd": 0})
        group["requests"] = int(group["requests"]) + 1; group["failed"] = int(group["failed"]) + int(row.status == "failed")
        group["fallbacks"] = int(group["fallbacks"]) + int(row.used_fallback); group["estimated_cost_microusd"] = int(group["estimated_cost_microusd"]) + (row.estimated_cost_microusd or 0)
    budget_micro = policy.monthly_budget_cents * 10_000 if policy.monthly_budget_cents is not None else None
    return {"days": days, "requests": len(rows), "failed_requests": sum(row.status == "failed" for row in rows),
            "rate_limit_events": sum(row.error_category in {"rate_limited", "quota_exceeded"} for row in rows), "estimated_cost_microusd": cost,
            "estimated_cost_usd": round(cost / 1_000_000, 6), "budget_cents": policy.monthly_budget_cents,
            "budget_used_percent": round(cost / budget_micro * 100, 1) if budget_micro else None,
            "cost_kind": "estimate", "by_model": list(groups.values())}
