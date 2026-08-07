import json

from app.agent.prompt_loader import load_prompt
from app.agent.state import EvidenceStore, TraceSink
from app.db.models import JobPhase
from app.llm.base import LLMProvider
from app.tools.base import ToolResult
from app.tools.registry import ToolRegistry


class ResearchLoopResult:
    def __init__(self, summary: str, tool_call_count: int, total_tokens: int, total_cost_usd: float) -> None:
        self.summary = summary
        self.tool_call_count = tool_call_count
        self.total_tokens = total_tokens
        self.total_cost_usd = total_cost_usd


async def run_research_loop(
    *,
    llm: LLMProvider,
    model: str,
    registry: ToolRegistry,
    query: str,
    sub_questions: list[str],
    evidence: EvidenceStore,
    sink: TraceSink,
    max_steps: int,
    extra_instruction: str | None = None,
) -> ResearchLoopResult:
    """The ReAct-style tool-calling loop: the model alternates between
    deciding which tool to call and reading the results, until it either
    volunteers a plain-text summary (no more tool calls) or the step budget
    for this job runs out. `max_steps` caps the number of *tool calls*, not
    LLM turns -- that's the dimension that actually costs external API
    quota (Tavily) and wall-clock time.
    """
    prompt = load_prompt("research_loop").format(
        query=query,
        sub_questions="\n".join(f"- {q}" for q in sub_questions),
        max_steps=max_steps,
    )
    messages: list[dict] = [{"role": "system", "content": prompt}]
    if extra_instruction:
        messages.append({"role": "user", "content": extra_instruction})

    tool_call_count = 0
    total_tokens = 0
    total_cost_usd = 0.0
    summary = ""

    while tool_call_count < max_steps:
        result = await llm.chat(model=model, messages=messages, tools=registry.openai_schemas())
        total_tokens += result.usage.total_tokens
        total_cost_usd += result.cost_usd
        await sink.llm_call(
            JobPhase.RESEARCHING,
            model,
            result.usage.total_tokens,
            result.cost_usd,
            summary=(result.content or "")[:200] or f"{len(result.tool_calls)} tool call(s) requested",
        )

        if not result.tool_calls:
            summary = result.content or "Research loop concluded with no summary."
            break

        messages.append(
            {
                "role": "assistant",
                "content": result.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                    }
                    for tc in result.tool_calls
                ],
            }
        )

        for tc in result.tool_calls:
            await sink.tool_call(JobPhase.RESEARCHING, tc.name, tc.arguments)
            tool_result = await registry.call(tc.name, tc.arguments)
            _record_evidence(evidence, tc.name, tool_result)
            await sink.tool_result(JobPhase.RESEARCHING, tc.name, tool_result.ok, tool_result.content[:200])
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": tool_result.content[:4000]})
            tool_call_count += 1
            if tool_call_count >= max_steps:
                break

        if tool_call_count >= max_steps:
            summary = "Reached the tool-call step limit for this research pass."
            break

    return ResearchLoopResult(summary, tool_call_count, total_tokens, total_cost_usd)


def _record_evidence(evidence: EvidenceStore, tool_name: str, tool_result: ToolResult) -> None:
    if not tool_result.ok or not tool_result.citation:
        return
    if tool_name == "web_search":
        for hit in tool_result.citation.get("hits", []):
            evidence.add(hit["url"], hit["title"], hit["snippet"])
    elif tool_name == "fetch_url":
        url = tool_result.citation.get("url")
        if url:
            evidence.add(url, url, tool_result.content[:500])
