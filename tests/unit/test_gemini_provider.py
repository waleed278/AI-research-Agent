from unittest.mock import AsyncMock

import pytest
from google.genai import types
from google.genai.errors import ClientError, ServerError
from pydantic import BaseModel

from app.llm.base import InvalidCredentialError
from app.llm.providers.gemini_provider import (
    GeminiProvider,
    StructuredOutputError,
    _convert_messages,
    _convert_tools,
    _extract_text_and_tool_calls,
    _is_transient,
)


class _Verdict(BaseModel):
    ok: bool
    reason: str


def _provider() -> GeminiProvider:
    return GeminiProvider(api_key="test-key")


def _client_error(code: int) -> ClientError:
    return ClientError(code, {"error": {"message": "boom"}})


def _text_response(
    text: str, prompt_tokens: int = 10, completion_tokens: int = 5
) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(role="model", parts=[types.Part(text=text)]),
                finish_reason=types.FinishReason.STOP,
            )
        ],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=prompt_tokens,
            candidates_token_count=completion_tokens,
            total_token_count=prompt_tokens + completion_tokens,
        ),
    )


def _tool_call_response(name: str, args: dict) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(
                    role="model", parts=[types.Part.from_function_call(name=name, args=args)]
                ),
                finish_reason=types.FinishReason.STOP,
            )
        ],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=10, candidates_token_count=5, total_token_count=15
        ),
    )


class TestIsTransient:
    def test_server_error_is_transient(self) -> None:
        assert _is_transient(ServerError(500, {"error": {"message": "oops"}}))

    def test_rate_limited_client_error_is_transient(self) -> None:
        assert _is_transient(_client_error(429))

    def test_bad_request_client_error_is_not_transient(self) -> None:
        assert not _is_transient(_client_error(400))

    def test_unrelated_exception_is_not_transient(self) -> None:
        assert not _is_transient(ValueError("not an API error"))


class TestConvertTools:
    def test_unwraps_openai_shaped_schema_into_a_gemini_tool(self) -> None:
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web.",
                    "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
                },
            }
        ]
        tool = _convert_tools(tools)
        assert len(tool.function_declarations) == 1
        declaration = tool.function_declarations[0]
        assert declaration.name == "web_search"
        assert declaration.description == "Search the web."
        assert declaration.parameters_json_schema == tools[0]["function"]["parameters"]


class TestConvertMessages:
    def test_extracts_system_messages_separately_from_contents(self) -> None:
        system, contents = _convert_messages(
            [{"role": "system", "content": "You are helpful."}, {"role": "user", "content": "Hi"}]
        )
        assert system == "You are helpful."
        assert len(contents) == 1
        assert contents[0].role == "user"

    def test_assistant_tool_call_and_matching_tool_result_round_trip(self) -> None:
        """The trickiest conversion: our lingua franca's "tool" message only
        carries a tool_call_id, not the function name Gemini needs -- this
        must be recovered from the preceding assistant message."""
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "search for cats"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "web_search", "arguments": '{"query": "cats"}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "cats are great"},
        ]
        system, contents = _convert_messages(messages)

        assert system == "sys"
        assert len(contents) == 3  # user, model (tool call), user (tool result)
        assert contents[0].role == "user"
        assert contents[1].role == "model"
        assert contents[1].parts[0].function_call.name == "web_search"
        assert contents[1].parts[0].function_call.args == {"query": "cats"}
        assert contents[2].role == "user"
        function_response = contents[2].parts[0].function_response
        assert function_response.name == "web_search"  # recovered via call_id_to_name
        assert function_response.response == {"output": "cats are great"}

    def test_promotes_a_system_only_prompt_into_the_sole_user_content(self) -> None:
        """planner/critic/synthesizer send a single system-role message with
        no separate user turn -- Gemini's API rejects a request whose
        `contents` is empty ("contents are required.") even when
        `system_instruction` is set, so this must not leave `contents` empty."""
        system, contents = _convert_messages([{"role": "system", "content": "Do the thing."}])

        assert system is None
        assert len(contents) == 1
        assert contents[0].role == "user"
        assert contents[0].parts[0].text == "Do the thing."

    def test_merges_consecutive_tool_results_into_one_content(self) -> None:
        messages = [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "a", "type": "function", "function": {"name": "f1", "arguments": "{}"}},
                    {"id": "b", "type": "function", "function": {"name": "f2", "arguments": "{}"}},
                ],
            },
            {"role": "tool", "tool_call_id": "a", "content": "result a"},
            {"role": "tool", "tool_call_id": "b", "content": "result b"},
        ]
        _, contents = _convert_messages(messages)

        assert len(contents) == 2  # model turn, then ONE merged user turn with two responses
        assert len(contents[1].parts) == 2


class TestExtractTextAndToolCalls:
    def test_extracts_plain_text(self) -> None:
        text, tool_calls = _extract_text_and_tool_calls(_text_response("hello there"))
        assert text == "hello there"
        assert tool_calls == []

    def test_extracts_tool_calls_with_a_fallback_id_when_none_is_provided(self) -> None:
        text, tool_calls = _extract_text_and_tool_calls(
            _tool_call_response("web_search", {"query": "cats"})
        )
        assert text is None
        assert len(tool_calls) == 1
        assert tool_calls[0].name == "web_search"
        assert tool_calls[0].arguments == {"query": "cats"}
        assert tool_calls[0].id  # some non-empty fallback id was assigned


@pytest.mark.asyncio
class TestChatAndStructured:
    async def test_chat_returns_text_and_usage(self) -> None:
        provider = _provider()
        provider._client.aio.models.generate_content = AsyncMock(return_value=_text_response("hi"))

        result = await provider.chat(model="gemini-2.0-flash", messages=[{"role": "user", "content": "hi"}])

        assert result.content == "hi"
        assert result.usage.total_tokens == 15

    async def test_structured_returns_the_parsed_pydantic_model(self) -> None:
        provider = _provider()
        verdict = _Verdict(ok=True, reason="fine")
        response = _text_response("{}")
        response.parsed = verdict
        provider._client.aio.models.generate_content = AsyncMock(return_value=response)

        result = await provider.structured(
            model="gemini-2.0-flash", messages=[{"role": "user", "content": "x"}], response_model=_Verdict
        )

        assert result.data == verdict
        assert result.repaired is False

    async def test_structured_repairs_once_then_raises_if_still_unparsed(self) -> None:
        provider = _provider()
        unparsed = _text_response("not json")
        unparsed.parsed = None
        provider._client.aio.models.generate_content = AsyncMock(return_value=unparsed)

        with pytest.raises(StructuredOutputError):
            await provider.structured(
                model="gemini-2.0-flash",
                messages=[{"role": "user", "content": "x"}],
                response_model=_Verdict,
            )
        assert provider._client.aio.models.generate_content.call_count == 2

    async def test_validate_succeeds_when_key_is_accepted(self) -> None:
        provider = _provider()

        async def fake_page():
            yield object()

        provider._client.aio.models.list = AsyncMock(return_value=fake_page())

        await provider.validate()

    async def test_validate_raises_invalid_credential_error_on_client_error(self) -> None:
        provider = _provider()
        provider._client.aio.models.list = AsyncMock(side_effect=_client_error(400))

        with pytest.raises(InvalidCredentialError):
            await provider.validate()
