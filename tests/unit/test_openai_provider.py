import asyncio
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from openai import APITimeoutError, AuthenticationError, RateLimitError
from pydantic import BaseModel

from app.llm.base import InvalidCredentialError
from app.llm.providers.openai_provider import OpenAIProvider, StructuredOutputError
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


def _provider() -> OpenAIProvider:
    return OpenAIProvider(api_key="test-key")


def _dummy_request() -> httpx.Request:
    return httpx.Request("POST", "https://api.openai.com/v1/chat/completions")


@pytest.mark.asyncio
async def test_chat_retries_on_rate_limit_then_succeeds() -> None:
    provider = _provider()
    success = fake_openai_chat_completion(content="hello")
    mock_create: Any = AsyncMock(
        side_effect=[
            RateLimitError("rate limited", response=httpx.Response(429, request=_dummy_request()), body=None),
            success,
        ]
    )
    provider._client.chat.completions.create = mock_create

    result = await provider.chat(model="gpt-4o-mini", messages=[{"role": "user", "content": "hi"}])

    assert result.content == "hello"
    assert mock_create.call_count == 2


@pytest.mark.asyncio
async def test_chat_gives_up_after_exhausting_retries() -> None:
    provider = _provider()
    mock_create: Any = AsyncMock(side_effect=APITimeoutError(request=_dummy_request()))
    provider._client.chat.completions.create = mock_create

    with pytest.raises(APITimeoutError):
        await provider.chat(model="gpt-4o-mini", messages=[{"role": "user", "content": "hi"}])

    assert mock_create.call_count == 4  # stop_after_attempt(4)


@pytest.mark.asyncio
async def test_structured_returns_validated_pydantic_model() -> None:
    provider = _provider()
    verdict = _Verdict(ok=True, reason="looks fine")
    provider._client.chat.completions.parse = AsyncMock(
        return_value=fake_openai_parsed_completion(parsed=verdict)
    )

    result = await provider.structured(
        model="gpt-4o", messages=[{"role": "system", "content": "x"}], response_model=_Verdict
    )

    assert result.data == verdict
    assert result.repaired is False


@pytest.mark.asyncio
async def test_structured_repairs_once_on_incomplete_response() -> None:
    provider = _provider()
    verdict = _Verdict(ok=False, reason="needs more evidence")
    mock_parse: Any = AsyncMock(
        side_effect=[
            fake_openai_parsed_completion(parsed=None, finish_reason="length"),
            fake_openai_parsed_completion(parsed=verdict),
        ]
    )
    provider._client.chat.completions.parse = mock_parse

    result = await provider.structured(
        model="gpt-4o", messages=[{"role": "system", "content": "x"}], response_model=_Verdict
    )

    assert result.data == verdict
    assert result.repaired is True
    assert mock_parse.call_count == 2


@pytest.mark.asyncio
async def test_structured_raises_after_repair_still_fails() -> None:
    provider = _provider()
    provider._client.chat.completions.parse = AsyncMock(
        return_value=fake_openai_parsed_completion(parsed=None, finish_reason="length")
    )

    with pytest.raises(StructuredOutputError):
        await provider.structured(
            model="gpt-4o", messages=[{"role": "system", "content": "x"}], response_model=_Verdict
        )


@pytest.mark.asyncio
async def test_structured_raises_on_refusal_without_retry() -> None:
    provider = _provider()
    mock_parse: Any = AsyncMock(
        return_value=fake_openai_parsed_completion(parsed=None, refusal="cannot comply")
    )
    provider._client.chat.completions.parse = mock_parse

    with pytest.raises(StructuredOutputError, match="refused"):
        await provider.structured(
            model="gpt-4o", messages=[{"role": "system", "content": "x"}], response_model=_Verdict
        )

    assert mock_parse.call_count == 1


@pytest.mark.asyncio
async def test_validate_succeeds_when_the_key_is_accepted() -> None:
    provider = _provider()

    async def fake_page():
        yield object()

    # `models.list()` on the real SDK returns an async-iterable page
    # directly (confirmed by exercising it live against a bad key) rather
    # than a coroutine to await first -- a plain callable matches that,
    # where AsyncMock would instead wrap the return value in a coroutine.
    provider._client.models.list = lambda: fake_page()

    await provider.validate()  # raises on failure; no exception here means success


@pytest.mark.asyncio
async def test_validate_raises_invalid_credential_error_when_the_key_is_rejected() -> None:
    provider = _provider()
    error = AuthenticationError(
        "invalid key", response=httpx.Response(401, request=_dummy_request()), body=None
    )

    async def failing_page():
        raise error
        yield  # pragma: no cover - makes this a generator function; never reached

    # See test_validate_succeeds_when_the_key_is_accepted: `.list()` returns
    # the async-iterable directly, so the error must surface on iteration
    # (`__anext__`), not at the call itself -- a plain callable models this,
    # not AsyncMock(side_effect=...), which raises at await-time on a
    # coroutine our code never awaits.
    provider._client.models.list = lambda: failing_page()

    with pytest.raises(InvalidCredentialError):
        await provider.validate()
