import uuid

from arq.connections import RedisSettings

from app.agent.orchestrator import Orchestrator
from app.agent.state import AttachmentInput
from app.core.config import get_settings
from app.core.crypto import DecryptionError, decrypt_secret
from app.core.exceptions import AgentRunLimitExceeded
from app.core.logging import configure_logging, get_logger
from app.db.models import JobStatus
from app.db.repositories import LlmCredentialRepository, ResearchJobRepository
from app.db.session import get_session_factory
from app.llm.factory import build_provider
from app.services.research_service import DbTraceSink

logger = get_logger(__name__)


async def startup(ctx: dict) -> None:
    configure_logging(get_settings().log_level)


async def shutdown(ctx: dict) -> None:
    pass


async def run_research_job(ctx: dict, job_id: str) -> None:
    """The arq job entrypoint. Loads the job, builds a provider client from
    *that job's owner's* decrypted BYOK credential (never shared or cached
    across jobs -- different jobs can belong to different users with
    different keys, see app/llm/factory.py), runs the orchestrator against
    it with a DB-backed trace sink, and always leaves the job in a terminal
    status (`completed` or `failed`) -- a job should never be left dangling
    in `running` because the worker crashed without recording anything."""
    settings = get_settings()
    session_factory = get_session_factory()

    async with session_factory() as session:
        jobs = ResearchJobRepository(session)
        job = await jobs.get(uuid.UUID(job_id))
        if job is None:
            logger.warning("research_job_not_found", job_id=job_id)
            return
        if job.status == JobStatus.CANCELLED:
            logger.info("research_job_cancelled_before_start", job_id=job_id)
            return

        credential = await LlmCredentialRepository(session).get_for_provider(
            job.user_id, job.llm_provider
        )
        if credential is None:
            # Job creation requires a valid credential to exist (see
            # app/services/research_service.py), so this means it was
            # deleted after the job was queued but before the worker
            # picked it up -- rare, but must fail cleanly, not crash.
            logger.warning(
                "research_job_missing_credential", job_id=job_id, provider=job.llm_provider.value
            )
            await jobs.set_status(
                job,
                JobStatus.FAILED,
                error=f"No {job.llm_provider.value} credential configured for this account.",
            )
            await session.commit()
            return

        try:
            api_key = decrypt_secret(credential.encrypted_key, settings)
        except DecryptionError:
            logger.exception("research_job_credential_decryption_failed", job_id=job_id)
            await jobs.set_status(
                job, JobStatus.FAILED, error="Stored credential could not be decrypted."
            )
            await session.commit()
            return

        llm = build_provider(job.llm_provider, api_key, settings)

        await jobs.set_status(job, JobStatus.RUNNING)
        await session.commit()

        sink = DbTraceSink(session, job)
        orchestrator = Orchestrator(llm=llm, model=job.llm_model, settings=settings)
        attachments = [
            AttachmentInput(filename=attachment.filename, text=attachment.extracted_text)
            for attachment in job.attachments
        ]

        try:
            result = await orchestrator.run(
                query=job.query,
                max_iterations=job.max_iterations,
                max_sources=job.max_sources,
                attachments=attachments,
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
