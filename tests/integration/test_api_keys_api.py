import uuid

import pytest

from tests.integration.conftest import bearer_headers


@pytest.mark.asyncio
async def test_create_key_returns_a_usable_raw_key_exactly_once(client, user) -> None:
    response = await client.post(
        "/api/v1/me/api-keys", json={"name": "my script"}, headers=bearer_headers(user)
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "my script"
    raw_key = body["raw_key"]
    assert raw_key.startswith("ra_")

    # The listing never includes the raw key -- only the one creation
    # response does.
    listing = await client.get("/api/v1/me/api-keys", headers=bearer_headers(user))
    assert "raw_key" not in listing.json()[0]

    # And the returned key genuinely authenticates.
    me_response = await client.get("/api/v1/auth/me", headers={"X-API-Key": raw_key})
    assert me_response.status_code == 200
    assert me_response.json()["email"] == user.email


@pytest.mark.asyncio
async def test_list_keys_only_shows_the_caller_own_keys(client, user) -> None:
    await client.post("/api/v1/me/api-keys", json={"name": "mine"}, headers=bearer_headers(user))

    signup = await client.post(
        "/api/v1/auth/signup",
        json={"email": "other-key-user@example.com", "password": "correct horse battery staple"},
    )
    other_headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}

    listing = await client.get("/api/v1/me/api-keys", headers=other_headers)
    assert listing.json() == []


@pytest.mark.asyncio
async def test_revoked_key_can_no_longer_authenticate(client, user) -> None:
    create_response = await client.post(
        "/api/v1/me/api-keys", json={"name": "temporary"}, headers=bearer_headers(user)
    )
    key_id = create_response.json()["id"]
    raw_key = create_response.json()["raw_key"]

    revoke_response = await client.delete(f"/api/v1/me/api-keys/{key_id}", headers=bearer_headers(user))
    assert revoke_response.status_code == 204

    me_response = await client.get("/api/v1/auth/me", headers={"X-API-Key": raw_key})
    assert me_response.status_code == 401


@pytest.mark.asyncio
async def test_revoke_unknown_key_returns_404(client, user) -> None:
    response = await client.delete(f"/api/v1/me/api-keys/{uuid.uuid4()}", headers=bearer_headers(user))
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_api_keys_endpoints_require_authentication(client) -> None:
    response = await client.get("/api/v1/me/api-keys")
    assert response.status_code == 401
