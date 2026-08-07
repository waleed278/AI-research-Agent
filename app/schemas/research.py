import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.core.config import DEFAULT_MODEL_BY_PROVIDER, SUPPORTED_MODELS
from app.db.models import JobPhase, JobStatus, LlmProvider


class ResearchJobCreateRequest(BaseModel):
    query: str = Field(
        min_length=8, max_length=2000, description="The research question to investigate."
    )
    provider: LlmProvider = Field(description="Which LLM provider to run this job on.")
    model: str | None = Field(
        default=None,
        description="Defaults to a sensible model for the chosen provider if omitted.",
    )
    max_iterations: int | None = Field(default=None, ge=1, le=20)
    max_sources: int | None = Field(default=None, ge=1, le=20)
    attachment_ids: list[uuid.UUID] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def _resolve_and_validate_model(self) -> "ResearchJobCreateRequest":
        allowed = SUPPORTED_MODELS.get(self.provider.value, [])
        if self.model is None:
            self.model = DEFAULT_MODEL_BY_PROVIDER.get(self.provider.value, allowed[0] if allowed else "")
        elif self.model not in allowed:
            raise ValueError(
                f"'{self.model}' is not a supported model for provider '{self.provider.value}'. "
                f"Supported: {', '.join(allowed)}"
            )
        return self


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
    llm_provider: LlmProvider
    llm_model: str
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
