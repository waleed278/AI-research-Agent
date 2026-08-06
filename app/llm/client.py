from typing import Any, TypeVar

from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    InternalServerError,
    RateLimitError,
)
from pydantic import BaseModel
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.llm.pricing import calculate_cost_usd
from app.llm.schemas import ChatResult, LLMUsage, StructuredResult, ToolCallRequest

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)

_TRANSIENT_ERRORS = (RateLimitError, APITimeoutError, APIConnectionError, InternalServerError)

_retry_transient = retry(
    retry=retry_if_exception_type(_TRANSIENT_ERRORS),
    wait=wait_exponential_jitter(initial=1, max=20),
    stop=stop_after_attempt(4),
    reraise=True,
)


class StructuredOutputError(RuntimeError):
    """Raised when the model refuses to answer or produces output that still
    fails schema validation after the repair retry."""


class LLMClient:
    """Thin async wrapper around the OpenAI SDK. Every call site in this
    codebase goes through here rather than touching `openai` directly, so
    retries, cost accounting, and structured-output validation are enforced
    in exactly one place instead of being reimplemented (or forgotten) at
    each call site."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = AsyncOpenAI(
            api_key=self.settings.openai_api_key,
            timeout=self.settings.openai_request_timeout_seconds,
        )

    @_retry_transient
    async def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
    ) -> ChatResult:
        """Free-form chat completion, optionally with tool-calling enabled.
        Used by the research loop, where the model chooses which tool (if
        any) to call next."""
        response = await self._client.chat.completions.create(  # type: ignore[call-overload]
            model=model,
            messages=messages,
            tools=tools,
            tool_choice="auto" if tools else None,
            temperature=temperature,
        )
        choice = response.choices[0]
        usage = _usage_from_response(response)
        tool_calls = [
            ToolCallRequest(
                id=tc.id,
                name=tc.function.name,
                arguments=_safe_json_loads(tc.function.arguments),
            )
            for tc in (choice.message.tool_calls or [])
        ]
        return ChatResult(
            content=choice.message.content,
            tool_calls=tool_calls,
            usage=usage,
            cost_usd=calculate_cost_usd(model, usage.prompt_tokens, usage.completion_tokens),
            finish_reason=choice.finish_reason,
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
        """Schema-constrained call: the response is guaranteed (by OpenAI's
        structured-outputs mode) to be JSON matching `response_model`, and we
        additionally validate it through Pydantic. On a refusal or an
        incomplete response (e.g. truncated by a length limit) we retry once
        with an explicit instruction to comply -- if that still fails we
        raise rather than silently returning garbage to the agent."""
        repaired = False
        working_messages = list(messages)

        for attempt in range(2):
            response = await self._client.chat.completions.parse(
                model=model,
                messages=working_messages,  # type: ignore[arg-type]
                response_format=response_model,
                temperature=temperature,
            )
            choice = response.choices[0]
            usage = _usage_from_response(response)
            cost = calculate_cost_usd(model, usage.prompt_tokens, usage.completion_tokens)

            if choice.message.refusal:
                raise StructuredOutputError(f"Model refused to answer: {choice.message.refusal}")

            parsed = choice.message.parsed
            if parsed is not None:
                return StructuredResult(data=parsed, usage=usage, cost_usd=cost, repaired=repaired)

            logger.warning(
                "structured_output_incomplete",
                model=model,
                finish_reason=choice.finish_reason,
                attempt=attempt,
            )
            repaired = True
            working_messages = [
                *messages,
                {
                    "role": "user",
                    "content": (
                        "Your previous response did not produce valid, complete JSON matching "
                        "the required schema. Respond again with ONLY the complete JSON object."
                    ),
                },
            ]

        raise StructuredOutputError(
            f"Failed to obtain a schema-valid response from {model} after repair retry"
        )


def _usage_from_response(response: Any) -> LLMUsage:
    usage = response.usage
    if usage is None:
        return LLMUsage()
    return LLMUsage(
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        total_tokens=usage.total_tokens,
    )


def _safe_json_loads(raw: str) -> dict[str, Any]:
    import json

    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return {}
