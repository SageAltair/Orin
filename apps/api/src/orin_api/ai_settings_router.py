from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from orin_api.ai import PROVIDER_BASE_URLS, ProviderName
from orin_api.auth import get_current_user
from orin_api.config import Settings, get_settings
from orin_api.database import get_session
from orin_api.integration_secrets import IntegrationSecretError, decrypt_credential, encrypt_credential
from orin_api.models import AIModelConfiguration, AIProviderConnection, User
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
            "is_default": row.is_default, "provider_enabled": provider_enabled, "capabilities": row.capabilities}


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
    session.commit()
    connection = _connection(session, user, row.connection_id)
    return _model_read(row, connection.provider, connection.enabled)
