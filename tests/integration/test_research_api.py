import uuid

import pytest

from app.agent.state import CriticVerdict, PlannerOutput, SubQuestion, SynthesizerOutput
from app.core.config import get_settings
from app.db.models import JobStatus
from app.llm.schemas import ChatResult
from app.workers.worker import run_research_job
from tests.conftest import FakeLLMClient, make_usage


def _auth(raw_key: str) -> dict[str, str]:
    return {"X-API-Key": raw_key}


@pytest.mark.asyncio
async def test_create_job_requires_api_key(client) -> None:
    response = await client.post("/api/v1/research-jobs", json={"query": "why is the sky blue"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_job_rejects_too_short_query(client, api_key) -> None:
    _, raw_key = api_key
    response = await client.post(
        "/api/v1/research-jobs", json={"query": "hi"}, headers=_auth(raw_key)
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_unknown_job_returns_404(client, api_key) -> None:
    _, raw_key = api_key
    response = await client.get(f"/api/v1/research-jobs/{uuid.uuid4()}", headers=_auth(raw_key))
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_full_job_lifecycle_create_run_and_fetch(client, api_key) -> None:
    """The core end-to-end contract: create a job over HTTP, let the worker
    (invoked directly here, standing in for a real arq process) run the
    orchestrator against it, then confirm the API surfaces the completed
    report with its sources."""
    _, raw_key = api_key
    create_response = await client.post(
        "/api/v1/research-jobs",
        json={"query": "What causes the northern lights?", "max_iterations": 4, "max_sources": 5},
        headers=_auth(raw_key),
    )
    assert create_response.status_code == 202
    body = create_response.json()
    assert body["status"] == "queued"
    job_id = body["id"]

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

    await run_research_job({"llm": fake_llm}, job_id=job_id)

    get_response = await client.get(f"/api/v1/research-jobs/{job_id}", headers=_auth(raw_key))
    assert get_response.status_code == 200
    result = get_response.json()
    assert result["status"] == JobStatus.COMPLETED.value
    assert result["result"]["report_markdown"].startswith("# Northern Lights")
    assert result["total_tokens"] > 0


@pytest.mark.asyncio
async def test_failed_job_reports_error_and_does_not_crash_api(client, api_key) -> None:
    _, raw_key = api_key
    create_response = await client.post(
        "/api/v1/research-jobs",
        json={"query": "What causes the northern lights?"},
        headers=_auth(raw_key),
    )
    job_id = create_response.json()["id"]

    fake_llm = FakeLLMClient()  # no queued responses -> planner call raises AssertionError

    await run_research_job({"llm": fake_llm}, job_id=job_id)

    get_response = await client.get(f"/api/v1/research-jobs/{job_id}", headers=_auth(raw_key))
    result = get_response.json()
    assert result["status"] == JobStatus.FAILED.value
    assert result["error"]


@pytest.mark.asyncio
async def test_cancel_queued_job(client, api_key) -> None:
    _, raw_key = api_key
    create_response = await client.post(
        "/api/v1/research-jobs",
        json={"query": "What causes the northern lights?"},
        headers=_auth(raw_key),
    )
    job_id = create_response.json()["id"]

    cancel_response = await client.delete(f"/api/v1/research-jobs/{job_id}", headers=_auth(raw_key))
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == JobStatus.CANCELLED.value


@pytest.mark.asyncio
async def test_cancelling_a_running_job_is_rejected(client, api_key) -> None:
    _, raw_key = api_key
    create_response = await client.post(
        "/api/v1/research-jobs",
        json={"query": "What causes the northern lights?"},
        headers=_auth(raw_key),
    )
    job_id = create_response.json()["id"]

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
    fake_llm.queue_structured("SynthesizerOutput", SynthesizerOutput(report_markdown="# Done"))
    await run_research_job({"llm": fake_llm}, job_id=job_id)

    cancel_response = await client.delete(f"/api/v1/research-jobs/{job_id}", headers=_auth(raw_key))
    assert cancel_response.status_code == 409


@pytest.mark.asyncio
async def test_list_jobs_only_returns_caller_own_jobs(client, api_key, db_session) -> None:
    from app.core.security import generate_api_key, hash_api_key
    from app.db.models import ApiKey

    _, raw_key = api_key
    other_key_raw = generate_api_key()
    other_key = ApiKey(id=uuid.uuid4(), name="other", key_hash=hash_api_key(other_key_raw))
    db_session.add(other_key)
    await db_session.commit()

    await client.post(
        "/api/v1/research-jobs", json={"query": "my own research question"}, headers=_auth(raw_key)
    )
    await client.post(
        "/api/v1/research-jobs",
        json={"query": "someone else's research question"},
        headers=_auth(other_key_raw),
    )

    listing = await client.get("/api/v1/research-jobs", headers=_auth(raw_key))
    items = listing.json()["items"]
    assert len(items) == 1
    assert items[0]["query"] == "my own research question"


@pytest.mark.asyncio
async def test_rate_limit_kicks_in_after_configured_threshold(client, api_key) -> None:
    _, raw_key = api_key
    limit = get_settings().api_key_rate_limit_per_minute

    statuses = [
        (
            await client.post(
                "/api/v1/research-jobs",
                json={"query": "A sufficiently long research query text."},
                headers=_auth(raw_key),
            )
        ).status_code
        for _ in range(limit + 2)
    ]

    assert statuses.count(429) >= 1
