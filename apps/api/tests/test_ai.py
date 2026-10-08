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
    {"intent": "LIST_TASKS", "confidence": 0.2, "parameters": {}},
])
def test_structured_intent_rejects_invalid_proposals(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        AIIntent.model_validate(payload)


def test_provider_selection_requires_only_selected_provider_credentials() -> None:
    settings = Settings(ai_provider="openai", ai_model="test-model", openai_api_key="secret")
    provider = create_provider(settings)
    assert provider.config.model == "test-model"
    with pytest.raises(AIProviderError, match="Credentials"):
        create_provider(Settings(ai_provider="mistral", ai_model="test-model"))


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
    with pytest.raises(AIProviderError, match="invalid command proposal"):
        AIInterpreter(provider, "model").interpret("Help me figure this out")


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
