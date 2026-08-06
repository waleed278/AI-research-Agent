from pydantic import BaseModel, Field

from app.agent.state import EvidenceItem
from app.llm.client import LLMClient
from app.llm.schemas import StructuredResult

_COVERAGE_PROMPT = """You are grading a research report for completeness against a \
checklist of points it should address. Be strict: a point only counts as covered if \
the report actually states it, not if it is merely implied or adjacent.

Original research query:
{query}

Points the report should cover:
{must_cover}

The report to grade:
---
{report}
---

Score the fraction of the checklist points that are actually covered (0.0 to 1.0), \
and list any points that are missing or only superficially addressed.
"""

_GROUNDEDNESS_PROMPT = """You are grading a research report for factual grounding. \
The writer had access only to the numbered sources below and was instructed to cite \
every non-obvious claim by source ID.

Sources available to the writer (id, title, snippet):
{sources}

The report to grade:
---
{report}
---

For each non-trivial factual claim in the report, check whether it is actually \
supported by the snippet of the source it cites (a citation to a source that does not \
actually contain that fact counts as unsupported). Score the fraction of claims that \
are properly grounded (0.0 to 1.0), and list specific unsupported or miscited claims.
"""


class CoverageVerdict(BaseModel):
    coverage_score: float = Field(ge=0, le=1)
    missing_points: list[str] = Field(default_factory=list)
    reasoning: str


class GroundednessVerdict(BaseModel):
    groundedness_score: float = Field(ge=0, le=1)
    unsupported_claims: list[str] = Field(default_factory=list)
    reasoning: str


async def judge_coverage(
    llm: LLMClient, judge_model: str, query: str, must_cover: list[str], report_markdown: str
) -> StructuredResult[CoverageVerdict]:
    prompt = _COVERAGE_PROMPT.format(
        query=query,
        must_cover="\n".join(f"- {point}" for point in must_cover),
        report=report_markdown,
    )
    return await llm.structured(
        model=judge_model,
        messages=[{"role": "system", "content": prompt}],
        response_model=CoverageVerdict,
        temperature=0.0,
    )


async def judge_groundedness(
    llm: LLMClient, judge_model: str, sources: list[EvidenceItem], report_markdown: str
) -> StructuredResult[GroundednessVerdict]:
    sources_block = (
        "\n\n".join(f"[{s.id}] {s.title}\n{s.snippet}" for s in sources) or "(no sources were gathered)"
    )
    prompt = _GROUNDEDNESS_PROMPT.format(sources=sources_block, report=report_markdown)
    return await llm.structured(
        model=judge_model,
        messages=[{"role": "system", "content": prompt}],
        response_model=GroundednessVerdict,
        temperature=0.0,
    )
