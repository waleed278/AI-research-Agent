import uuid

from arq.connections import RedisSettings

from app.agent.orchestrator import Orchestrator
from app.core.config import get_settings
from app.core.exceptions import AgentRunLimitExceeded
from app.core.logging import configure_logging, get_logger
from app.db.models import JobStatus
from app.db.repositories import ResearchJobRepository
from app.db.session import get_session_factory
from app.llm.client import LLMClient
from app.services.research_service import DbTraceSink

logger = get_logger(__name__)


async def startup(ctx: dict) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    # One shared LLMClient (and therefore one shared HTTP connection pool)
    # per worker process, reused across every job it picks up.
    ctx["llm"] = LLMClient(settings)


async def shutdown(ctx: dict) -> None:
    pass


async def run_research_job(ctx: dict, job_id: str) -> None:
    """The arq job entrypoint. Loads the job, runs the orchestrator against
    it with a DB-backed trace sink, and always leaves the job in a terminal
    status (`completed` or `failed`) -- a job should never be left dangling
    in `running` because the worker crashed without recording anything."""
    settings = get_settings()
    session_factory = get_session_factory()
    llm: LLMClient = ctx.get("llm") or LLMClient(settings)

    async with session_factory() as session:
        jobs = ResearchJobRepository(session)
        job = await jobs.get(uuid.UUID(job_id))
        if job is None:
            logger.warning("research_job_not_found", job_id=job_id)
            return
        if job.status == JobStatus.CANCELLED:
            logger.info("research_job_cancelled_before_start", job_id=job_id)
            return

        await jobs.set_status(job, JobStatus.RUNNING)
        await session.commit()

        sink = DbTraceSink(session, job)
        orchestrator = Orchestrator(llm=llm, settings=settings)

        try:
            result = await orchestrator.run(
                query=job.query,
                max_iterations=job.max_iterations,
                max_sources=job.max_sources,
                sink=sink,
            )
        except AgentRunLimitExceeded as exc:
            logger.warning("research_job_limit_exceeded", job_id=job_id, reason=str(exc))
            await jobs.set_status(job, JobStatus.FAILED, error=str(exc))
            await session.commit()
            return
        except Exception as exc:  # noqa: BLE001 - last line of defense; must not crash the worker loop
            logger.exception("research_job_failed", job_id=job_id)
            await jobs.set_status(job, JobStatus.FAILED, error=str(exc))
            await session.commit()
            return

        sources = [s.model_dump() for s in result.sources]
        await jobs.save_result(job, result.report_markdown, sources)
        await jobs.set_status(job, JobStatus.COMPLETED)
        await session.commit()
        logger.info(
            "research_job_completed",
            job_id=job_id,
            total_tokens=result.total_tokens,
            total_cost_usd=result.total_cost_usd,
            tool_call_count=result.tool_call_count,
        )


class WorkerSettings:
    functions = [run_research_job]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    job_timeout = get_settings().agent_job_timeout_seconds + 30
    max_jobs = 5
