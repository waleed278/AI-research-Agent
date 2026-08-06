import enum
import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


def _enum_values(enum_cls: type[enum.StrEnum]) -> list[str]:
    """SQLAlchemy's `Enum` type stores the Python enum *member name* by
    default (e.g. "QUEUED"), not `.value` ("queued") -- which would silently
    diverge from the lowercase values used everywhere else (API JSON,
    Alembic's hand-written `postgresql.ENUM(...)` in the initial migration,
    and every `JobStatus.X.value` comparison in this codebase). Passed as
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


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    jobs: Mapped[list["ResearchJob"]] = relationship(back_populates="api_key")


class ResearchJob(Base):
    __tablename__ = "research_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    api_key_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("api_keys.id"), index=True)

    query: Mapped[str] = mapped_column(Text)
    max_iterations: Mapped[int] = mapped_column(default=12)
    max_sources: Mapped[int] = mapped_column(default=8)

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

    api_key: Mapped["ApiKey"] = relationship(back_populates="jobs")
    trace_events: Mapped[list["TraceEvent"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", order_by="TraceEvent.seq"
    )
    result: Mapped["ResearchResult | None"] = relationship(
        back_populates="job", cascade="all, delete-orphan", uselist=False
    )


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
