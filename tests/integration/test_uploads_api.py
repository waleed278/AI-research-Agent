import uuid

import pytest
from sqlalchemy import select

from app.db.models import UploadedFile
from tests.integration.conftest import bearer_headers


@pytest.mark.asyncio
async def test_upload_a_text_file_returns_extracted_char_count(client, user) -> None:
    response = await client.post(
        "/api/v1/uploads",
        files={"file": ("notes.txt", b"some research notes", "text/plain")},
        headers=bearer_headers(user),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "notes.txt"
    assert body["extracted_chars"] == len("some research notes")


@pytest.mark.asyncio
async def test_upload_rejects_a_disallowed_extension(client, user) -> None:
    response = await client.post(
        "/api/v1/uploads",
        files={"file": ("virus.exe", b"whatever", "application/octet-stream")},
        headers=bearer_headers(user),
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_upload_requires_authentication(client) -> None:
    response = await client.post(
        "/api/v1/uploads", files={"file": ("notes.txt", b"hi", "text/plain")}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_attaching_an_upload_to_a_job_links_it_and_seeds_it_as_a_source(
    client, user, api_key, llm_credential, db_session, monkeypatch
) -> None:
    """End-to-end wiring check: upload -> reference by id at job creation ->
    the row is linked (job_id set) -- the actual evidence-seeding into the
    agent's EvidenceStore is covered at the unit level
    (test_orchestrator.py); this confirms the plumbing between them."""
    _, raw_key = api_key
    upload_response = await client.post(
        "/api/v1/uploads",
        files={"file": ("research.txt", b"important background info", "text/plain")},
        headers={"X-API-Key": raw_key},
    )
    upload_id = upload_response.json()["id"]

    create_response = await client.post(
        "/api/v1/research-jobs",
        json={
            "query": "What causes the northern lights?",
            "provider": "openai",
            "attachment_ids": [upload_id],
        },
        headers={"X-API-Key": raw_key},
    )
    assert create_response.status_code == 202
    job_id = create_response.json()["id"]

    stored = (
        await db_session.execute(select(UploadedFile).where(UploadedFile.id == uuid.UUID(upload_id)))
    ).scalar_one()
    assert str(stored.job_id) == job_id


@pytest.mark.asyncio
async def test_attaching_someone_elses_upload_is_silently_ignored(
    client, user, api_key, llm_credential, db_session
) -> None:
    """`get_owned_many` drops ids that don't belong to the caller (see
    app/db/repositories.py) -- a job creation request can't be used to
    exfiltrate or attach another account's uploaded file by guessing its id."""
    _, raw_key = api_key

    other_signup = await client.post(
        "/api/v1/auth/signup",
        json={"email": "other-upload-user@example.com", "password": "correct horse battery staple"},
    )
    other_user_headers = {"Authorization": f"Bearer {other_signup.json()['access_token']}"}
    other_upload = await client.post(
        "/api/v1/uploads",
        files={"file": ("secret.txt", b"not yours", "text/plain")},
        headers=other_user_headers,
    )
    other_upload_id = other_upload.json()["id"]

    create_response = await client.post(
        "/api/v1/research-jobs",
        json={
            "query": "What causes the northern lights?",
            "provider": "openai",
            "attachment_ids": [other_upload_id],
        },
        headers={"X-API-Key": raw_key},
    )
    assert create_response.status_code == 202

    stored = (
        await db_session.execute(
            select(UploadedFile).where(UploadedFile.id == uuid.UUID(other_upload_id))
        )
    ).scalar_one()
    assert stored.job_id is None  # never attached, since it wasn't the caller's file
