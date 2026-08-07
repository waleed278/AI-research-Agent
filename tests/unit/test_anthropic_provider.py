from unittest.mock import AsyncMock

import httpx
import pytest
from anthropic import AuthenticationError
from anthropic.types import Message, TextBlock, ToolUseBlock, Usage
from pydantic import BaseModel

from app.llm.base import InvalidCredentialError
from app.llm.providers.anthropic_provider import (
    AnthropicProvider,
    StructuredOutputError,
    _convert_messages,
    _convert_tools,
    _extract_text_and_tool_calls,
)


class _Verdict(BaseModel):
    ok: bool
    reason: str


def _provider() -> AnthropicProvider:
    return AnthropicProvider(api_key="test-key")


def _dummy_request() -> httpx.Request:
    return httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def _text_message(text: str, prompt_tokens: int = 10, completion_tokens: int = 5) -> Message:
    return Message(
        id="msg_1",
        type="message",
        role="assistant",
        model="claude-sonnet-5",
        content=[TextBlock(type="text", text=text)],
        stop_reason="end_turn",
        stop_sequence=None,
        usage=Usage(input_tokens=prompt_tokens, output_tokens=completion_tokens),
    )


def _tool_use_message(name: str, input_: dict, tool_id: str = "call_1") -> Message:
    return Message(
        id="msg_2",
        type="message",
        role="assistant",
        model="claude-sonnet-5",
        content=[ToolUseBlock(type="tool_use", id=tool_id, name=name, input=input_)],
        stop_reason="tool_use",
        stop_sequence=None,
        usage=Usage(input_tokens=10, output_tokens=5),
    )


class TestConvertTools:
    def test_converts_openai_shaped_schema_to_anthropic_tool_param(self) -> None:
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
        converted = _convert_tools(tools)
        assert converted == [
            {
                "name": "web_search",
                "description": "Search the web.",
                "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
            }
        ]


class TestConvertMessages:
    def test_extracts_system_and_converts_plain_user_message(self) -> None:
        system, converted = _convert_messages(
            [{"role": "system", "content": "You are helpful."}, {"role": "user", "content": "Hi"}]
        )
        assert system == "You are helpful."
        assert converted == [{"role": "user", "content": "Hi"}]

    def test_assistant_tool_call_becomes_a_tool_use_content_block(self) -> None:
        messages = [
            {
                "role": "assistant",
                "content": "Let me check.",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "web_search", "arguments": '{"query": "cats"}'},
                    }
                ],
            }
        ]
        _, converted = _convert_messages(messages)

        assert converted == [
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Let me check."},
                    {"type": "tool_use", "id": "call_1", "name": "web_search", "input": {"query": "cats"}},
                ],
            }
        ]

    def test_merges_consecutive_tool_results_into_a_single_user_message(self) -> None:
        """Anthropic requires every tool_result for one assistant turn to
        arrive batched in a single following user message -- sending them
        as separate messages (as our lingua franca naturally produces one
        per tool call) is invalid for this API specifically."""
        messages = [
            {"role": "tool", "tool_call_id": "a", "content": "result a"},
            {"role": "tool", "tool_call_id": "b", "content": "result b"},
        ]
        _, converted = _convert_messages(messages)

        assert len(converted) == 1
        assert converted[0]["role"] == "user"
        assert converted[0]["content"] == [
            {"type": "tool_result", "tool_use_id": "a", "content": "result a"},
            {"type": "tool_result", "tool_use_id": "b", "content": "result b"},
        ]


class TestExtractTextAndToolCalls:
    def test_extracts_plain_text(self) -> None:
        text, tool_calls = _extract_text_and_tool_calls(_text_message("hello"))
        assert text == "hello"
        assert tool_calls == []

    def test_extracts_tool_use_blocks(self) -> None:
        text, tool_calls = _extract_text_and_tool_calls(
            _tool_use_message("web_search", {"query": "cats"})
        )
        assert text is None
        assert len(tool_calls) == 1
        assert tool_calls[0].id == "call_1"
        assert tool_calls[0].name == "web_search"
        assert tool_calls[0].arguments == {"query": "cats"}


@pytest.mark.asyncio
class TestChatAndStructured:
    async def test_chat_returns_text_and_usage(self) -> None:
        provider = _provider()
        provider._client.messages.create = AsyncMock(return_value=_text_message("hi"))

        result = await provider.chat(model="claude-sonnet-5", messages=[{"role": "user", "content": "hi"}])

        assert result.content == "hi"
        assert result.usage.total_tokens == 15
        assert result.finish_reason == "end_turn"

    async def test_structured_returns_the_validated_pydantic_model_from_the_forced_tool_call(self) -> None:
        provider = _provider()
        provider._client.messages.create = AsyncMock(
            return_value=_tool_use_message("emit_result", {"ok": True, "reason": "fine"})
        )

        result = await provider.structured(
            model="claude-sonnet-5", messages=[{"role": "user", "content": "x"}], response_model=_Verdict
        )

        assert result.data == _Verdict(ok=True, reason="fine")
        assert result.repaired is False

    async def test_structured_repairs_once_when_tool_input_fails_validation(self) -> None:
        provider = _provider()
        provider._client.messages.create = AsyncMock(
            side_effect=[
                _tool_use_message("emit_result", {"ok": "not-a-bool"}),  # fails Pydantic validation
                _tool_use_message("emit_result", {"ok": True, "reason": "fixed"}),
            ]
        )

        result = await provider.structured(
            model="claude-sonnet-5", messages=[{"role": "user", "content": "x"}], response_model=_Verdict
        )

        assert result.data == _Verdict(ok=True, reason="fixed")
        assert result.repaired is True
        assert provider._client.messages.create.call_count == 2

    async def test_structured_raises_after_repair_still_fails(self) -> None:
        provider = _provider()
        provider._client.messages.create = AsyncMock(
            return_value=_text_message("I cannot produce that")  # no tool_use block at all
        )

        with pytest.raises(StructuredOutputError):
            await provider.structured(
                model="claude-sonnet-5",
                messages=[{"role": "user", "content": "x"}],
                response_model=_Verdict,
            )

    async def test_validate_succeeds_when_key_is_accepted(self) -> None:
        provider = _provider()

        async def fake_page():
            yield object()

        provider._client.models.list = lambda: fake_page()

        await provider.validate()

    async def test_validate_raises_invalid_credential_error_when_key_is_rejected(self) -> None:
        provider = _provider()
        error = AuthenticationError(
            "invalid key", response=httpx.Response(401, request=_dummy_request()), body=None
        )

        async def failing_page():
            raise error
            yield  # pragma: no cover

        provider._client.models.list = lambda: failing_page()

        with pytest.raises(InvalidCredentialError):
            await provider.validate()
