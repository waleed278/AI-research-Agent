import pytest

from app.agent.research_loop import run_research_loop
from app.agent.state import EvidenceStore, NullTraceSink
from app.llm.schemas import ChatResult
from app.tools.registry import ToolRegistry
from app.tools.web_search import MockSearchProvider, WebSearchTool
from tests.conftest import FakeLLMClient, make_usage, tool_call


@pytest.mark.asyncio
async def test_research_loop_stops_when_model_returns_no_tool_calls(fake_llm: FakeLLMClient) -> None:
    fake_llm.queue_chat(
        ChatResult(
            content=None,
            tool_calls=[tool_call("1", "web_search", {"query": "q", "max_results": 2})],
            usage=make_usage(),
            cost_usd=0.0,
            finish_reason="tool_calls",
        )
    )
    fake_llm.queue_chat(
        ChatResult(
            content="Enough evidence gathered.",
            tool_calls=[],
            usage=make_usage(),
            cost_usd=0.0,
            finish_reason="stop",
        )
    )
    registry = ToolRegistry([WebSearchTool(MockSearchProvider())])
    evidence = EvidenceStore()

    result = await run_research_loop(
        llm=fake_llm,
        model="gpt-4o-mini",
        registry=registry,
        query="q",
        sub_questions=["q"],
        evidence=evidence,
        sink=NullTraceSink(),
        max_steps=10,
    )

    assert result.summary == "Enough evidence gathered."
    assert result.tool_call_count == 1
    assert len(evidence.items) == 2


@pytest.mark.asyncio
async def test_research_loop_respects_max_steps_cap(fake_llm: FakeLLMClient) -> None:
    for i in range(20):
        fake_llm.queue_chat(
            ChatResult(
                content=None,
                tool_calls=[tool_call(str(i), "web_search", {"query": f"q{i}", "max_results": 1})],
                usage=make_usage(),
                cost_usd=0.0,
                finish_reason="tool_calls",
            )
        )
    registry = ToolRegistry([WebSearchTool(MockSearchProvider())])
    evidence = EvidenceStore()

    result = await run_research_loop(
        llm=fake_llm,
        model="gpt-4o-mini",
        registry=registry,
        query="q",
        sub_questions=["q"],
        evidence=evidence,
        sink=NullTraceSink(),
        max_steps=5,
    )

    assert result.tool_call_count == 5
    assert "step limit" in result.summary
