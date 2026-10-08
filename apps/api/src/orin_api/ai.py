from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from enum import StrEnum
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from orin_api.config import Settings


logger = logging.getLogger(__name__)


class AITaskType(StrEnum):
    COMMAND_INTERPRETATION = "command_interpretation"
    STRUCTURED_PLANNING = "structured_planning"
    SUMMARIZATION = "summarization"
    GENERAL_REASONING = "general_reasoning"
    CLASSIFICATION = "classification"


@dataclass(frozen=True)
class ModelInfo:
    provider: str
    model: str
    supports_streaming: bool = True
    supports_structured_output: bool = True
    supports_json_schema: bool = False
    context_window: int | None = None


MODEL_REGISTRY: dict[str, ModelInfo] = {}


class AIProviderError(Exception):
    """Safe application-level error for provider failures."""

    def __init__(self, message: str, *, category: str = "provider_error") -> None:
        super().__init__(message)
        self.category = category


def _error_details(response: httpx.Response) -> tuple[str, str]:
    """Extract stable, non-secret provider error fields from common API formats."""
    try:
        payload = response.json()
    except ValueError:
        return "", ""
    error = payload.get("error", {}) if isinstance(payload, dict) else {}
    if isinstance(error, str):
        return error[:160], ""
    if not isinstance(error, dict):
        return "", ""
    code = error.get("code") or error.get("type") or error.get("status") or ""
    message = error.get("message") or ""
    return str(code)[:160], str(message)[:320]


def _provider_failure(provider: str, model: str, exc: Exception, attempt: int, api_key: str = "") -> AIProviderError:
    response = exc.response if isinstance(exc, httpx.HTTPStatusError) else None
    status_code = response.status_code if response is not None else None
    code, detail = _error_details(response) if response is not None else ("", "")
    if api_key:
        detail = detail.replace(api_key, "[REDACTED]")
    searchable = f"{code} {detail}".lower()
    quota = any(token in searchable for token in ("quota", "billing", "insufficient_credit", "credit balance"))

    if quota:
        category = "quota_exceeded"
        message = "The configured AI provider has no available quota. Check its billing or usage limits."
    elif status_code == 429:
        category = "rate_limited"
        message = "The AI provider is rate limiting requests. Please retry shortly."
    elif isinstance(exc, (httpx.TimeoutException, TimeoutError)):
        category = "timeout"
        message = "The AI provider timed out. Please retry shortly."
    elif status_code in (401, 403):
        category = "authentication"
        message = "The AI provider rejected its configured credentials or access. Check provider settings."
    elif status_code is not None and status_code >= 500:
        category = "provider_unavailable"
        message = "The AI provider is temporarily unavailable. Please retry shortly."
    elif status_code is not None:
        category = "request_rejected"
        message = "The AI provider rejected the request. Check the configured model and provider settings."
    elif isinstance(exc, httpx.TransportError):
        category = "connection_error"
        message = "The AI provider could not be reached. Please retry shortly."
    else:
        category = "invalid_response"
        message = "The AI provider returned an invalid response. Please retry shortly."

    log_data = {
        "provider": provider,
        "model": model,
        "category": category,
        "status_code": status_code,
        "provider_error_code": code,
        "provider_error_message": detail,
        "attempt": attempt,
        "request_id": response.headers.get("x-request-id") if response is not None else None,
    }
    logger.warning(
        "AI provider request failed: %s",
        json.dumps(log_data, sort_keys=True),
        extra=log_data,
    )
    return AIProviderError(message, category=category)


def _retry_delay(response: httpx.Response | None, attempt: int) -> float | None:
    """Return a bounded delay for a safe retry, or None when the provider asks us to wait longer."""
    if response is not None:
        retry_after = response.headers.get("retry-after")
        if retry_after:
            try:
                delay = float(retry_after)
            except ValueError:
                match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)s\s*", retry_after, re.IGNORECASE)
                if match:
                    delay = float(match.group(1))
                else:
                    try:
                        retry_at = parsedate_to_datetime(retry_after)
                        if retry_at.tzinfo is None:
                            retry_at = retry_at.replace(tzinfo=timezone.utc)
                        delay = max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
                    except (TypeError, ValueError, OverflowError):
                        return None
            return delay if 0 <= delay <= 10 else None
        reset = response.headers.get("x-ratelimit-reset-requests") or response.headers.get("x-ratelimit-reset")
        if reset:
            match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)s\s*", reset, re.IGNORECASE)
            if match:
                delay = float(match.group(1))
                return delay if 0 <= delay <= 10 else None
    return min(0.25 * (2 ** (attempt - 1)), 1.0)


def _post_with_retry(url: str, *, provider: str, model: str, api_key: str = "", **kwargs: Any) -> httpx.Response:
    """Retry only transient inference failures; inference requests have no application side effects."""
    for attempt in range(1, 4):
        try:
            response = httpx.post(url, **kwargs)
            response.raise_for_status()
            return response
        except (httpx.HTTPError, TimeoutError) as exc:
            response = exc.response if isinstance(exc, httpx.HTTPStatusError) else None
            code, detail = _error_details(response) if response is not None else ("", "")
            quota = any(token in f"{code} {detail}".lower() for token in ("quota", "billing", "insufficient_credit", "credit balance"))
            status_code = response.status_code if response is not None else None
            retryable = (
                not quota
                and attempt < 3
                and (status_code == 429 or status_code == 408 or (status_code is not None and status_code >= 500)
                     or isinstance(exc, (httpx.TimeoutException, httpx.TransportError, TimeoutError)))
            )
            if retryable:
                delay = _retry_delay(response, attempt)
                if delay is not None:
                    logger.info(
                        "Retrying transient AI provider request",
                        extra={"provider": provider, "model": model, "status_code": status_code, "attempt": attempt},
                    )
                    time.sleep(delay)
                    continue
            raise _provider_failure(provider, model, exc, attempt, api_key) from exc
    raise AssertionError("unreachable")


class AIProvider(Protocol):
    def generate(self, *, system: str, user: str, model: str, temperature: float = 0.0, max_tokens: int = 512) -> str: ...
    def stream(self, *, system: str, user: str, model: str): ...
    def structured_output(self, *, system: str, user: str, model: str, schema: dict[str, Any]) -> str: ...


class ProviderName(StrEnum):
    OPENAI = "openai"
    MISTRAL = "mistral"
    GOOGLE = "google"
    OPENROUTER = "openrouter"
    QWEN = "qwen"
    GROQ = "groq"
    CEREBRAS = "cerebras"
    CLOUDFLARE = "cloudflare"


@dataclass(frozen=True)
class ProviderConfig:
    api_key: str
    base_url: str
    model: str
    account_id: str | None = None


class _OpenAICompatibleProvider:
    def __init__(self, config: ProviderConfig):
        self.config = config
        self.capabilities = {"streaming": True, "structured_output": True, "json_schema": False, "tool_calling": False}

    def generate(self, *, system: str, user: str, model: str, temperature: float = 0.0, max_tokens: int = 512) -> str:
        try:
            response = _post_with_retry(
                f"{self.config.base_url}/chat/completions", provider=type(self).__name__, model=model, api_key=self.config.api_key,
                headers={"Authorization": f"Bearer {self.config.api_key}", "HTTP-Referer": "https://orin.local", "X-Title": "Orin"},
                json={"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}], "temperature": temperature, "max_tokens": max_tokens, "response_format": {"type": "json_object"}},
                timeout=30.0,
            )
            content = response.json()["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("empty or non-text model content")
            return content
        except AIProviderError:
            raise
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            failure = _provider_failure(type(self).__name__, model, exc, 1, self.config.api_key)
            raise failure from exc

    def stream(self, *, system: str, user: str, model: str):
        try:
            with httpx.stream(
                "POST", f"{self.config.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.config.api_key}"},
                json={"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}], "stream": True},
                timeout=30.0,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line.startswith("data: ") or line[6:] == "[DONE]":
                        continue
                    chunk = json.loads(line[6:])
                    content = chunk["choices"][0]["delta"].get("content")
                    if isinstance(content, str) and content:
                        yield content
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise _provider_failure(type(self).__name__, model, exc, 1, self.config.api_key) from exc

    def structured_output(self, *, system: str, user: str, model: str, schema: dict[str, Any]) -> str:
        schema_instruction = f"Return JSON matching this schema exactly: {json.dumps(schema, separators=(',', ':'))}"
        return self.generate(system=f"{system}\n{schema_instruction}", user=user, model=model)


class OpenAIProvider(_OpenAICompatibleProvider): pass
class MistralProvider(_OpenAICompatibleProvider): pass
class OpenRouterProvider(_OpenAICompatibleProvider): pass
class QwenProvider(_OpenAICompatibleProvider): pass
class GroqProvider(_OpenAICompatibleProvider): pass
class CerebrasProvider(_OpenAICompatibleProvider): pass
class CloudflareWorkersAIProvider(_OpenAICompatibleProvider): pass


class GoogleProvider:
    def __init__(self, config: ProviderConfig):
        self.config = config
        self.capabilities = {"streaming": True, "structured_output": True, "json_schema": False, "tool_calling": False}

    def generate(self, *, system: str, user: str, model: str, temperature: float = 0.0, max_tokens: int = 512) -> str:
        try:
            response = _post_with_retry(
                f"{self.config.base_url}/models/{model}:generateContent",
                provider=type(self).__name__, model=model, api_key=self.config.api_key,
                params={"key": self.config.api_key},
                json={"systemInstruction": {"parts": [{"text": system}]}, "contents": [{"parts": [{"text": user}]}], "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens, "responseMimeType": "application/json"}},
                timeout=30.0,
            )
            content = response.json()["candidates"][0]["content"]["parts"][0]["text"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("empty or non-text model content")
            return content
        except AIProviderError:
            raise
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            failure = _provider_failure(type(self).__name__, model, exc, 1, self.config.api_key)
            raise failure from exc

    def stream(self, *, system: str, user: str, model: str):
        try:
            with httpx.stream(
                "POST", f"{self.config.base_url}/models/{model}:streamGenerateContent",
                params={"key": self.config.api_key, "alt": "sse"},
                json={"systemInstruction": {"parts": [{"text": system}]}, "contents": [{"parts": [{"text": user}]}]},
                timeout=30.0,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    event = json.loads(line[6:])
                    content = event["candidates"][0]["content"]["parts"][0].get("text")
                    if isinstance(content, str) and content:
                        yield content
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise _provider_failure(type(self).__name__, model, exc, 1, self.config.api_key) from exc

    def structured_output(self, *, system: str, user: str, model: str, schema: dict[str, Any]) -> str:
        schema_instruction = f"Return JSON matching this schema exactly: {json.dumps(schema, separators=(',', ':'))}"
        return self.generate(system=f"{system}\n{schema_instruction}", user=user, model=model)


PROVIDER_TYPES = {
    ProviderName.OPENAI: OpenAIProvider,
    ProviderName.MISTRAL: MistralProvider,
    ProviderName.GOOGLE: GoogleProvider,
    ProviderName.OPENROUTER: OpenRouterProvider,
    ProviderName.QWEN: QwenProvider,
    ProviderName.GROQ: GroqProvider,
    ProviderName.CEREBRAS: CerebrasProvider,
    ProviderName.CLOUDFLARE: CloudflareWorkersAIProvider,
}


def create_provider(settings: Settings) -> AIProvider:
    try:
        name = ProviderName(settings.ai_provider.lower())
    except ValueError as exc:
        raise AIProviderError("Configured AI provider is unsupported") from exc
    key_by_name = {
        "openai": settings.openai_api_key, "mistral": settings.mistral_api_key,
        "google": settings.google_api_key, "openrouter": settings.openrouter_api_key,
        "qwen": settings.qwen_api_key, "groq": settings.groq_api_key,
        "cerebras": settings.cerebras_api_key, "cloudflare": settings.cloudflare_api_key,
    }
    urls = {
        "openai": "https://api.openai.com/v1", "mistral": "https://api.mistral.ai/v1",
        "google": "https://generativelanguage.googleapis.com/v1beta", "openrouter": "https://openrouter.ai/api/v1",
        "qwen": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "groq": "https://api.groq.com/openai/v1",
        "cerebras": "https://api.cerebras.ai/v1",
        "cloudflare": f"https://api.cloudflare.com/client/v4/accounts/{settings.cloudflare_account_id}/ai/v1",
    }
    key = key_by_name[name.value]
    if not key:
        raise AIProviderError("Credentials for the configured AI provider are missing")
    if name == ProviderName.CLOUDFLARE and not settings.cloudflare_account_id:
        raise AIProviderError("Cloudflare account ID is required for the configured AI provider")
    model = settings.ai_model
    MODEL_REGISTRY[f"{name.value}:{model}"] = ModelInfo(
        provider=name.value, model=model, supports_streaming=False,
        supports_structured_output=True, supports_json_schema=False,
    )
    return PROVIDER_TYPES[name](ProviderConfig(key, urls[name.value], model, settings.cloudflare_account_id))


class IntentName(StrEnum):
    RESPOND = "RESPOND"
    CREATE_TASK = "CREATE_TASK"
    UPDATE_TASK = "UPDATE_TASK"
    COMPLETE_TASK = "COMPLETE_TASK"
    CREATE_PROJECT = "CREATE_PROJECT"
    LIST_PROJECTS = "LIST_PROJECTS"
    LIST_TASKS = "LIST_TASKS"
    GET_ACTIVITY = "GET_ACTIVITY"
    UNSUPPORTED = "UNSUPPORTED"


class IntentParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    title: str | None = Field(default=None, min_length=1, max_length=240)
    description: str | None = None
    due_at: str | None = None
    project_id: str | None = None
    task_id: str | None = None
    fields_to_update: dict[str, Any] | None = None
    name: str | None = Field(default=None, min_length=1, max_length=160)
    status: str | None = None
    limit: int | None = Field(default=None, ge=1, le=100)
    response: str | None = Field(default=None, min_length=1, max_length=1000)


class AIIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    intent: IntentName
    confidence: float = Field(ge=0, le=1)
    parameters: IntentParameters

    @model_validator(mode="after")
    def validate_required_fields(self) -> AIIntent:
        allowed_fields = {
            IntentName.RESPOND: {"response"},
            IntentName.CREATE_TASK: {"title", "description", "due_at", "project_id"},
            IntentName.UPDATE_TASK: {"task_id", "fields_to_update"},
            IntentName.COMPLETE_TASK: {"task_id"},
            IntentName.CREATE_PROJECT: {"name", "description"},
            IntentName.LIST_PROJECTS: {"limit", "status"},
            IntentName.LIST_TASKS: {"limit", "status", "project_id"},
            IntentName.GET_ACTIVITY: {"limit"},
            IntentName.UNSUPPORTED: set(),
        }[self.intent]
        supplied_fields = self.parameters.model_fields_set
        if supplied_fields - allowed_fields:
            raise ValueError(f"Unexpected parameters for {self.intent.value}")
        required = {
            IntentName.RESPOND: ("response",),
            IntentName.CREATE_TASK: ("title",), IntentName.UPDATE_TASK: ("task_id", "fields_to_update"),
            IntentName.COMPLETE_TASK: ("task_id",), IntentName.CREATE_PROJECT: ("name",),
        }.get(self.intent, ())
        for field in required:
            if getattr(self.parameters, field) is None:
                raise ValueError(f"{field} is required for {self.intent.value}")
        if self.intent == IntentName.UPDATE_TASK:
            allowed = {"title", "description", "due_at", "project_id", "status", "priority"}
            fields = self.parameters.fields_to_update or {}
            if not fields or set(fields) - allowed:
                raise ValueError("Task update fields are invalid")
        if self.confidence < 0.55:
            raise ValueError("Interpretation confidence is too low")
        return self


SYSTEM_INSTRUCTIONS = "Interpret the user's request as one supported Orin intent. Return only JSON with intent, confidence, parameters. For greetings, thanks, or conversational messages that do not request workspace action, use RESPOND with a brief friendly response. Never invent identifiers or intents. Supported: RESPOND(response), CREATE_TASK(title,description,due_at,project_id), UPDATE_TASK(task_id,fields_to_update), COMPLETE_TASK(task_id), CREATE_PROJECT(name,description), LIST_PROJECTS, LIST_TASKS, GET_ACTIVITY. Otherwise use UNSUPPORTED."


def _parse_intent(raw: str) -> AIIntent:
    text = raw.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.IGNORECASE | re.DOTALL)
    if fenced:
        text = fenced.group(1)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for index, char in enumerate(text):
            if char == "{":
                try:
                    payload, _ = decoder.raw_decode(text[index:])
                    break
                except json.JSONDecodeError:
                    continue
        else:
            raise ValueError("No JSON object in model response")
    if isinstance(payload, dict) and isinstance(payload.get("parameters"), dict):
        payload["parameters"] = {
            key: value for key, value in payload["parameters"].items() if value is not None
        }
    return AIIntent.model_validate_json(json.dumps(payload))


class AIInterpreter:
    def __init__(self, provider: AIProvider, model: str):
        self.provider, self.model = provider, model

    def interpret(self, command: str) -> AIIntent:
        if re.fullmatch(r"(?:hi|hey|hello|good morning|good afternoon|good evening)[.!?,\s]*", command.strip(), re.IGNORECASE):
            return AIIntent(
                intent=IntentName.RESPOND,
                confidence=1.0,
                parameters=IntentParameters(response="Hey! What can I help you with?"),
            )
        schema = AIIntent.model_json_schema()
        raw = self.provider.structured_output(system=SYSTEM_INSTRUCTIONS, user=command, model=self.model, schema=schema)
        try:
            return _parse_intent(raw)
        except (ValidationError, ValueError, TypeError) as first_error:
            logger.warning(
                "AI provider returned an invalid proposal; requesting one schema repair",
                extra={"model": self.model, "category": "invalid_response", "attempt": 1},
            )
            repair_request = (
                f"The previous response did not match the required schema. Return only one corrected JSON object. "
                f"Validation issue: {first_error}. User request: {command}"
            )
            repaired = self.provider.structured_output(
                system=SYSTEM_INSTRUCTIONS, user=repair_request, model=self.model, schema=schema
            )
            try:
                return _parse_intent(repaired)
            except (ValidationError, ValueError, TypeError) as exc:
                logger.warning(
                    "AI provider proposal remained invalid after schema repair",
                    extra={"model": self.model, "category": "invalid_response", "attempt": 2},
                )
                raise AIProviderError(
                    "The AI provider returned an invalid response. Please retry shortly.",
                    category="invalid_response",
                ) from exc


class ModelSelector:
    """Replaceable task-to-model policy; explicit model overrides take precedence."""

    def __init__(self, default_model: str, task_models: dict[AITaskType, str] | None = None):
        self.default_model = default_model
        self.task_models = task_models or {}

    def select(self, task: AITaskType, explicit_model: str | None = None) -> str:
        selected = explicit_model or self.task_models.get(task) or self.default_model
        if not selected:
            raise AIProviderError("No AI model is configured")
        return selected


@dataclass(frozen=True)
class ProviderMetadata:
    provider: str
    model: str
    latency_ms: int
