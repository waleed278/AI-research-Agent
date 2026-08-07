from types import SimpleNamespace
from typing import Any

import pytest

from app.llm.pricing import calculate_cost_usd
from app.llm.schemas import ChatResult, LLMUsage, StructuredResult, ToolCallRequest


def make_usage(prompt_tokens: int = 10, completion_tokens: int = 5) -> LLMUsage:
    return LLMUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )


class FakeLLMClient:
    """Drop-in stand-in for any `app.llm.base.LLMProvider` implementation,
    used throughout the unit/integration tests. Responses are pre-scripted
    per call, which lets a test assert on exactly what the orchestrator does
    at each phase without ever making a network call or depending on model
    non-determinism -- that determinism is what makes the *rest* of the
    agent pipeline testable at all.
    """

    def __init__(self) -> None:
        self._chat_queue: list[ChatResult] = []
        self._structured_queue: dict[str, list[Any]] = {}
        self.chat_calls: list[dict[str, Any]] = []
        self.structured_calls: list[dict[str, Any]] = []

    def queue_chat(self, result: ChatResult) -> None:
        self._chat_queue.append(result)

    def queue_structured(self, model_name: str, data: Any) -> None:
        self._structured_queue.setdefault(model_name, []).append(data)

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
    ) -> ChatResult:
        self.chat_calls.append({"model": model, "messages": messages, "tools": tools})
        if self._chat_queue:
            return self._chat_queue.pop(0)
        return ChatResult(
            content="No more evidence needed.",
            tool_calls=[],
            usage=make_usage(),
            cost_usd=0.0,
            finish_reason="stop",
        )

    async def structured(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        response_model: type,
        temperature: float = 0.0,
    ) -> StructuredResult:
        self.structured_calls.append(
            {"model": model, "response_model": response_model.__name__, "messages": messages}
        )
        queue = self._structured_queue.get(response_model.__name__, [])
        if not queue:
            raise AssertionError(f"No queued structured response for {response_model.__name__}")
        data = queue.pop(0)
        usage = make_usage()
        return StructuredResult(
            data=data,
            usage=usage,
            cost_usd=calculate_cost_usd(model, usage.prompt_tokens, usage.completion_tokens),
        )


def tool_call(call_id: str, name: str, arguments: dict[str, Any]) -> ToolCallRequest:
    return ToolCallRequest(id=call_id, name=name, arguments=arguments)


def fake_openai_chat_completion(
    content: str | None,
    tool_calls: list | None = None,
    finish_reason: str = "stop",
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
) -> SimpleNamespace:
    """Builds an object shaped enough like an OpenAI `ChatCompletion` for
    `OpenAIProvider.chat()` to parse -- used to test the LLM adapter itself
    (retry/parsing logic) without hitting the network."""
    message = SimpleNamespace(content=content, tool_calls=tool_calls or [])
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    usage = SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )
    return SimpleNamespace(choices=[choice], usage=usage)


def fake_openai_parsed_completion(
    parsed: Any,
    refusal: str | None = None,
    finish_reason: str = "stop",
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
) -> SimpleNamespace:
    message = SimpleNamespace(parsed=parsed, refusal=refusal)
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    usage = SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )
    return SimpleNamespace(choices=[choice], usage=usage)


@pytest.fixture
def fake_llm() -> FakeLLMClient:
    return FakeLLMClient()
