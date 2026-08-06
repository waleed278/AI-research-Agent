import logging
import sys

import structlog


def configure_logging(log_level: str = "INFO") -> None:
    """Structured JSON logging everywhere. request_id / job_id are bound
    per-context (see api/middleware.py and workers/worker.py) so every log
    line emitted while handling a request or running a job carries it --
    the single most useful thing for debugging a distributed agent run
    after the fact."""

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=log_level)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(log_level)),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    return structlog.get_logger(name)
