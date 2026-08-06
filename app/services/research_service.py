import uuid
from datetime import datetime
from typing import Any

from arq import ArqRedis
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.state import TraceSink
from app.core.config import Settings, get_settings
from app.core.exceptions import ConflictError, NotFoundError
from app.db.models import JobPhase, JobStatus, ResearchJob, TraceEventType
from app.db.repositories import ResearchJobRepository, TraceEventRepository
from app.schemas.research import (
    ResearchJobCreateRequest,
    ResearchJobResponse,
    ResearchResultResponse,
    SourceResponse,
)


class DbTraceSink(TraceSink):
    """Persists every agent step as a `TraceEvent` row and keeps the parent
    `ResearchJob`'s phase/usage columns in sync. This is what the worker
    hands to the `Orchestrator` -- the orchestrator itself has no idea a
    database exists, it just calls this interface."""

    def __init__(self, session: AsyncSession, job: ResearchJob) -> None:
        self.session = session
        self.job = job
        self.jobs = ResearchJobRepository(session)
        self.events = TraceEventRepository(session)

    # Every method commits immediately (rather than relying on one commit at
    # the end of the job) so the trace survives even if the job later fails
    # or times out -- the whole point of a trace is to see what happened
    # right up to the failure, not lose it to a rollback.

    async def phase_change(self, phase: JobPhase) -> None:
        await self.jobs.set_phase(self.job, phase)
        await self.events.record(
            self.job.id, phase, TraceEventType.PHASE_CHANGE, {"phase": phase.value}
        )
        await self.session.commit()

    async def llm_call(
        self, phase: JobPhase, model: str, tokens: int, cost_usd: float, summary: str
    ) -> None:
        await self.jobs.add_usage(self.job, tokens, cost_usd)
        await self.events.record(
            self.job.id,
            phase,
            TraceEventType.LLM_CALL,
            {"model": model, "summary": summary},
            tokens_used=tokens,
            cost_usd=cost_usd,
        )
        await self.session.commit()

    async def tool_call(self, phase: JobPhase, tool_name: str, arguments: dict[str, Any]) -> None:
        await self.events.record(
            self.job.id,
            phase,
            TraceEventType.TOOL_CALL,
            {"tool": tool_name, "arguments": arguments},
        )
        await self.session.commit()

    async def tool_result(self, phase: JobPhase, tool_name: str, ok: bool, summary: str) -> None:
        await self.events.record(
            self.job.id,
            phase,
            TraceEventType.TOOL_RESULT,
            {"tool": tool_name, "ok": ok, "summary": summary},
        )
        await self.session.commit()

    async def error(self, phase: JobPhase, message: str) -> None:
        await self.events.record(self.job.id, phase, TraceEventType.ERROR, {"message": message})
        await self.session.commit()


async def create_research_job(
    session: AsyncSession,
    arq_redis: ArqRedis,
    api_key_id: uuid.UUID,
    request: ResearchJobCreateRequest,
    settings: Settings | None = None,
) -> ResearchJob:
    settings = settings or get_settings()
    jobs = ResearchJobRepository(session)
    job = await jobs.create(
        api_key_id=api_key_id,
        query=request.query,
        max_iterations=request.max_iterations or settings.agent_max_tool_steps,
        max_sources=request.max_sources or 8,
    )
    await session.flush()
    await arq_redis.enqueue_job("run_research_job", job_id=str(job.id))
    return job


async def get_research_job(
    session: AsyncSession, job_id: uuid.UUID, api_key_id: uuid.UUID
) -> ResearchJob:
    jobs = ResearchJobRepository(session)
    job = await jobs.get(job_id, api_key_id=api_key_id)
    if job is None:
        raise NotFoundError(f"No research job with id {job_id}")
    return job


async def list_research_jobs(
    session: AsyncSession, api_key_id: uuid.UUID, limit: int, before: datetime | None
) -> list[ResearchJob]:
    jobs = ResearchJobRepository(session)
    return await jobs.list_for_key(api_key_id, limit=limit, before=before)


async def cancel_research_job(
    session: AsyncSession, job_id: uuid.UUID, api_key_id: uuid.UUID
) -> ResearchJob:
    job = await get_research_job(session, job_id, api_key_id)
    if job.status != JobStatus.QUEUED:
        raise ConflictError(f"Job {job_id} is '{job.status.value}' and can no longer be cancelled")
    jobs = ResearchJobRepository(session)
    await jobs.set_status(job, JobStatus.CANCELLED)
    return job


def to_response(job: ResearchJob) -> ResearchJobResponse:
    result = None
    if job.result is not None:
        result = ResearchResultResponse(
            report_markdown=job.result.report_markdown,
            sources=[SourceResponse(**s) for s in job.result.sources],
        )
    return ResearchJobResponse(
        id=job.id,
        query=job.query,
        status=job.status,
        phase=job.phase,
        error=job.error,
        total_tokens=job.total_tokens,
        total_cost_usd=job.total_cost_usd,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        result=result,
    )
