import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import hash_api_key
from app.db.models import (
    ApiKey,
    JobPhase,
    JobStatus,
    ResearchJob,
    ResearchResult,
    TraceEvent,
    TraceEventType,
)


class ApiKeyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_raw_key(self, raw_key: str) -> ApiKey | None:
        stmt = select(ApiKey).where(
            ApiKey.key_hash == hash_api_key(raw_key), ApiKey.is_active.is_(True)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def create(self, name: str, key_hash: str) -> ApiKey:
        api_key = ApiKey(name=name, key_hash=key_hash)
        self.session.add(api_key)
        await self.session.flush()
        return api_key


class ResearchJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self, api_key_id: uuid.UUID, query: str, max_iterations: int, max_sources: int
    ) -> ResearchJob:
        job = ResearchJob(
            api_key_id=api_key_id,
            query=query,
            max_iterations=max_iterations,
            max_sources=max_sources,
            status=JobStatus.QUEUED,
        )
        self.session.add(job)
        await self.session.flush()
        return job

    async def get(self, job_id: uuid.UUID, api_key_id: uuid.UUID | None = None) -> ResearchJob | None:
        stmt = (
            select(ResearchJob)
            .where(ResearchJob.id == job_id)
            .options(selectinload(ResearchJob.result))
        )
        if api_key_id is not None:
            stmt = stmt.where(ResearchJob.api_key_id == api_key_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_for_key(
        self, api_key_id: uuid.UUID, limit: int = 20, before: datetime | None = None
    ) -> list[ResearchJob]:
        stmt = (
            select(ResearchJob)
            .where(ResearchJob.api_key_id == api_key_id)
            .options(selectinload(ResearchJob.result))
            .order_by(ResearchJob.created_at.desc())
            .limit(limit)
        )
        if before is not None:
            stmt = stmt.where(ResearchJob.created_at < before)
        return list((await self.session.execute(stmt)).scalars().all())

    async def set_status(
        self, job: ResearchJob, status: JobStatus, error: str | None = None
    ) -> None:
        job.status = status
        job.error = error
        now = datetime.now(UTC)
        if status == JobStatus.RUNNING and job.started_at is None:
            job.started_at = now
        if status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
            job.completed_at = now
        await self.session.flush()

    async def set_phase(self, job: ResearchJob, phase: JobPhase) -> None:
        job.phase = phase
        await self.session.flush()

    async def add_usage(self, job: ResearchJob, tokens: int, cost_usd: float) -> None:
        job.total_tokens += tokens
        job.total_cost_usd += cost_usd
        await self.session.flush()

    async def save_result(
        self, job: ResearchJob, report_markdown: str, sources: list[dict]
    ) -> None:
        self.session.add(
            ResearchResult(job_id=job.id, report_markdown=report_markdown, sources=sources)
        )
        await self.session.flush()


class TraceEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def next_seq(self, job_id: uuid.UUID) -> int:
        stmt = select(TraceEvent.seq).where(TraceEvent.job_id == job_id).order_by(
            TraceEvent.seq.desc()
        ).limit(1)
        last = (await self.session.execute(stmt)).scalar_one_or_none()
        return (last or 0) + 1

    async def record(
        self,
        job_id: uuid.UUID,
        phase: JobPhase,
        event_type: TraceEventType,
        payload: dict,
        tokens_used: int = 0,
        cost_usd: float = 0.0,
    ) -> TraceEvent:
        event = TraceEvent(
            job_id=job_id,
            seq=await self.next_seq(job_id),
            phase=phase,
            event_type=event_type,
            payload=payload,
            tokens_used=tokens_used,
            cost_usd=cost_usd,
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def list_since(self, job_id: uuid.UUID, after_seq: int = 0) -> list[TraceEvent]:
        stmt = (
            select(TraceEvent)
            .where(TraceEvent.job_id == job_id, TraceEvent.seq > after_seq)
            .order_by(TraceEvent.seq)
        )
        return list((await self.session.execute(stmt)).scalars().all())
