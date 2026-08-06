import asyncio
import json
import uuid
from datetime import datetime

from arq import ArqRedis
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.api.deps import enforce_rate_limit, get_arq_redis, get_current_api_key, get_db_session
from app.core.config import Settings, get_settings
from app.db.models import ApiKey, JobStatus
from app.db.repositories import ResearchJobRepository, TraceEventRepository
from app.schemas.research import (
    ResearchJobCreateRequest,
    ResearchJobCreateResponse,
    ResearchJobListResponse,
    ResearchJobResponse,
)
from app.services.research_service import (
    cancel_research_job,
    create_research_job,
    get_research_job,
    list_research_jobs,
    to_response,
)

router = APIRouter(prefix="/research-jobs", tags=["research"])

_TERMINAL_STATUSES = {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}


@router.post(
    "",
    response_model=ResearchJobCreateResponse,
    status_code=202,
    dependencies=[Depends(enforce_rate_limit)],
)
async def create_job(
    body: ResearchJobCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    arq_redis: ArqRedis = Depends(get_arq_redis),
    api_key: ApiKey = Depends(get_current_api_key),
) -> ResearchJobCreateResponse:
    """Enqueues a research job and returns immediately -- a thorough research
    run can take 30s-3min, which is well past what a synchronous HTTP
    request should block on. Poll GET /{id} or stream GET /{id}/events."""
    job = await create_research_job(session, arq_redis, api_key.id, body)
    return ResearchJobCreateResponse(id=job.id, status=job.status)


@router.get("/{job_id}", response_model=ResearchJobResponse)
async def get_job(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    api_key: ApiKey = Depends(get_current_api_key),
) -> ResearchJobResponse:
    job = await get_research_job(session, job_id, api_key.id)
    return to_response(job)


@router.get("", response_model=ResearchJobListResponse)
async def list_jobs(
    limit: int = Query(default=20, ge=1, le=100),
    before: datetime | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
    api_key: ApiKey = Depends(get_current_api_key),
) -> ResearchJobListResponse:
    jobs = await list_research_jobs(session, api_key.id, limit, before)
    next_cursor = jobs[-1].created_at if len(jobs) == limit else None
    return ResearchJobListResponse(items=[to_response(j) for j in jobs], next_cursor=next_cursor)


@router.delete("/{job_id}", response_model=ResearchJobResponse)
async def cancel_job(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    api_key: ApiKey = Depends(get_current_api_key),
) -> ResearchJobResponse:
    job = await cancel_research_job(session, job_id, api_key.id)
    return to_response(job)


@router.get("/{job_id}/events")
async def stream_job_events(
    job_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    api_key: ApiKey = Depends(get_current_api_key),
    settings: Settings = Depends(get_settings),
) -> EventSourceResponse:
    """Server-Sent Events feed of a job's trace as it happens -- the live
    view of the agent thinking/searching/reading, as an alternative to
    polling GET /{id}. Closes on its own once the job reaches a terminal
    status or the client disconnects."""
    await get_research_job(session, job_id, api_key.id)  # 404s / ownership-check up front
    jobs_repo = ResearchJobRepository(session)
    events_repo = TraceEventRepository(session)
    max_duration_seconds = settings.agent_job_timeout_seconds + 30

    async def event_generator():
        after_seq = 0
        elapsed = 0.0
        poll_interval = 1.0

        while elapsed < max_duration_seconds:
            if await request.is_disconnected():
                break

            new_events = await events_repo.list_since(job_id, after_seq)
            for event in new_events:
                after_seq = event.seq
                yield {
                    "event": event.event_type.value,
                    "data": json.dumps(
                        {
                            "seq": event.seq,
                            "phase": event.phase.value,
                            "payload": event.payload,
                            "tokens_used": event.tokens_used,
                            "cost_usd": event.cost_usd,
                        }
                    ),
                }

            job = await jobs_repo.get(job_id)
            if job is not None and job.status in _TERMINAL_STATUSES:
                yield {"event": "job_status", "data": json.dumps({"status": job.status.value})}
                break

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

    return EventSourceResponse(event_generator())
