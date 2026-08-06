import pytest

from app.agent.orchestrator import Orchestrator
from app.agent.state import CriticVerdict, PlannerOutput, SubQuestion, SynthesizerOutput
from app.core.config import Settings
from app.core.exceptions import AgentRunLimitExceeded
from app.llm.schemas import ChatResult
from app.tools.registry import ToolRegistry
from app.tools.web_search import MockSearchProvider, WebSearchTool
from tests.conftest import FakeLLMClient, make_usage

QUERY = "What is the capital of France and why?"


def _settings(**overrides) -> Settings:
    return Settings(openai_api_key="test", **overrides)


def _registry() -> ToolRegistry:
    return ToolRegistry([WebSearchTool(MockSearchProvider())])


def _chat_done(text: str) -> ChatResult:
    return ChatResult(content=text, tool_calls=[], usage=make_usage(), cost_usd=0.0, finish_reason="stop")


@pytest.mark.asyncio
async def test_orchestrator_raises_when_token_budget_exceeded(fake_llm: FakeLLMClient) -> None:
    fake_llm.queue_structured(
        "PlannerOutput",
        PlannerOutput(sub_questions=[SubQuestion(question="q1", rationale="r")]),
    )
    # make_usage() reports 15 tokens per call -- a budget of 5 is blown by the planner call alone.
    settings = _settings(agent_max_tokens_per_job=5)
    orchestrator = Orchestrator(llm=fake_llm, registry=_registry(), settings=settings)

    with pytest.raises(AgentRunLimitExceeded, match="token budget"):
        await orchestrator.run(query=QUERY, max_iterations=5, max_sources=5)


@pytest.mark.asyncio
async def test_orchestrator_happy_path_produces_cited_report(fake_llm: FakeLLMClient) -> None:
    fake_llm.queue_structured(
        "PlannerOutput",
        PlannerOutput(sub_questions=[SubQuestion(question="q1", rationale="r")]),
    )
    fake_llm.queue_chat(_chat_done("done"))
    fake_llm.queue_structured(
        "CriticVerdict",
        CriticVerdict(coverage_ok=True, grounding_ok=True, gaps=[], revise_queries=[], rationale="fine"),
    )
    fake_llm.queue_structured(
        "SynthesizerOutput", SynthesizerOutput(report_markdown="# Report\n\nAll good.")
    )

    settings = _settings(agent_max_tokens_per_job=100_000, agent_max_revision_loops=1)
    orchestrator = Orchestrator(llm=fake_llm, registry=_registry(), settings=settings)

    result = await orchestrator.run(query=QUERY, max_iterations=5, max_sources=5)

    assert result.report_markdown.startswith("# Report")
    assert result.total_tokens > 0


@pytest.mark.asyncio
async def test_orchestrator_runs_a_revision_loop_when_critic_finds_gaps(fake_llm: FakeLLMClient) -> None:
    fake_llm.queue_structured(
        "PlannerOutput",
        PlannerOutput(sub_questions=[SubQuestion(question="q1", rationale="r")]),
    )
    fake_llm.queue_chat(_chat_done("initial pass done"))
    # Critic finds a gap and asks for one more targeted search.
    fake_llm.queue_structured(
        "CriticVerdict",
        CriticVerdict(
            coverage_ok=False,
            grounding_ok=False,
            gaps=["missing a key statistic"],
            revise_queries=["the missing statistic"],
            rationale="needs more",
        ),
    )
    fake_llm.queue_chat(_chat_done("revision pass done"))
    fake_llm.queue_structured(
        "SynthesizerOutput", SynthesizerOutput(report_markdown="# Report\n\nComplete.")
    )

    settings = _settings(agent_max_tokens_per_job=100_000, agent_max_revision_loops=1)
    orchestrator = Orchestrator(llm=fake_llm, registry=_registry(), settings=settings)

    result = await orchestrator.run(query=QUERY, max_iterations=5, max_sources=5)

    assert result.report_markdown == "# Report\n\nComplete."
    # planner + 2 chat turns + critic + synthesizer
    assert len(fake_llm.chat_calls) == 2
    assert len(fake_llm.structured_calls) == 3
