import enum
import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


def _enum_values(enum_cls: type[enum.StrEnum]) -> list[str]:
    """SQLAlchemy's `Enum` type stores the Python enum *member name* by
    default (e.g. "QUEUED"), not `.value` ("queued") -- which would silently
    diverge from the lowercase values used everywhere else (API JSON,
    Alembic's hand-written `postgresql.ENUM(...)` in the migrations, and
    every `JobStatus.X.value` comparison in this codebase). Passed as
    `values_callable` on every `Enum(...)` column below so the database
    representation matches `.value`, not `.name`.
    """
    return [member.value for member in enum_cls]


class JobStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobPhase(enum.StrEnum):
    PLANNING = "planning"
    RESEARCHING = "researching"
    CRITIQUING = "critiquing"
    SYNTHESIZING = "synthesizing"
    DONE = "done"


class TraceEventType(enum.StrEnum):
    PHASE_CHANGE = "phase_change"
    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    ERROR = "error"


class LlmProvider(enum.StrEnum):
    OPENAI = "openai"
    GEMINI = "gemini"
    ANTHROPIC = "anthropic"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    api_keys: Mapped[list["ApiKey"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    llm_credentials: Mapped[list["LlmCredential"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    jobs: Mapped[list["ResearchJob"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    uploaded_files: Mapped[list["UploadedFile"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class ApiKey(Base):
    """A user-owned developer credential for programmatic/script access to
    this platform's own API -- distinct from `LlmCredential`, which is a
    user's *third-party* LLM provider key that this platform uses on their
    behalf. Mirrors how OpenAI/Anthropic/Stripe separate "log into the
    console" from "API keys for scripts": both ultimately resolve to the
    same `User` (see `app/api/deps.py::get_current_user`)."""

    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="api_keys")


class LlmCredential(Base):
    """A user's own third-party LLM provider API key, encrypted at rest
    (see app/core/crypto.py) and decrypted only in-process, in the worker,
    right before building that job's provider client. One credential per
    provider per user -- adding a new one for the same provider replaces
    the old (see LlmCredentialRepository.upsert)."""

    __tablename__ = "llm_credentials"
    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_llm_credentials_user_provider"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[LlmProvider] = mapped_column(
        Enum(LlmProvider, name="llm_provider", values_callable=_enum_values)
    )
    encrypted_key: Mapped[str] = mapped_column(Text)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_valid: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_validated_at: Mapped[datetime | None] = mapped_column(nullable=True)

    user: Mapped["User"] = relationship(back_populates="llm_credentials")


class UploadedFile(Base):
    """A file a user attached to a research request. `job_id` is null
    between upload and attachment (POST /uploads happens before the job
    exists) and set once the job is created. Extracted text is seeded into
    the agent's EvidenceStore as a citable source -- see
    app/services/uploads_service.py and Orchestrator._seed_attachments."""

    __tablename__ = "uploaded_files"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_jobs.id"), nullable=True, index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int]
    storage_path: Mapped[str] = mapped_column(String(500))
    # Extracted once at upload time (see app/services/uploads_service.py) and
    # reused as-is when a job seeds its evidence store -- the worker never
    # needs filesystem access to re-parse the original file, only this column.
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    extracted_chars: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="uploaded_files")
    job: Mapped["ResearchJob | None"] = relationship(back_populates="attachments")


class ResearchJob(Base):
    __tablename__ = "research_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)

    query: Mapped[str] = mapped_column(Text)
    max_iterations: Mapped[int] = mapped_column(default=12)
    max_sources: Mapped[int] = mapped_column(default=8)
    llm_provider: Mapped[LlmProvider] = mapped_column(
        Enum(LlmProvider, name="llm_provider", values_callable=_enum_values)
    )
    llm_model: Mapped[str] = mapped_column(String(100))

    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status", values_callable=_enum_values), default=JobStatus.QUEUED, index=True
    )
    phase: Mapped[JobPhase | None] = mapped_column(
        Enum(JobPhase, name="job_phase", values_callable=_enum_values), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    total_tokens: Mapped[int] = mapped_column(default=0)
    total_cost_usd: Mapped[float] = mapped_column(default=0.0)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    user: Mapped["User"] = relationship(back_populates="jobs")
    trace_events: Mapped[list["TraceEvent"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", order_by="TraceEvent.seq"
    )
    result: Mapped["ResearchResult | None"] = relationship(
        back_populates="job", cascade="all, delete-orphan", uselist=False
    )
    attachments: Mapped[list["UploadedFile"]] = relationship(back_populates="job")


class TraceEvent(Base):
    """One row per LLM call / tool call / phase transition. This is both the
    live-progress feed (SSE endpoint tails these) and the audit trail an eval
    or a post-incident debug session replays."""

    __tablename__ = "trace_events"
    __table_args__ = (Index("ix_trace_events_job_seq", "job_id", "seq"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("research_jobs.id"), index=True)
    seq: Mapped[int]
    phase: Mapped[JobPhase] = mapped_column(Enum(JobPhase, name="job_phase", values_callable=_enum_values))
    event_type: Mapped[TraceEventType] = mapped_column(
        Enum(TraceEventType, name="trace_event_type", values_callable=_enum_values)
    )
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    tokens_used: Mapped[int] = mapped_column(default=0)
    cost_usd: Mapped[float] = mapped_column(default=0.0)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    job: Mapped["ResearchJob"] = relationship(back_populates="trace_events")


class ResearchResult(Base):
    __tablename__ = "research_results"

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_jobs.id"), primary_key=True
    )
    report_markdown: Mapped[str] = mapped_column(Text)
    sources: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    job: Mapped["ResearchJob"] = relationship(back_populates="result")
