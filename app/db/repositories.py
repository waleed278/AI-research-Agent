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
    LlmCredential,
    LlmProvider,
    ResearchJob,
    ResearchResult,
    TraceEvent,
    TraceEventType,
    UploadedFile,
    User,
)


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, email: str, password_hash: str) -> User:
        user = User(email=email.lower(), password_hash=password_hash)
        self.session.add(user)
        await self.session.flush()
        return user

    async def get(self, user_id: uuid.UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email.lower())
        return (await self.session.execute(stmt)).scalar_one_or_none()


class ApiKeyRepository:
    """Manages user-owned developer credentials (programmatic access to
    this platform's own API) -- see ApiKey's docstring in app/db/models.py
    for how this differs from LlmCredential."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_raw_key(self, raw_key: str) -> ApiKey | None:
        stmt = select(ApiKey).where(
            ApiKey.key_hash == hash_api_key(raw_key), ApiKey.is_active.is_(True)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def create(self, user_id: uuid.UUID, name: str, key_hash: str) -> ApiKey:
        api_key = ApiKey(user_id=user_id, name=name, key_hash=key_hash)
        self.session.add(api_key)
        await self.session.flush()
        return api_key

    async def list_for_user(self, user_id: uuid.UUID) -> list[ApiKey]:
        stmt = select(ApiKey).where(ApiKey.user_id == user_id).order_by(ApiKey.created_at.desc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def get(self, key_id: uuid.UUID, user_id: uuid.UUID) -> ApiKey | None:
        stmt = select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def revoke(self, api_key: ApiKey) -> None:
        api_key.is_active = False
        await self.session.flush()


class LlmCredentialRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert(
        self,
        user_id: uuid.UUID,
        provider: LlmProvider,
        encrypted_key: str,
        label: str | None,
    ) -> LlmCredential:
        """One credential per (user, provider) -- see the unique constraint
        in app/db/models.py. Adding a new key for a provider the user
        already configured replaces it rather than erroring, since the
        obvious intent of re-submitting the form is "use this key now"."""
        existing = await self.get_for_provider(user_id, provider)
        now = datetime.now(UTC)
        if existing is not None:
            existing.encrypted_key = encrypted_key
            existing.label = label
            existing.is_valid = True
            existing.last_validated_at = now
            await self.session.flush()
            return existing

        credential = LlmCredential(
            user_id=user_id,
            provider=provider,
            encrypted_key=encrypted_key,
            label=label,
            is_valid=True,
            last_validated_at=now,
        )
        self.session.add(credential)
        await self.session.flush()
        return credential

    async def get_for_provider(self, user_id: uuid.UUID, provider: LlmProvider) -> LlmCredential | None:
        stmt = select(LlmCredential).where(
            LlmCredential.user_id == user_id, LlmCredential.provider == provider
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_for_user(self, user_id: uuid.UUID) -> list[LlmCredential]:
        stmt = (
            select(LlmCredential)
            .where(LlmCredential.user_id == user_id)
            .order_by(LlmCredential.created_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get(self, credential_id: uuid.UUID, user_id: uuid.UUID) -> LlmCredential | None:
        stmt = select(LlmCredential).where(
            LlmCredential.id == credential_id, LlmCredential.user_id == user_id
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def delete(self, credential: LlmCredential) -> None:
        await self.session.delete(credential)
        await self.session.flush()


class UploadedFileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        upload_id: uuid.UUID,
        user_id: uuid.UUID,
        filename: str,
        content_type: str,
        size_bytes: int,
        storage_path: str,
        extracted_text: str,
    ) -> UploadedFile:
        uploaded = UploadedFile(
            id=upload_id,
            user_id=user_id,
            filename=filename,
            content_type=content_type,
            size_bytes=size_bytes,
            storage_path=storage_path,
            extracted_text=extracted_text,
            extracted_chars=len(extracted_text),
        )
        self.session.add(uploaded)
        await self.session.flush()
        return uploaded

    async def get_owned_many(self, file_ids: list[uuid.UUID], user_id: uuid.UUID) -> list[UploadedFile]:
        """Fetches only the files in `file_ids` that actually belong to
        `user_id` -- silently drops any id that doesn't (an id belonging to
        another user, or one that never existed), so a caller can't attach
        someone else's upload to their own job by guessing a UUID."""
        stmt = select(UploadedFile).where(
            UploadedFile.id.in_(file_ids), UploadedFile.user_id == user_id
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def attach_to_job(self, files: list[UploadedFile], job_id: uuid.UUID) -> None:
        for file in files:
            file.job_id = job_id
        await self.session.flush()


class ResearchJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        user_id: uuid.UUID,
        query: str,
        max_iterations: int,
        max_sources: int,
        llm_provider: LlmProvider,
        llm_model: str,
    ) -> ResearchJob:
        job = ResearchJob(
            user_id=user_id,
            query=query,
            max_iterations=max_iterations,
            max_sources=max_sources,
            llm_provider=llm_provider,
            llm_model=llm_model,
            status=JobStatus.QUEUED,
        )
        self.session.add(job)
        await self.session.flush()
        return job

    async def get(self, job_id: uuid.UUID, user_id: uuid.UUID | None = None) -> ResearchJob | None:
        stmt = (
            select(ResearchJob)
            .where(ResearchJob.id == job_id)
            .options(selectinload(ResearchJob.result), selectinload(ResearchJob.attachments))
        )
        if user_id is not None:
            stmt = stmt.where(ResearchJob.user_id == user_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_for_user(
        self, user_id: uuid.UUID, limit: int = 20, before: datetime | None = None
    ) -> list[ResearchJob]:
        stmt = (
            select(ResearchJob)
            .where(ResearchJob.user_id == user_id)
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
