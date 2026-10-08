from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from orin_api.config import Settings


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
            response = httpx.post(
                f"{self.config.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.config.api_key}", "HTTP-Referer": "https://orin.local", "X-Title": "Orin"},
                json={"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}], "temperature": temperature, "max_tokens": max_tokens, "response_format": {"type": "json_object"}},
                timeout=30.0,
            )
            response.raise_for_status()
            return str(response.json()["choices"][0]["message"]["content"])
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise AIProviderError("AI provider request failed") from exc

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
            raise AIProviderError("AI provider streaming request failed") from exc

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
            response = httpx.post(
                f"{self.config.base_url}/models/{model}:generateContent",
                params={"key": self.config.api_key},
                json={"systemInstruction": {"parts": [{"text": system}]}, "contents": [{"parts": [{"text": user}]}], "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens, "responseMimeType": "application/json"}},
                timeout=30.0,
            )
            response.raise_for_status()
            return str(response.json()["candidates"][0]["content"]["parts"][0]["text"])
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise AIProviderError("AI provider request failed") from exc

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
            raise AIProviderError("AI provider streaming request failed") from exc

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
    return AIIntent.model_validate_json(json.dumps(payload))


class AIInterpreter:
    def __init__(self, provider: AIProvider, model: str):
        self.provider, self.model = provider, model

    def interpret(self, command: str) -> AIIntent:
        schema = AIIntent.model_json_schema()
        raw = self.provider.structured_output(system=SYSTEM_INSTRUCTIONS, user=command, model=self.model, schema=schema)
        try:
            return _parse_intent(raw)
        except (ValidationError, ValueError, TypeError) as first_error:
            repair_request = (
                f"The previous response did not match the required schema. Return only one corrected JSON object. "
                f"Validation issue: {first_error}. User request: {command}"
            )
            try:
                repaired = self.provider.structured_output(
                    system=SYSTEM_INSTRUCTIONS, user=repair_request, model=self.model, schema=schema
                )
                return _parse_intent(repaired)
            except (AIProviderError, ValidationError, ValueError, TypeError) as exc:
                raise AIProviderError("AI returned an invalid command proposal") from exc


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
