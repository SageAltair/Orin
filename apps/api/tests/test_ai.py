import pytest
from pydantic import ValidationError
from contextlib import contextmanager

from orin_api.ai import AITaskType, AIIntent, AIInterpreter, AIProviderError, IntentName, IntentParameters, ModelSelector, OpenAIProvider, ProviderConfig, create_provider
from orin_api.config import Settings


class FakeProvider:
    def __init__(self, response: str | list[str]):
        self.responses = [response] if isinstance(response, str) else list(response)
        self.calls = 0

    def structured_output(self, **kwargs: object) -> str:
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return response


def test_structured_intent_accepts_supported_proposal() -> None:
    proposal = AIIntent.model_validate_json('{"intent":"CREATE_TASK","confidence":0.9,"parameters":{"title":"Call John"}}')
    assert proposal.intent == IntentName.CREATE_TASK


@pytest.mark.parametrize("payload", [
    {"intent": "RUN_SHELL", "confidence": 1.0, "parameters": {}},
    {"intent": "CREATE_TASK", "confidence": 1.1, "parameters": {"title": "x"}},
    {"intent": "CREATE_TASK", "confidence": 0.9, "parameters": {}},
    {"intent": "UPDATE_TASK", "confidence": 0.9, "parameters": {"task_id": "not-a-uuid", "fields_to_update": {"sql": "DROP"}}},
    {"intent": "COMPLETE_TASK", "confidence": 0.9, "parameters": {"task_id": "Website"}},
    {"intent": "LIST_TASKS", "confidence": 0.2, "parameters": {}},
])
def test_structured_intent_rejects_invalid_proposals(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        AIIntent.model_validate(payload)


def test_provider_selection_requires_only_selected_provider_credentials() -> None:
    settings = Settings(_env_file=None, ai_provider="openai", ai_model="test-model", openai_api_key="secret")
    provider = create_provider(settings)
    assert provider.config.model == "test-model"
    with pytest.raises(AIProviderError, match="Credentials"):
        create_provider(Settings(_env_file=None, ai_provider="mistral", ai_model="test-model"))


def test_intent_parameter_schema_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        IntentParameters.model_validate({"title": "ok", "shell": "echo bad"})


def test_intent_rejects_parameters_not_allowed_for_its_action() -> None:
    with pytest.raises(ValidationError):
        AIIntent.model_validate_json('{"intent":"LIST_TASKS","confidence":0.9,"parameters":{"title":"ignored"}}')


def test_model_selector_honors_task_and_explicit_overrides() -> None:
    selector = ModelSelector("default", {AITaskType.CLASSIFICATION: "cheap"})
    assert selector.select(AITaskType.CLASSIFICATION) == "cheap"
    assert selector.select(AITaskType.CLASSIFICATION, "override") == "override"


def test_interpreter_validates_json_enum_strings() -> None:
    provider = FakeProvider('{"intent":"LIST_TASKS","confidence":0.9,"parameters":{}}')
    proposal = AIInterpreter(provider, "model").interpret("List my tasks")
    assert proposal.intent == IntentName.LIST_TASKS


def test_interpreter_returns_safe_conversational_response_for_greeting() -> None:
    provider = FakeProvider('{"intent":"RESPOND","confidence":0.95,"parameters":{"response":"Hey! What can I help you with?"}}')
    proposal = AIInterpreter(provider, "model").interpret("Help me figure this out")
    assert proposal.intent == IntentName.RESPOND
    assert proposal.parameters.response == "Hey! What can I help you with?"


def test_interpreter_accepts_task_proposal_from_fenced_json() -> None:
    provider = FakeProvider('```json\n{"intent":"CREATE_TASK","confidence":0.9,"parameters":{"title":"Call John"}}\n```')
    proposal = AIInterpreter(provider, "model").interpret("Create a task called Call John")
    assert proposal.intent == IntentName.CREATE_TASK
    assert proposal.parameters.title == "Call John"


def test_interpreter_ignores_null_optional_parameters_returned_by_providers() -> None:
    provider = FakeProvider('{"intent":"CREATE_TASK","confidence":0.9,"parameters":{"title":"Call John","description":null,"due_at":null,"project_id":null,"task_id":null,"name":null,"status":null,"limit":null,"response":null,"fields_to_update":null}}')
    proposal = AIInterpreter(provider, "model").interpret("Create a task called Call John")
    assert proposal.intent == IntentName.CREATE_TASK
    assert proposal.parameters.title == "Call John"


def test_interpreter_repairs_malformed_or_unstructured_output() -> None:
    provider = FakeProvider(["I can help with that!", '{"intent":"RESPOND","confidence":0.9,"parameters":{"response":"Hey!"}}'])
    proposal = AIInterpreter(provider, "model").interpret("Help me figure this out")
    assert proposal.intent == IntentName.RESPOND
    assert provider.calls == 2


def test_interpreter_rejects_unrepairable_output() -> None:
    provider = FakeProvider("not json")
    with pytest.raises(AIProviderError, match="invalid response") as raised:
        AIInterpreter(provider, "model").interpret("Help me figure this out")
    assert raised.value.category == "invalid_response"


def test_intent_supports_name_reference_for_task_updates() -> None:
    proposal = AIIntent.model_validate_json(
        '{"intent":"COMPLETE_TASK","confidence":0.9,"parameters":{"task_reference":"Website"}}'
    )
    assert proposal.parameters.task_reference == "Website"


def test_interpreter_rejects_json_with_trailing_model_text() -> None:
    provider = FakeProvider([
        '{"intent":"LIST_TASKS","confidence":0.9,"parameters":{}} arbitrary text',
        '{"intent":"UNSUPPORTED","confidence":0.9,"parameters":{}}',
    ])
    proposal = AIInterpreter(provider, "model").interpret("show tasks")
    assert proposal.intent == IntentName.UNSUPPORTED


def test_interpreter_rejects_model_generated_shell_command() -> None:
    provider = FakeProvider(
        '{"intent":"CREATE_TASK","confidence":0.9,"parameters":{"title":"x","shell":"rm -rf /"}}'
    )
    with pytest.raises(AIProviderError):
        AIInterpreter(provider, "model").interpret("create a task")


def test_interpreter_repairs_model_generated_uuid_and_uses_task_reference() -> None:
    provider = FakeProvider([
        '{"intent":"COMPLETE_TASK","confidence":0.9,"parameters":{"task_id":"123e4567-e89b-12d3-a456-426614174000"}}',
        '{"intent":"COMPLETE_TASK","confidence":0.9,"parameters":{"task_reference":"Website"}}',
    ])
    proposal = AIInterpreter(provider, "model").interpret("Complete the Website task")
    assert proposal.parameters.task_id is None
    assert proposal.parameters.task_reference == "Website"
    assert provider.calls == 2


def test_interpreter_repairs_model_generated_uuid_and_uses_task_reference() -> None:
    provider = FakeProvider([
        '{"intent":"COMPLETE_TASK","confidence":0.9,"parameters":{"task_id":"123e4567-e89b-12d3-a456-426614174000"}}',
        '{"intent":"COMPLETE_TASK","confidence":0.9,"parameters":{"task_reference":"Website"}}',
    ])
    proposal = AIInterpreter(provider, "model").interpret("Complete the Website task")
    assert proposal.parameters.task_id is None
    assert proposal.parameters.task_reference == "Website"
    assert provider.calls == 2


def test_interpreter_preserves_provider_failure_during_schema_repair() -> None:
    class RepairFailureProvider(FakeProvider):
        def structured_output(self, **kwargs: object) -> str:
            if self.calls:
                raise AIProviderError("The AI provider is rate limiting requests.", category="rate_limited")
            self.calls += 1
            return "not json"

    with pytest.raises(AIProviderError, match="rate limiting") as raised:
        AIInterpreter(RepairFailureProvider("unused"), "model").interpret("Create a task")
    assert raised.value.category == "rate_limited"


def test_streaming_yields_only_text_and_sends_stream_request(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def raise_for_status(self) -> None:
            pass

        def iter_lines(self):
            return iter(['data: {"choices":[{"delta":{"content":"hello"}}]}', "data: [DONE]"])

    captured: dict[str, object] = {}

    @contextmanager
    def fake_stream(*args: object, **kwargs: object):
        captured.update(kwargs)
        yield Response()

    monkeypatch.setattr("orin_api.ai.httpx.stream", fake_stream)
    provider = OpenAIProvider(ProviderConfig("secret", "https://provider.test/v1", "model"))
    assert list(provider.stream(system="rules", user="hi", model="model")) == ["hello"]
    assert captured["json"]["stream"] is True


def _http_response(status: int, payload: dict[str, object], headers: dict[str, str] | None = None):
    import httpx

    return httpx.Response(status, json=payload, headers=headers, request=httpx.Request("POST", "https://provider.test"))


def test_provider_retries_rate_limit_and_uses_selected_model(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        _http_response(429, {"error": {"code": "rate_limit_exceeded", "message": "slow down"}}, {"retry-after": "0"}),
        _http_response(200, {"choices": [{"message": {"content": '{"intent":"RESPOND"}'}}]}),
    ]
    captured: list[dict[str, object]] = []

    def fake_post(url: str, **kwargs: object):
        captured.append(kwargs)
        return responses.pop(0)

    monkeypatch.setattr("orin_api.ai.httpx.post", fake_post)
    monkeypatch.setattr("orin_api.ai.time.sleep", lambda _: None)
    provider = OpenAIProvider(ProviderConfig("secret", "https://provider.test/v1", "configured-model"))
    assert provider.generate(system="rules", user="hey", model="configured-model") == '{"intent":"RESPOND"}'
    assert len(captured) == 2
    assert all(request["json"]["model"] == "configured-model" for request in captured)


def test_provider_does_not_retry_exhausted_quota_or_log_secrets(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    response = _http_response(429, {"error": {"code": "insufficient_quota", "message": "secret quota exhausted"}})
    calls = 0

    def fake_post(*args: object, **kwargs: object):
        nonlocal calls
        calls += 1
        return response

    monkeypatch.setattr("orin_api.ai.httpx.post", fake_post)
    provider = OpenAIProvider(ProviderConfig("secret", "https://provider.test/v1", "model"))
    with pytest.raises(AIProviderError, match="quota") as raised:
        provider.generate(system="rules", user="hello", model="model")
    assert raised.value.category == "quota_exceeded"
    assert calls == 1
    assert "secret" not in caplog.text
    assert any(getattr(record, "provider_error_code", None) == "insufficient_quota" for record in caplog.records)


def test_provider_retries_temporary_server_error_then_recovers(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        _http_response(503, {"error": {"code": "temporarily_unavailable", "message": "try again"}}),
        _http_response(200, {"choices": [{"message": {"content": "{}"}}]}),
    ]
    monkeypatch.setattr("orin_api.ai.httpx.post", lambda *args, **kwargs: responses.pop(0))
    monkeypatch.setattr("orin_api.ai.time.sleep", lambda _: None)
    provider = OpenAIProvider(ProviderConfig("secret", "https://provider.test/v1", "model"))
    assert provider.generate(system="rules", user="hello", model="model") == "{}"


def test_provider_reports_upstream_status_when_temporary_failure_persists(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    response = _http_response(503, {"error": {"code": "service_unavailable", "message": "provider maintenance"}})
    calls = 0

    def fake_post(*args: object, **kwargs: object):
        nonlocal calls
        calls += 1
        return response

    monkeypatch.setattr("orin_api.ai.httpx.post", fake_post)
    monkeypatch.setattr("orin_api.ai.time.sleep", lambda _: None)
    provider = OpenAIProvider(ProviderConfig("secret", "https://provider.test/v1", "model"))
    with pytest.raises(AIProviderError, match="temporarily unavailable") as raised:
        provider.generate(system="rules", user="hello", model="model")
    assert raised.value.category == "provider_unavailable"
    assert calls == 3
    assert '"status_code": 503' in caplog.text
    assert "service_unavailable" in caplog.text


def test_provider_reports_timeout_and_malformed_success_response(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    monkeypatch.setattr("orin_api.ai.httpx.post", lambda *args, **kwargs: (_ for _ in ()).throw(httpx.ReadTimeout("timed out")))
    monkeypatch.setattr("orin_api.ai.time.sleep", lambda _: None)
    provider = OpenAIProvider(ProviderConfig("secret", "https://provider.test/v1", "model"))
    with pytest.raises(AIProviderError, match="timed out") as timeout:
        provider.generate(system="rules", user="hello", model="model")
    assert timeout.value.category == "timeout"

    monkeypatch.setattr("orin_api.ai.httpx.post", lambda *args, **kwargs: _http_response(200, {"choices": []}))
    with pytest.raises(AIProviderError, match="invalid response") as malformed:
        provider.generate(system="rules", user="hello", model="model")
    assert malformed.value.category == "invalid_response"
