import asyncio

from app.agent.critic import critique
from app.agent.planner import plan
from app.agent.research_loop import run_research_loop
from app.agent.state import AttachmentInput, EvidenceStore, NullTraceSink, RunResult, TraceSink
from app.agent.synthesizer import synthesize
from app.core.config import Settings, get_settings
from app.core.exceptions import AgentRunLimitExceeded
from app.core.logging import get_logger
from app.db.models import JobPhase
from app.llm.base import LLMProvider
from app.tools.registry import ToolRegistry, default_registry

logger = get_logger(__name__)


class _UsageTracker:
    """Enforces the per-job token budget across every LLM call the
    orchestrator makes, regardless of which phase it happened in. This is
    the actual cost-control mechanism -- prompts and step counts bound
    *effort*, this bounds *spend*."""

    def __init__(self, max_tokens: int) -> None:
        self._max_tokens = max_tokens
        self.total_tokens = 0
        self.total_cost_usd = 0.0

    def add(self, tokens: int, cost_usd: float) -> None:
        self.total_tokens += tokens
        self.total_cost_usd += cost_usd
        if self.total_tokens > self._max_tokens:
            raise AgentRunLimitExceeded(
                f"Job exceeded token budget ({self.total_tokens} > {self._max_tokens} tokens)"
            )


class Orchestrator:
    """Runs a research job through the fixed Plan -> Research -> Critique ->
    Synthesize state machine. This is the whole "agent" -- everything else
    (tools, LLM adapter, prompts) exists to support this class."""

    def __init__(
        self,
        llm: LLMProvider,
        model: str,
        registry: ToolRegistry | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.llm = llm
        self.model = model
        self.registry = registry or default_registry()
        self.settings = settings or get_settings()

    async def run(
        self,
        query: str,
        max_iterations: int,
        max_sources: int,
        attachments: list[AttachmentInput] | None = None,
        sink: TraceSink | None = None,
    ) -> RunResult:
        sink = sink or NullTraceSink()
        try:
            return await asyncio.wait_for(
                self._run(query, max_iterations, max_sources, attachments or [], sink),
                timeout=self.settings.agent_job_timeout_seconds,
            )
        except TimeoutError as exc:
            await sink.error(JobPhase.DONE, "Job exceeded wall-clock timeout")
            raise AgentRunLimitExceeded("Job exceeded wall-clock timeout") from exc

    async def _run(
        self,
        query: str,
        max_iterations: int,
        max_sources: int,
        attachments: list[AttachmentInput],
        sink: TraceSink,
    ) -> RunResult:
        model = self.model
        usage = _UsageTracker(self.settings.agent_max_tokens_per_job)
        # Uploaded documents share the same max_sources budget as web
        # sources (see EvidenceStore's max_items) -- a job attaching more
        # files than the budget allows just means fewer web sources get
        # room, which is the right tradeoff: the user handed those documents
        # over deliberately, an untrusted web search result did not.
        evidence = EvidenceStore(max_items=max_sources)
        for attachment in attachments:
            evidence.add(
                url=f"upload://{attachment.filename}",
                title=attachment.filename,
                snippet=attachment.text,
            )
        tool_call_count = 0

        await sink.phase_change(JobPhase.PLANNING)
        planner_result = await plan(self.llm, model, query, attachments)
        usage.add(planner_result.usage.total_tokens, planner_result.cost_usd)
        await sink.llm_call(
            JobPhase.PLANNING,
            model,
            planner_result.usage.total_tokens,
            planner_result.cost_usd,
            summary=f"{len(planner_result.data.sub_questions)} sub-questions planned",
        )
        sub_questions = [sq.question for sq in planner_result.data.sub_questions]

        step_budget = min(max_iterations, self.settings.agent_max_tool_steps)

        await sink.phase_change(JobPhase.RESEARCHING)
        loop_result = await run_research_loop(
            llm=self.llm,
            model=model,
            registry=self.registry,
            query=query,
            sub_questions=sub_questions,
            evidence=evidence,
            sink=sink,
            max_steps=step_budget,
        )
        usage.add(loop_result.total_tokens, loop_result.total_cost_usd)
        tool_call_count += loop_result.tool_call_count

        for _ in range(self.settings.agent_max_revision_loops):
            await sink.phase_change(JobPhase.CRITIQUING)
            critic_result = await critique(self.llm, model, query, sub_questions, evidence)
            usage.add(critic_result.usage.total_tokens, critic_result.cost_usd)
            verdict = critic_result.data
            await sink.llm_call(
                JobPhase.CRITIQUING,
                model,
                critic_result.usage.total_tokens,
                critic_result.cost_usd,
                summary=verdict.rationale[:200],
            )

            if (verdict.coverage_ok and verdict.grounding_ok) or not verdict.revise_queries:
                break

            remaining_steps = self.settings.agent_max_tool_steps - tool_call_count
            if remaining_steps <= 0:
                break

            await sink.phase_change(JobPhase.RESEARCHING)
            extra_instruction = "The critic identified gaps -- search specifically for:\n" + "\n".join(
                f"- {q}" for q in verdict.revise_queries
            )
            loop_result = await run_research_loop(
                llm=self.llm,
                model=model,
                registry=self.registry,
                query=query,
                sub_questions=sub_questions,
                evidence=evidence,
                sink=sink,
                max_steps=remaining_steps,
                extra_instruction=extra_instruction,
            )
            usage.add(loop_result.total_tokens, loop_result.total_cost_usd)
            tool_call_count += loop_result.tool_call_count

        await sink.phase_change(JobPhase.SYNTHESIZING)
        synth_result = await synthesize(self.llm, model, query, sub_questions, evidence)
        usage.add(synth_result.usage.total_tokens, synth_result.cost_usd)
        await sink.llm_call(
            JobPhase.SYNTHESIZING,
            model,
            synth_result.usage.total_tokens,
            synth_result.cost_usd,
            summary="report synthesized",
        )

        await sink.phase_change(JobPhase.DONE)
        return RunResult(
            report_markdown=synth_result.data.report_markdown,
            sources=evidence.items,
            total_tokens=usage.total_tokens,
            total_cost_usd=usage.total_cost_usd,
            tool_call_count=tool_call_count,
        )
