import uuid

import pytest

from app.agent.state import CriticVerdict, PlannerOutput, SubQuestion, SynthesizerOutput
from app.core.config import get_settings
from app.core.crypto import encrypt_secret
from app.core.security import generate_api_key, hash_api_key, hash_password
from app.db.models import ApiKey, JobStatus, LlmCredential, LlmProvider, User
from app.llm.schemas import ChatResult
from app.workers.worker import run_research_job
from tests.conftest import FakeLLMClient, make_usage
from tests.integration.conftest import bearer_headers

JOB_PAYLOAD = {"query": "What causes the northern lights?", "provider": "openai"}


def _auth(raw_key: str) -> dict[str, str]:
    return {"X-API-Key": raw_key}


def _patch_worker_llm(monkeypatch: pytest.MonkeyPatch, fake_llm: FakeLLMClient) -> None:
    """`run_research_job` builds a real provider client from the job's
    decrypted BYOK credential (see app/workers/worker.py) -- there's no
    `ctx["llm"]` override anymore now that the worker is multi-tenant, so
    tests substitute the provider factory itself instead."""
    monkeypatch.setattr("app.workers.worker.build_provider", lambda *args, **kwargs: fake_llm)


def _happy_path_llm() -> FakeLLMClient:
    fake_llm = FakeLLMClient()
    fake_llm.queue_structured(
        "PlannerOutput", PlannerOutput(sub_questions=[SubQuestion(question="q1", rationale="r")])
    )
    fake_llm.queue_chat(
        ChatResult(content="done", tool_calls=[], usage=make_usage(), cost_usd=0.0, finish_reason="stop")
    )
    fake_llm.queue_structured(
        "CriticVerdict",
        CriticVerdict(coverage_ok=True, grounding_ok=True, gaps=[], revise_queries=[], rationale="fine"),
    )
    fake_llm.queue_structured(
        "SynthesizerOutput",
        SynthesizerOutput(report_markdown="# Northern Lights\n\nCharged solar particles."),
    )
    return fake_llm


@pytest.mark.asyncio
async def test_create_job_requires_authentication(client) -> None:
    response = await client.post("/api/v1/research-jobs", json=JOB_PAYLOAD)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_job_rejects_too_short_query(client, api_key, llm_credential) -> None:
    _, raw_key = api_key
    response = await client.post(
        "/api/v1/research-jobs",
        json={"query": "hi", "provider": "openai"},
        headers=_auth(raw_key),
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_job_requires_a_configured_credential_for_the_provider(client, api_key) -> None:
    """No `llm_credential` fixture here -- the account has never added an
    OpenAI key, so job creation must be rejected up front rather than
    queueing a job that would only fail once the worker picks it up."""
    _, raw_key = api_key
    response = await client.post("/api/v1/research-jobs", json=JOB_PAYLOAD, headers=_auth(raw_key))
    assert response.status_code == 422
    assert "credential" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_job_rejects_a_model_not_supported_by_the_provider(
    client, api_key, llm_credential
) -> None:
    _, raw_key = api_key
    response = await client.post(
        "/api/v1/research-jobs",
        json={**JOB_PAYLOAD, "model": "not-a-real-model"},
        headers=_auth(raw_key),
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_unknown_job_returns_404(client, api_key) -> None:
    _, raw_key = api_key
    response = await client.get(f"/api/v1/research-jobs/{uuid.uuid4()}", headers=_auth(raw_key))
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_full_job_lifecycle_create_run_and_fetch(client, api_key, llm_credential, monkeypatch) -> None:
    """The core end-to-end contract: create a job over HTTP, let the worker
    (invoked directly here, standing in for a real arq process) run the
    orchestrator against it, then confirm the API surfaces the completed
    report with its sources."""
    _patch_worker_llm(monkeypatch, _happy_path_llm())
    _, raw_key = api_key
    create_response = await client.post(
        "/api/v1/research-jobs",
        json={**JOB_PAYLOAD, "max_iterations": 4, "max_sources": 5},
        headers=_auth(raw_key),
    )
    assert create_response.status_code == 202
    body = create_response.json()
    assert body["status"] == "queued"
    job_id = body["id"]

    await run_research_job({}, job_id=job_id)

    get_response = await client.get(f"/api/v1/research-jobs/{job_id}", headers=_auth(raw_key))
    assert get_response.status_code == 200
    result = get_response.json()
    assert result["status"] == JobStatus.COMPLETED.value
    assert result["llm_provider"] == "openai"
    assert result["result"]["report_markdown"].startswith("# Northern Lights")
    assert result["total_tokens"] > 0


@pytest.mark.asyncio
async def test_a_bearer_token_authenticates_the_same_as_an_api_key(client, user, llm_credential) -> None:
    """The web app and programmatic API-key access are two doors to the
    same account -- see app/api/deps.py::get_current_user."""
    create_response = await client.post(
        "/api/v1/research-jobs", json=JOB_PAYLOAD, headers=bearer_headers(user)
    )
    assert create_response.status_code == 202

    get_response = await client.get(
        f"/api/v1/research-jobs/{create_response.json()['id']}", headers=bearer_headers(user)
    )
    assert get_response.status_code == 200


@pytest.mark.asyncio
async def test_failed_job_reports_error_and_does_not_crash_api(
    client, api_key, llm_credential, monkeypatch
) -> None:
    _patch_worker_llm(monkeypatch, FakeLLMClient())  # no queued responses -> planner call raises
    _, raw_key = api_key
    create_response = await client.post(
        "/api/v1/research-jobs", json=JOB_PAYLOAD, headers=_auth(raw_key)
    )
    job_id = create_response.json()["id"]

    await run_research_job({}, job_id=job_id)

    get_response = await client.get(f"/api/v1/research-jobs/{job_id}", headers=_auth(raw_key))
    result = get_response.json()
    assert result["status"] == JobStatus.FAILED.value
    assert result["error"]


@pytest.mark.asyncio
async def test_cancel_queued_job(client, api_key, llm_credential) -> None:
    _, raw_key = api_key
    create_response = await client.post(
        "/api/v1/research-jobs", json=JOB_PAYLOAD, headers=_auth(raw_key)
    )
    job_id = create_response.json()["id"]

    cancel_response = await client.delete(f"/api/v1/research-jobs/{job_id}", headers=_auth(raw_key))
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == JobStatus.CANCELLED.value


@pytest.mark.asyncio
async def test_cancelling_a_running_job_is_rejected(client, api_key, llm_credential, monkeypatch) -> None:
    _patch_worker_llm(monkeypatch, _happy_path_llm())
    _, raw_key = api_key
    create_response = await client.post(
        "/api/v1/research-jobs", json=JOB_PAYLOAD, headers=_auth(raw_key)
    )
    job_id = create_response.json()["id"]

    await run_research_job({}, job_id=job_id)

    cancel_response = await client.delete(f"/api/v1/research-jobs/{job_id}", headers=_auth(raw_key))
    assert cancel_response.status_code == 409


@pytest.mark.asyncio
async def test_list_jobs_only_returns_caller_own_jobs(client, api_key, llm_credential, db_session) -> None:
    _, raw_key = api_key

    other_user = User(
        id=uuid.uuid4(), email="other-user@example.com", password_hash=hash_password("irrelevant")
    )
    db_session.add(other_user)
    await db_session.flush()
    other_key_raw = generate_api_key()
    db_session.add(
        ApiKey(id=uuid.uuid4(), user_id=other_user.id, name="other", key_hash=hash_api_key(other_key_raw))
    )
    db_session.add(
        LlmCredential(
            id=uuid.uuid4(),
            user_id=other_user.id,
            provider=LlmProvider.OPENAI,
            encrypted_key=encrypt_secret("sk-other-not-real"),
            is_valid=True,
        )
    )
    await db_session.commit()

    await client.post(
        "/api/v1/research-jobs",
        json={**JOB_PAYLOAD, "query": "my own research question"},
        headers=_auth(raw_key),
    )
    await client.post(
        "/api/v1/research-jobs",
        json={**JOB_PAYLOAD, "query": "someone else's research question"},
        headers=_auth(other_key_raw),
    )

    listing = await client.get("/api/v1/research-jobs", headers=_auth(raw_key))
    items = listing.json()["items"]
    assert len(items) == 1
    assert items[0]["query"] == "my own research question"


@pytest.mark.asyncio
async def test_rate_limit_kicks_in_after_configured_threshold(client, api_key, llm_credential) -> None:
    _, raw_key = api_key
    limit = get_settings().api_key_rate_limit_per_minute

    statuses = [
        (
            await client.post(
                "/api/v1/research-jobs",
                json={**JOB_PAYLOAD, "query": "A sufficiently long research query text."},
                headers=_auth(raw_key),
            )
        ).status_code
        for _ in range(limit + 2)
    ]

    assert statuses.count(429) >= 1
