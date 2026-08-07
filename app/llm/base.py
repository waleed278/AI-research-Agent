from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from app.llm.schemas import ChatResult, StructuredResult

T = TypeVar("T", bound=BaseModel)


class InvalidCredentialError(Exception):
    """Raised by a provider's `validate()` when the API key it was built
    with is rejected by the provider. Distinct from `StructuredOutputError`
    (a model behavior problem) -- this is a credential problem, surfaced to
    the user as "that key doesn't work", not retried."""


class LLMProvider(Protocol):
    """Every LLM backend (OpenAI, Gemini, Anthropic -- see
    app/llm/providers/) implements this. Agent code
    (app/agent/planner.py, critic.py, synthesizer.py, research_loop.py,
    orchestrator.py) only ever calls `chat()`/`structured()` through this
    interface, never a concrete provider class, which is what let the BYOK
    multi-provider support land without changing a single line of agent
    logic -- see docs/decisions/0009-multi-provider-byok.md.
    """

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
    ) -> ChatResult:
        """Free-form chat completion, optionally with tool-calling enabled.
        `messages` is always the OpenAI wire format (roles
        system/user/assistant/tool, tool_calls as OpenAI shapes them) --
        every provider adapter is responsible for translating this lingua
        franca to and from its own SDK's native format, so callers never
        need to know which provider they're talking to."""
        ...

    async def structured(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        response_model: type[T],
        temperature: float = 0.0,
    ) -> StructuredResult[T]:
        """Schema-constrained call returning a validated `response_model`
        instance. Each provider implements this with whatever mechanism it
        actually has (native structured outputs, or -- for Anthropic, which
        has none -- a forced single tool call); see each adapter's
        docstring."""
        ...

    async def validate(self) -> None:
        """Makes the cheapest possible real call to the provider to confirm
        the API key this instance was built with actually works. Raises
        InvalidCredentialError on failure -- returns nothing on success, so
        a caller can't accidentally ignore a bool result."""
        ...
