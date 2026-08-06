from starlette.requests import Request
from starlette.responses import JSONResponse


class AppError(Exception):
    """Base class for domain errors that should surface to the API caller
    as a well-formed problem+json response instead of a raw 500."""

    status_code = 500
    title = "Internal Server Error"

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail or self.title
        super().__init__(self.detail)


class NotFoundError(AppError):
    status_code = 404
    title = "Resource Not Found"


class InvalidRequestError(AppError):
    status_code = 422
    title = "Invalid Request"


class UnauthorizedError(AppError):
    status_code = 401
    title = "Unauthorized"


class RateLimitedError(AppError):
    status_code = 429
    title = "Too Many Requests"


class ConflictError(AppError):
    status_code = 409
    title = "Conflict"


class AgentRunLimitExceeded(AppError):
    """Raised internally when a research job hits its step/token/time caps.
    Not a client error -- caught by the worker and turned into a job status
    of 'failed' with this as the reason, never bubbles to the HTTP layer."""

    status_code = 500
    title = "Agent Run Limit Exceeded"


async def app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """RFC 7807 (application/problem+json) so every error -- ours or a
    dependency's -- has the same predictable shape for API consumers.

    Typed as `Exception` (not `AppError`) to match Starlette's exception
    handler signature -- FastAPI only ever calls this for `AppError`
    subclasses because that's what it's registered against.
    """
    assert isinstance(exc, AppError)  # noqa: S101 - guaranteed by handler registration, see above
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "type": f"https://errors.research-agent.dev/{exc.__class__.__name__}",
            "title": exc.title,
            "status": exc.status_code,
            "detail": exc.detail,
            "instance": str(request.url.path),
        },
        media_type="application/problem+json",
    )
