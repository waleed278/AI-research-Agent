import json
from typing import Any, TypeVar

from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError
from pydantic import BaseModel
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential_jitter

from app.core.logging import get_logger
from app.llm.base import InvalidCredentialError
from app.llm.pricing import calculate_cost_usd
from app.llm.schemas import ChatResult, LLMUsage, StructuredResult, ToolCallRequest

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


class StructuredOutputError(RuntimeError):
    """Mirrors app.llm.providers.openai_provider.StructuredOutputError --
    raised when Gemini's structured-output mode fails to produce a
    schema-valid result even after a repair retry."""


def _is_transient(exc: BaseException) -> bool:
    """Gemini has no single "rate limited" exception class -- 429s surface
    as a ClientError with `.code == 429`, indistinguishable by type alone
    from a plain bad request (also a ClientError). Retrying on type alone
    (as the OpenAI adapter does) would either retry non-transient 400s or
    miss the 429 case, so this checks the actual status code instead."""
    if isinstance(exc, ServerError):
        return True
    if isinstance(exc, ClientError):
        return getattr(exc, "code", None) == 429
    return False


_retry_transient = retry(
    retry=retry_if_exception(_is_transient),
    wait=wait_exponential_jitter(initial=1, max=20),
    stop=stop_after_attempt(4),
    reraise=True,
)


class GeminiProvider:
    """Async wrapper around Google's `google-genai` SDK implementing
    `LLMProvider` (app/llm/base.py). Translates the OpenAI-shaped
    message/tool lingua franca that flows through the agent layer into
    Gemini's Content/Part/FunctionCall model -- see
    docs/decisions/0009-multi-provider-byok.md for why that lingua franca
    exists and what's non-obvious about this specific translation
    (message-role mapping, and Gemini having no "tool" role of its own)."""

    def __init__(self, api_key: str, timeout_seconds: float = 60.0) -> None:
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=int(timeout_seconds * 1000)),
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
        system_instruction, contents = _convert_messages(messages)
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            tools=[_convert_tools(tools)] if tools else None,
        )
        response = await self._client.aio.models.generate_content(
            model=model, contents=contents, config=config
        )
        usage = _usage_from_response(response)
        text, tool_calls = _extract_text_and_tool_calls(response)
        return ChatResult(
            content=text,
            tool_calls=tool_calls,
            usage=usage,
            cost_usd=calculate_cost_usd(model, usage.prompt_tokens, usage.completion_tokens),
            finish_reason=_finish_reason(response),
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
        """Gemini's structured-output mode (`response_mime_type` +
        `response_schema`) accepts a Pydantic model class directly and
        returns the parsed instance on `response.parsed` -- close enough to
        OpenAI's `.parse()` ergonomics that this needs no schema
        conversion, just the same repair-retry contract as every other
        provider (see ADR 0003)."""
        system_instruction, contents = _convert_messages(messages)
        repaired = False
        working_contents = contents

        for attempt in range(2):
            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=temperature,
                response_mime_type="application/json",
                response_schema=response_model,
            )
            response = await self._client.aio.models.generate_content(
                model=model, contents=working_contents, config=config
            )
            usage = _usage_from_response(response)
            cost = calculate_cost_usd(model, usage.prompt_tokens, usage.completion_tokens)

            parsed = response.parsed
            if isinstance(parsed, response_model):
                return StructuredResult(data=parsed, usage=usage, cost_usd=cost, repaired=repaired)

            logger.warning(
                "structured_output_incomplete", model=model, provider="gemini", attempt=attempt
            )
            repaired = True
            working_contents = [
                *contents,
                types.Content(role="model", parts=[types.Part.from_text(text=response.text or "")]),
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(
                            text=(
                                "Your previous response did not produce valid, complete JSON "
                                "matching the required schema. Respond again with ONLY the "
                                "complete JSON object."
                            )
                        )
                    ],
                ),
            ]

        raise StructuredOutputError(
            f"Failed to obtain a schema-valid response from {model} after repair retry"
        )

    async def validate(self) -> None:
        """Zero-token-cost credential check via the models-list endpoint."""
        try:
            async for _ in await self._client.aio.models.list():
                break
        except ClientError as exc:
            raise InvalidCredentialError(f"Gemini rejected this API key: {exc}") from exc


def _convert_tools(tools: list[dict[str, Any]]) -> types.Tool:
    """Converts our OpenAI-shaped tool schemas (see app/tools/base.py::
    Tool.to_openai_schema) into a single Gemini Tool. `parameters_json_schema`
    accepts a raw JSON-schema dict directly -- the exact shape our tool
    schemas already produce -- so no structural conversion is needed, only
    unwrapping OpenAI's `{"type": "function", "function": {...}}` envelope."""
    declarations = [
        types.FunctionDeclaration(
            name=t["function"]["name"],
            description=t["function"].get("description", ""),
            parameters_json_schema=t["function"]["parameters"],
        )
        for t in tools
    ]
    return types.Tool(function_declarations=declarations)


def _convert_messages(messages: list[dict[str, Any]]) -> tuple[str | None, list[types.Content]]:
    """Converts the OpenAI-shaped message lingua franca into a Gemini
    system_instruction + contents list.

    Two things are non-obvious here:
    1. Gemini's `Content.role` is only ever "user" or "model" -- tool
       results are sent back as role="user" parts, not a separate role.
    2. Our lingua franca's "tool" messages carry a `tool_call_id` but not
       the function *name*; Gemini's FunctionResponse needs the name to
       correlate. `call_id_to_name` is built while walking the messages in
       order, from the preceding assistant tool_calls message -- this only
       works because that message always precedes its tool results (which
       is how app/agent/research_loop.py constructs the list).
    """
    system_parts: list[str] = []
    contents: list[types.Content] = []
    call_id_to_name: dict[str, str] = {}
    pending_function_response_parts: list[types.Part] = []

    def flush_pending() -> None:
        if pending_function_response_parts:
            contents.append(types.Content(role="user", parts=list(pending_function_response_parts)))
            pending_function_response_parts.clear()

    for message in messages:
        role = message["role"]

        if role == "system":
            system_parts.append(message["content"])
            continue

        if role == "tool":
            name = call_id_to_name.get(message["tool_call_id"], "unknown_function")
            pending_function_response_parts.append(
                types.Part.from_function_response(
                    name=name, response={"output": message["content"]}
                )
            )
            continue

        flush_pending()

        if role == "user":
            contents.append(types.Content(role="user", parts=[types.Part.from_text(text=message["content"])]))
        elif role == "assistant":
            parts: list[types.Part] = []
            if message.get("content"):
                parts.append(types.Part.from_text(text=message["content"]))
            for tc in message.get("tool_calls", []):
                call_id_to_name[tc["id"]] = tc["function"]["name"]
                args = json.loads(tc["function"]["arguments"]) if tc["function"]["arguments"] else {}
                parts.append(types.Part.from_function_call(name=tc["function"]["name"], args=args))
            contents.append(types.Content(role="model", parts=parts))

    flush_pending()
    system_instruction = "\n\n".join(system_parts) if system_parts else None

    if not contents and system_instruction:
        # Gemini's API requires at least one entry in `contents` even when
        # `system_instruction` is set -- a system_instruction-only request
        # raises "contents are required." This is exactly what our one-shot
        # structured-output calls (planner/critic/synthesizer) send: the
        # whole prompt as a single system message with no separate user
        # turn. Promote it into the sole user content instead of leaving
        # `system_instruction` to carry a prompt Gemini won't accept alone.
        contents = [types.Content(role="user", parts=[types.Part.from_text(text=system_instruction)])]
        system_instruction = None

    return system_instruction, contents


def _extract_text_and_tool_calls(
    response: types.GenerateContentResponse,
) -> tuple[str | None, list[ToolCallRequest]]:
    text_parts: list[str] = []
    tool_calls: list[ToolCallRequest] = []
    candidate = response.candidates[0] if response.candidates else None
    parts = candidate.content.parts if candidate and candidate.content and candidate.content.parts else []

    for index, part in enumerate(parts):
        if part.text:
            text_parts.append(part.text)
        if part.function_call:
            tool_calls.append(
                ToolCallRequest(
                    id=part.function_call.id or f"gemini-call-{index}",
                    name=part.function_call.name or "",
                    arguments=dict(part.function_call.args or {}),
                )
            )

    return ("\n".join(text_parts) or None, tool_calls)


def _finish_reason(response: types.GenerateContentResponse) -> str:
    candidate = response.candidates[0] if response.candidates else None
    reason = candidate.finish_reason if candidate else None
    return str(reason) if reason is not None else "unknown"


def _usage_from_response(response: types.GenerateContentResponse) -> LLMUsage:
    usage = response.usage_metadata
    if usage is None:
        return LLMUsage()
    prompt_tokens = usage.prompt_token_count or 0
    completion_tokens = usage.candidates_token_count or 0
    return LLMUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=usage.total_token_count or (prompt_tokens + completion_tokens),
    )
