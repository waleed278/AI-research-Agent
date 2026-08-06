import asyncio
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from openai import APITimeoutError, RateLimitError
from pydantic import BaseModel

from app.core.config import Settings
from app.llm.client import LLMClient, StructuredOutputError
from tests.conftest import fake_openai_chat_completion, fake_openai_parsed_completion


class _Verdict(BaseModel):
    ok: bool
    reason: str


@pytest.fixture(autouse=True)
def _no_real_sleeping(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tenacity's async retrying sleeps between attempts via asyncio.sleep --
    patched to a no-op so retry tests run instantly instead of waiting out
    real exponential backoff."""

    async def instant_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", instant_sleep)


def _client() -> LLMClient:
    return LLMClient(Settings(openai_api_key="test-key"))


def _dummy_request() -> httpx.Request:
    return httpx.Request("POST", "https://api.openai.com/v1/chat/completions")


@pytest.mark.asyncio
async def test_chat_retries_on_rate_limit_then_succeeds() -> None:
    client = _client()
    success = fake_openai_chat_completion(content="hello")
    mock_create: Any = AsyncMock(
        side_effect=[
            RateLimitError("rate limited", response=httpx.Response(429, request=_dummy_request()), body=None),
            success,
        ]
    )
    client._client.chat.completions.create = mock_create

    result = await client.chat(model="gpt-4o-mini", messages=[{"role": "user", "content": "hi"}])

    assert result.content == "hello"
    assert mock_create.call_count == 2


@pytest.mark.asyncio
async def test_chat_gives_up_after_exhausting_retries() -> None:
    client = _client()
    mock_create: Any = AsyncMock(side_effect=APITimeoutError(request=_dummy_request()))
    client._client.chat.completions.create = mock_create

    with pytest.raises(APITimeoutError):
        await client.chat(model="gpt-4o-mini", messages=[{"role": "user", "content": "hi"}])

    assert mock_create.call_count == 4  # stop_after_attempt(4)


@pytest.mark.asyncio
async def test_structured_returns_validated_pydantic_model() -> None:
    client = _client()
    verdict = _Verdict(ok=True, reason="looks fine")
    client._client.chat.completions.parse = AsyncMock(
        return_value=fake_openai_parsed_completion(parsed=verdict)
    )

    result = await client.structured(
        model="gpt-4o", messages=[{"role": "system", "content": "x"}], response_model=_Verdict
    )

    assert result.data == verdict
    assert result.repaired is False


@pytest.mark.asyncio
async def test_structured_repairs_once_on_incomplete_response() -> None:
    client = _client()
    verdict = _Verdict(ok=False, reason="needs more evidence")
    mock_parse: Any = AsyncMock(
        side_effect=[
            fake_openai_parsed_completion(parsed=None, finish_reason="length"),
            fake_openai_parsed_completion(parsed=verdict),
        ]
    )
    client._client.chat.completions.parse = mock_parse

    result = await client.structured(
        model="gpt-4o", messages=[{"role": "system", "content": "x"}], response_model=_Verdict
    )

    assert result.data == verdict
    assert result.repaired is True
    assert mock_parse.call_count == 2


@pytest.mark.asyncio
async def test_structured_raises_after_repair_still_fails() -> None:
    client = _client()
    client._client.chat.completions.parse = AsyncMock(
        return_value=fake_openai_parsed_completion(parsed=None, finish_reason="length")
    )

    with pytest.raises(StructuredOutputError):
        await client.structured(
            model="gpt-4o", messages=[{"role": "system", "content": "x"}], response_model=_Verdict
        )


@pytest.mark.asyncio
async def test_structured_raises_on_refusal_without_retry() -> None:
    client = _client()
    mock_parse: Any = AsyncMock(
        return_value=fake_openai_parsed_completion(parsed=None, refusal="cannot comply")
    )
    client._client.chat.completions.parse = mock_parse

    with pytest.raises(StructuredOutputError, match="refused"):
        await client.structured(
            model="gpt-4o", messages=[{"role": "system", "content": "x"}], response_model=_Verdict
        )

    assert mock_parse.call_count == 1
