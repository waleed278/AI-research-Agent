import uuid

import pytest

from app.llm.base import InvalidCredentialError
from tests.integration.conftest import bearer_headers


class _FakeValidatingProvider:
    """Stands in for a real provider adapter during `validate()` -- the
    credentials API's whole job is to call a live provider before trusting
    a key, so tests substitute the outcome of that call rather than the key
    material itself."""

    def __init__(self, *, should_succeed: bool) -> None:
        self._should_succeed = should_succeed

    async def validate(self) -> None:
        if not self._should_succeed:
            raise InvalidCredentialError("this key does not work")


def _patch_validation(monkeypatch: pytest.MonkeyPatch, *, should_succeed: bool) -> None:
    monkeypatch.setattr(
        "app.services.credentials_service.build_provider",
        lambda *args, **kwargs: _FakeValidatingProvider(should_succeed=should_succeed),
    )


@pytest.mark.asyncio
async def test_add_credential_succeeds_when_the_provider_accepts_the_key(client, user, monkeypatch) -> None:
    _patch_validation(monkeypatch, should_succeed=True)

    response = await client.post(
        "/api/v1/me/llm-credentials",
        json={"provider": "openai", "api_key": "sk-whatever", "label": "personal"},
        headers=bearer_headers(user),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["provider"] == "openai"
    assert body["label"] == "personal"
    assert body["is_valid"] is True
    assert "api_key" not in body  # the key itself, encrypted or not, is never echoed back


@pytest.mark.asyncio
async def test_add_credential_is_rejected_when_the_provider_rejects_the_key(
    client, user, monkeypatch
) -> None:
    _patch_validation(monkeypatch, should_succeed=False)

    response = await client.post(
        "/api/v1/me/llm-credentials",
        json={"provider": "gemini", "api_key": "not-a-real-key"},
        headers=bearer_headers(user),
    )

    assert response.status_code == 422
    assert "does not work" in response.json()["detail"]


@pytest.mark.asyncio
async def test_adding_a_second_credential_for_the_same_provider_replaces_the_first(
    client, user, monkeypatch
) -> None:
    _patch_validation(monkeypatch, should_succeed=True)

    first = await client.post(
        "/api/v1/me/llm-credentials",
        json={"provider": "openai", "api_key": "sk-first", "label": "first"},
        headers=bearer_headers(user),
    )
    second = await client.post(
        "/api/v1/me/llm-credentials",
        json={"provider": "openai", "api_key": "sk-second", "label": "second"},
        headers=bearer_headers(user),
    )
    assert first.json()["id"] == second.json()["id"]  # upserted, not duplicated

    listing = await client.get("/api/v1/me/llm-credentials", headers=bearer_headers(user))
    openai_credentials = [c for c in listing.json() if c["provider"] == "openai"]
    assert len(openai_credentials) == 1
    assert openai_credentials[0]["label"] == "second"


@pytest.mark.asyncio
async def test_list_credentials_only_shows_the_caller_own_credentials(client, user, monkeypatch) -> None:
    _patch_validation(monkeypatch, should_succeed=True)
    await client.post(
        "/api/v1/me/llm-credentials",
        json={"provider": "openai", "api_key": "sk-mine"},
        headers=bearer_headers(user),
    )

    other_response = await client.post("/api/v1/auth/signup", json={
        "email": "other-cred-user@example.com", "password": "correct horse battery staple"
    })
    other_headers = {"Authorization": f"Bearer {other_response.json()['access_token']}"}

    listing = await client.get("/api/v1/me/llm-credentials", headers=other_headers)
    assert listing.json() == []


@pytest.mark.asyncio
async def test_delete_credential_removes_it(client, user, monkeypatch) -> None:
    _patch_validation(monkeypatch, should_succeed=True)
    created = await client.post(
        "/api/v1/me/llm-credentials",
        json={"provider": "anthropic", "api_key": "sk-ant-whatever"},
        headers=bearer_headers(user),
    )
    credential_id = created.json()["id"]

    delete_response = await client.delete(
        f"/api/v1/me/llm-credentials/{credential_id}", headers=bearer_headers(user)
    )
    assert delete_response.status_code == 204

    listing = await client.get("/api/v1/me/llm-credentials", headers=bearer_headers(user))
    assert listing.json() == []


@pytest.mark.asyncio
async def test_delete_unknown_credential_returns_404(client, user) -> None:
    response = await client.delete(
        f"/api/v1/me/llm-credentials/{uuid.uuid4()}", headers=bearer_headers(user)
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_credentials_endpoints_require_authentication(client) -> None:
    response = await client.get("/api/v1/me/llm-credentials")
    assert response.status_code == 401
