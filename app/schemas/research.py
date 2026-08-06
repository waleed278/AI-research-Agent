import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.db.models import JobPhase, JobStatus


class ResearchJobCreateRequest(BaseModel):
    query: str = Field(
        min_length=8, max_length=2000, description="The research question to investigate."
    )
    max_iterations: int | None = Field(default=None, ge=1, le=20)
    max_sources: int | None = Field(default=None, ge=1, le=20)


class ResearchJobCreateResponse(BaseModel):
    id: uuid.UUID
    status: JobStatus


class SourceResponse(BaseModel):
    id: int
    url: str
    title: str


class ResearchResultResponse(BaseModel):
    report_markdown: str
    sources: list[SourceResponse]


class ResearchJobResponse(BaseModel):
    id: uuid.UUID
    query: str
    status: JobStatus
    phase: JobPhase | None
    error: str | None
    total_tokens: int
    total_cost_usd: float
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    result: ResearchResultResponse | None = None


class ResearchJobListResponse(BaseModel):
    items: list[ResearchJobResponse]
    next_cursor: datetime | None = None


class TraceEventResponse(BaseModel):
    seq: int
    phase: JobPhase
    event_type: str
    payload: dict
    tokens_used: int
    cost_usd: float
    created_at: datetime
