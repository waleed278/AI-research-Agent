import json
from typing import Any, TypeVar

from anthropic import (
    APIConnectionError,
    APITimeoutError,
    AsyncAnthropic,
    AuthenticationError,
    InternalServerError,
    OverloadedError,
    RateLimitError,
)
from pydantic import BaseModel, ValidationError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from app.core.logging import get_logger
from app.llm.base import InvalidCredentialError
from app.llm.pricing import calculate_cost_usd
from app.llm.schemas import ChatResult, LLMUsage, StructuredResult, ToolCallRequest

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)

_DEFAULT_MAX_TOKENS = 8192
_STRUCTURED_TOOL_NAME = "emit_result"

_TRANSIENT_ERRORS = (
    RateLimitError,
    APITimeoutError,
    APIConnectionError,
    InternalServerError,
    OverloadedError,
)

_retry_transient = retry(
    retry=retry_if_exception_type(_TRANSIENT_ERRORS),
    wait=wait_exponential_jitter(initial=1, max=20),
    stop=stop_after_attempt(4),
    reraise=True,
)


class StructuredOutputError(RuntimeError):
    """Mirrors app.llm.providers.openai_provider.StructuredOutputError."""


class AnthropicProvider:
    """Async wrapper around Anthropic's Messages API implementing
    `LLMProvider` (app/llm/base.py). Two things this API has no native
    equivalent for, both handled here:

    1. Structured output: Claude has no `response_format`-style mode. This
       uses the standard workaround -- a synthetic tool
       (`_STRUCTURED_TOOL_NAME`) whose `input_schema` is the target Pydantic
       model's JSON schema, with `tool_choice` forced to that exact tool so
       Claude cannot respond with anything else; the resulting `tool_use`
       block's `input` is validated as the structured result. See
       docs/decisions/0009-multi-provider-byok.md.
    2. Tool results: unlike OpenAI's one-message-per-result convention,
       Anthropic requires every tool_result for a given assistant turn
       batched into a single following user message. `_convert_messages`
       merges consecutive "tool"-role lingua-franca messages accordingly.
    """

    def __init__(self, api_key: str, timeout_seconds: float = 60.0) -> None:
        self._client = AsyncAnthropic(api_key=api_key, timeout=timeout_seconds)

    @_retry_transient
    async def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
    ) -> ChatResult:
        system, converted = _convert_messages(messages)
        response = await self._client.messages.create(
            model=model,
            max_tokens=_DEFAULT_MAX_TOKENS,
            system=system or "",
            messages=converted,  # type: ignore[arg-type]
            tools=_convert_tools(tools) if tools else [],  # type: ignore[arg-type]
            temperature=temperature,
        )
        usage = _usage_from_message(response)
        text, tool_calls = _extract_text_and_tool_calls(response)
        return ChatResult(
            content=text,
            tool_calls=tool_calls,
            usage=usage,
            cost_usd=calculate_cost_usd(model, usage.prompt_tokens, usage.completion_tokens),
            finish_reason=response.stop_reason or "unknown",
        )

    @_retry_transient
    async def structured(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        response_model: type[T],
        temperature: float = 0.0,
    ) -> StructuredResult[T]:
        system, converted = _convert_messages(messages)
        tool = {
            "name": _STRUCTURED_TOOL_NAME,
            "description": "Emit the final result. Always call this with the complete, valid result.",
            "input_schema": response_model.model_json_schema(),
        }
        max_tokens = _DEFAULT_MAX_TOKENS
        repaired = False
        working_system = system or ""

        for attempt in range(2):
            response = await self._client.messages.create(  # type: ignore[call-overload]
                model=model,
                max_tokens=max_tokens,
                system=working_system,
                messages=converted,
                tools=[tool],
                tool_choice={"type": "tool", "name": _STRUCTURED_TOOL_NAME},
                temperature=temperature,
            )
            usage = _usage_from_message(response)
            cost = calculate_cost_usd(model, usage.prompt_tokens, usage.completion_tokens)

            tool_use = next(
                (b for b in response.content if b.type == "tool_use" and b.name == _STRUCTURED_TOOL_NAME),
                None,
            )
            if tool_use is not None:
                try:
                    data = response_model.model_validate(tool_use.input)
                    return StructuredResult(data=data, usage=usage, cost_usd=cost, repaired=repaired)
                except ValidationError as exc:
                    logger.warning(
                        "structured_output_invalid",
                        model=model,
                        provider="anthropic",
                        attempt=attempt,
                        error=str(exc),
                    )
            else:
                logger.warning(
                    "structured_output_incomplete",
                    model=model,
                    provider="anthropic",
                    attempt=attempt,
                    stop_reason=response.stop_reason,
                )

            # A stateless retry (fresh request, not a continued tool_use/tool_result
            # round trip) -- simpler than reconstructing a valid partial turn, and
            # this path is rare since a forced tool_choice all but guarantees a
            # matching tool_use block; the failure modes are truncation (hence the
            # bumped max_tokens) or a schema-valid-but-semantically-wrong input.
            repaired = True
            max_tokens = int(max_tokens * 1.5)
            working_system = (
                f"{system or ''}\n\nYour previous attempt did not produce a complete, valid "
                f"call to {_STRUCTURED_TOOL_NAME}. Call it again with the complete result."
            )

        raise StructuredOutputError(
            f"Failed to obtain a schema-valid response from {model} after repair retry"
        )

    async def validate(self) -> None:
        """Zero-token-cost credential check via the models-list endpoint."""
        try:
            async for _ in self._client.models.list():
                break
        except AuthenticationError as exc:
            raise InvalidCredentialError(f"Anthropic rejected this API key: {exc}") from exc


def _convert_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": t["function"]["name"],
            "description": t["function"].get("description", ""),
            "input_schema": t["function"]["parameters"],
        }
        for t in tools
    ]


def _convert_messages(messages: list[dict[str, Any]]) -> tuple[str | None, list[dict[str, Any]]]:
    """Converts the OpenAI-shaped message lingua franca (see app/llm/base.py)
    into Anthropic's system string + messages list. Consecutive "tool"-role
    messages are merged into a single user message with multiple
    `tool_result` blocks, since Anthropic requires all results for one
    assistant turn to arrive together, not as separate messages."""
    system_parts: list[str] = []
    converted: list[dict[str, Any]] = []
    pending_tool_results: list[dict[str, Any]] = []

    def flush_pending() -> None:
        if pending_tool_results:
            converted.append({"role": "user", "content": list(pending_tool_results)})
            pending_tool_results.clear()

    for message in messages:
        role = message["role"]

        if role == "system":
            system_parts.append(message["content"])
            continue

        if role == "tool":
            pending_tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": message["tool_call_id"],
                    "content": message["content"],
                }
            )
            continue

        flush_pending()

        if role == "user":
            converted.append({"role": "user", "content": message["content"]})
        elif role == "assistant":
            blocks: list[dict[str, Any]] = []
            if message.get("content"):
                blocks.append({"type": "text", "text": message["content"]})
            for tc in message.get("tool_calls", []):
                args = json.loads(tc["function"]["arguments"]) if tc["function"]["arguments"] else {}
                blocks.append(
                    {"type": "tool_use", "id": tc["id"], "name": tc["function"]["name"], "input": args}
                )
            converted.append({"role": "assistant", "content": blocks})

    flush_pending()
    system = "\n\n".join(system_parts) if system_parts else None
    return system, converted


def _extract_text_and_tool_calls(message: Any) -> tuple[str | None, list[ToolCallRequest]]:
    text_parts: list[str] = []
    tool_calls: list[ToolCallRequest] = []
    for block in message.content:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "tool_use":
            tool_calls.append(ToolCallRequest(id=block.id, name=block.name, arguments=dict(block.input)))
    return ("\n".join(text_parts) or None, tool_calls)


def _usage_from_message(message: Any) -> LLMUsage:
    usage = message.usage
    if usage is None:
        return LLMUsage()
    return LLMUsage(
        prompt_tokens=usage.input_tokens,
        completion_tokens=usage.output_tokens,
        total_tokens=usage.input_tokens + usage.output_tokens,
    )
