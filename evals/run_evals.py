"""Offline evaluation harness for the research agent.

    make eval        # real run: real OpenAI + configured search provider, spends API budget
    make eval-mock    # offline run: proves the harness itself works, costs nothing

This intentionally is NOT wired into the default CI pipeline (see
.github/workflows/ci.yml) -- CI runs on every push and must stay free and
fast, while a real eval run costs real money and takes real wall-clock time.
It's a deliberate, separate step a developer (or a manual/nightly CI job)
runs before shipping a prompt or model change.
"""

import argparse
import asyncio
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from app.agent.orchestrator import Orchestrator
from app.agent.state import (
    CriticVerdict,
    NullTraceSink,
    PlannerOutput,
    SubQuestion,
    SynthesizerOutput,
)
from app.core.config import get_settings
from app.llm.providers.openai_provider import OpenAIProvider
from app.llm.schemas import ChatResult, LLMUsage, StructuredResult, ToolCallRequest
from app.tools.fetch_url import FetchUrlTool
from app.tools.registry import ToolRegistry
from app.tools.web_search import MockSearchProvider, WebSearchTool
from evals.judge import judge_coverage, judge_groundedness
from evals.metrics import citation_validity

DATASET_PATH = Path(__file__).parent / "golden_dataset.jsonl"
REPORTS_DIR = Path(__file__).parent / "reports"


class GoldenQuery(BaseModel):
    id: str
    query: str
    must_cover: list[str]


class EvalResult(BaseModel):
    query_id: str
    query: str
    citation_validity: float
    citation_count: int
    coverage_score: float | None = None
    groundedness_score: float | None = None
    composite_score: float
    latency_seconds: float
    total_tokens: int
    total_cost_usd: float
    tool_call_count: int
    error: str | None = None


class MockAgentLLM:
    """Fully offline stand-in for an `LLMProvider`, used only by `--mock` runs.
    It still exercises the real `Orchestrator` and a real `web_search` tool
    call against `MockSearchProvider` -- this proves the eval harness's
    scoring/reporting/gating plumbing end to end without ever touching the
    network or an API key.
    """

    def __init__(self) -> None:
        self._chat_turn = 0

    async def chat(
        self, *, model: str, messages: list[dict], tools: list[dict] | None = None, temperature: float = 0.2
    ) -> ChatResult:
        self._chat_turn += 1
        usage = LLMUsage(prompt_tokens=50, completion_tokens=20, total_tokens=70)
        if self._chat_turn == 1 and tools:
            return ChatResult(
                content=None,
                tool_calls=[
                    ToolCallRequest(
                        id="mock-1", name="web_search", arguments={"query": "mock query", "max_results": 3}
                    )
                ],
                usage=usage,
                cost_usd=0.0,
                finish_reason="tool_calls",
            )
        return ChatResult(
            content="Mock research pass complete.",
            tool_calls=[],
            usage=usage,
            cost_usd=0.0,
            finish_reason="stop",
        )

    async def structured(
        self, *, model: str, messages: list[dict], response_model: type, temperature: float = 0.0
    ) -> StructuredResult:
        usage = LLMUsage(prompt_tokens=50, completion_tokens=20, total_tokens=70)
        if response_model is PlannerOutput:
            data = PlannerOutput(
                sub_questions=[SubQuestion(question="A representative mock sub-question?", rationale="mock")]
            )
        elif response_model is CriticVerdict:
            data = CriticVerdict(
                coverage_ok=True, grounding_ok=True, gaps=[], revise_queries=[], rationale="mock: accepted"
            )
        elif response_model is SynthesizerOutput:
            data = SynthesizerOutput(
                report_markdown="# Mock Report\n\nThis is a deterministic mock report citing a source [1]."
            )
        else:
            raise AssertionError(f"MockAgentLLM has no canned response for {response_model.__name__}")
        return StructuredResult(data=data, usage=usage, cost_usd=0.0)


def load_dataset(path: Path, limit: int | None) -> list[GoldenQuery]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = [GoldenQuery.model_validate_json(line) for line in lines]
    return rows[:limit] if limit else rows


async def run_one(golden: GoldenQuery, *, mock: bool) -> EvalResult:
    settings = get_settings()
    llm: OpenAIProvider | MockAgentLLM
    if mock:
        llm = MockAgentLLM()
        registry = ToolRegistry([WebSearchTool(MockSearchProvider())])
    else:
        llm = OpenAIProvider(
            api_key=settings.openai_api_key, timeout_seconds=settings.llm_request_timeout_seconds
        )
        registry = ToolRegistry([WebSearchTool(), FetchUrlTool()])

    orchestrator = Orchestrator(
        llm=llm, model=settings.openai_model, registry=registry, settings=settings  # type: ignore[arg-type]
    )
    start = time.perf_counter()
    try:
        result = await orchestrator.run(
            query=golden.query,
            max_iterations=settings.agent_max_tool_steps,
            max_sources=8,
            sink=NullTraceSink(),
        )
    except Exception as exc:  # noqa: BLE001 - one bad query must not abort the whole eval run
        return EvalResult(
            query_id=golden.id,
            query=golden.query,
            citation_validity=0.0,
            citation_count=0,
            composite_score=0.0,
            latency_seconds=time.perf_counter() - start,
            total_tokens=0,
            total_cost_usd=0.0,
            tool_call_count=0,
            error=str(exc),
        )
    latency = time.perf_counter() - start
    validity, citation_count = citation_validity(result.report_markdown, result.sources)
    total_cost = result.total_cost_usd

    coverage_score = None
    groundedness_score = None
    if not mock:
        judge_llm = OpenAIProvider(
            api_key=settings.openai_api_key, timeout_seconds=settings.llm_request_timeout_seconds
        )
        coverage = await judge_coverage(
            judge_llm, settings.openai_judge_model, golden.query, golden.must_cover, result.report_markdown
        )
        groundedness = await judge_groundedness(
            judge_llm, settings.openai_judge_model, result.sources, result.report_markdown
        )
        coverage_score = coverage.data.coverage_score
        groundedness_score = groundedness.data.groundedness_score
        total_cost += coverage.cost_usd + groundedness.cost_usd

    scores = [s for s in (validity, coverage_score, groundedness_score) if s is not None]
    composite = sum(scores) / len(scores) if scores else 0.0

    return EvalResult(
        query_id=golden.id,
        query=golden.query,
        citation_validity=validity,
        citation_count=citation_count,
        coverage_score=coverage_score,
        groundedness_score=groundedness_score,
        composite_score=composite,
        latency_seconds=latency,
        total_tokens=result.total_tokens,
        total_cost_usd=total_cost,
        tool_call_count=result.tool_call_count,
    )


async def main_async(args: argparse.Namespace) -> int:
    dataset = load_dataset(Path(args.dataset), args.limit)
    results: list[EvalResult] = []

    for golden in dataset:
        result = await run_one(golden, mock=args.mock)
        results.append(result)
        status = "FAIL" if result.error or result.composite_score < args.fail_under else " ok "
        print(
            f"[{status}] {result.query_id:5s} composite={result.composite_score:.2f} "
            f"citation_validity={result.citation_validity:.2f} "
            f"cost=${result.total_cost_usd:.4f} latency={result.latency_seconds:.1f}s"
            + (f"  ERROR: {result.error}" if result.error else "")
        )

    aggregate = sum(r.composite_score for r in results) / len(results) if results else 0.0
    total_cost = sum(r.total_cost_usd for r in results)

    REPORTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = "-mock" if args.mock else ""
    report_path = REPORTS_DIR / f"{timestamp}{suffix}.json"
    report_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(UTC).isoformat(),
                "mock": args.mock,
                "fail_under": args.fail_under,
                "aggregate_composite_score": aggregate,
                "total_cost_usd": total_cost,
                "results": [r.model_dump() for r in results],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"\nAggregate composite score: {aggregate:.3f} (threshold: {args.fail_under})")
    print(f"Total cost: ${total_cost:.4f}")
    print(f"Report written to {report_path}")

    any_errors = any(r.error for r in results)
    return 0 if aggregate >= args.fail_under and not any_errors else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the research agent over the golden eval dataset.")
    parser.add_argument("--dataset", default=str(DATASET_PATH))
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Run fully offline with no OpenAI/search API calls. Validates the harness, not report quality.",
    )
    parser.add_argument(
        "--fail-under",
        type=float,
        default=0.8,
        help="Exit non-zero if the aggregate composite score falls below this.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Only run the first N golden queries.")
    args = parser.parse_args()
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
