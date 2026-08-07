from typing import Any, Protocol

from pydantic import BaseModel, Field

from app.db.models import JobPhase

# --- structured LLM call contracts -----------------------------------------


class SubQuestion(BaseModel):
    question: str = Field(description="A specific, searchable sub-question.")
    rationale: str = Field(description="Why answering this helps answer the overall query.")


class PlannerOutput(BaseModel):
    sub_questions: list[SubQuestion] = Field(
        description="3-5 sub-questions that together cover the user's research query.",
        min_length=1,
        max_length=6,
    )


class CriticVerdict(BaseModel):
    coverage_ok: bool = Field(description="True if the evidence gathered covers all sub-questions.")
    grounding_ok: bool = Field(
        description="True if claims implied by the evidence are backed by real source snippets."
    )
    gaps: list[str] = Field(default_factory=list, description="Specific missing pieces of information.")
    revise_queries: list[str] = Field(
        default_factory=list,
        description="Additional web_search queries that would close the gaps, if any.",
        max_length=4,
    )
    rationale: str = Field(description="One or two sentences explaining the verdict.")


class SynthesizerOutput(BaseModel):
    report_markdown: str = Field(
        description=(
            "The final research report in Markdown, with inline numeric citations like "
            "[1], [2] matching the provided source IDs. No fabricated sources."
        )
    )


# --- evidence / trace bookkeeping ------------------------------------------


class AttachmentInput(BaseModel):
    """A user-uploaded document's extracted text, handed to the orchestrator
    to seed as evidence before research starts (see
    Orchestrator._seed_attachments and app/services/uploads_service.py for
    where `text` actually comes from). Deliberately a plain agent-layer type
    rather than the `UploadedFile` ORM model -- the worker does that
    translation so agent code stays free of persistence concerns."""

    filename: str
    text: str


class EvidenceItem(BaseModel):
    id: int
    url: str
    title: str
    snippet: str


class EvidenceStore:
    """Deterministically assigns citation IDs to sources as the research
    loop discovers them. The synthesizer is only ever shown *this* list and
    told to cite by ID -- it never invents its own source list, which is
    what makes the citation-validity eval a purely mechanical check."""

    def __init__(self, max_items: int | None = None) -> None:
        self._by_url: dict[str, EvidenceItem] = {}
        self._next_id = 1
        self._max_items = max_items

    def add(self, url: str, title: str, snippet: str) -> EvidenceItem:
        if url in self._by_url:
            return self._by_url[url]
        if self._max_items is not None and len(self._by_url) >= self._max_items:
            # Source budget for this job is exhausted -- return an unlinked
            # item (still usable as tool-call context for the LLM this turn)
            # without registering it, so citation numbering stays stable and
            # bounded to what the caller asked for via `max_sources`.
            return EvidenceItem(id=-1, url=url, title=title or url, snippet=snippet)
        item = EvidenceItem(id=self._next_id, url=url, title=title or url, snippet=snippet)
        self._by_url[url] = item
        self._next_id += 1
        return item

    @property
    def items(self) -> list[EvidenceItem]:
        return sorted(self._by_url.values(), key=lambda e: e.id)

    def as_prompt_block(self) -> str:
        if not self._by_url:
            return "(no evidence gathered yet)"
        return "\n\n".join(
            f"[{e.id}] {e.title}\nURL: {e.url}\nSnippet: {e.snippet}" for e in self.items
        )


class RunResult(BaseModel):
    report_markdown: str
    sources: list[EvidenceItem]
    total_tokens: int
    total_cost_usd: float
    tool_call_count: int


# --- trace sink: decouples agent logic from persistence ---------------------


class TraceSink(Protocol):
    """The orchestrator reports everything it does through this interface.
    Production code implements it against Postgres (see
    services/research_service.py); tests use an in-memory implementation so
    agent logic can be verified without a database."""

    async def phase_change(self, phase: JobPhase) -> None: ...

    async def llm_call(
        self, phase: JobPhase, model: str, tokens: int, cost_usd: float, summary: str
    ) -> None: ...

    async def tool_call(self, phase: JobPhase, tool_name: str, arguments: dict[str, Any]) -> None: ...

    async def tool_result(self, phase: JobPhase, tool_name: str, ok: bool, summary: str) -> None: ...

    async def error(self, phase: JobPhase, message: str) -> None: ...


class NullTraceSink:
    """No-op sink -- useful for quick scripts/eval runs that don't need a
    persisted trace, only the final result."""

    async def phase_change(self, phase: JobPhase) -> None:
        pass

    async def llm_call(self, phase: JobPhase, model: str, tokens: int, cost_usd: float, summary: str) -> None:
        pass

    async def tool_call(self, phase: JobPhase, tool_name: str, arguments: dict[str, Any]) -> None:
        pass

    async def tool_result(self, phase: JobPhase, tool_name: str, ok: bool, summary: str) -> None:
        pass

    async def error(self, phase: JobPhase, message: str) -> None:
        pass


class InMemoryTraceSink:
    """Records everything in a plain list -- what unit/integration tests
    assert against instead of querying a database."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def phase_change(self, phase: JobPhase) -> None:
        self.events.append({"type": "phase_change", "phase": phase.value})

    async def llm_call(self, phase: JobPhase, model: str, tokens: int, cost_usd: float, summary: str) -> None:
        self.events.append(
            {"type": "llm_call", "phase": phase.value, "model": model, "tokens": tokens,
             "cost_usd": cost_usd, "summary": summary}
        )

    async def tool_call(self, phase: JobPhase, tool_name: str, arguments: dict[str, Any]) -> None:
        self.events.append(
            {"type": "tool_call", "phase": phase.value, "tool_name": tool_name, "arguments": arguments}
        )

    async def tool_result(self, phase: JobPhase, tool_name: str, ok: bool, summary: str) -> None:
        self.events.append(
            {
                "type": "tool_result",
                "phase": phase.value,
                "tool_name": tool_name,
                "ok": ok,
                "summary": summary,
            }
        )

    async def error(self, phase: JobPhase, message: str) -> None:
        self.events.append({"type": "error", "message": message})
