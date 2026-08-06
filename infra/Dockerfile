# --- builder: resolve deps with uv into a venv ---
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /bin/

# Same path as the runtime stage's WORKDIR below -- uv-created venvs bake
# absolute shebang paths into their scripts (`.venv/bin/alembic`, etc.), so
# copying `.venv` into a container where it lives at a different path than
# it was built at breaks every entrypoint script with "no such file or
# directory" (the interpreter path in the shebang no longer exists).
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY pyproject.toml uv.lock* README.md ./
RUN uv sync --no-dev --no-install-project

COPY app ./app
COPY evals ./evals
COPY alembic ./alembic
COPY alembic.ini ./
RUN uv sync --no-dev

# --- runtime: slim image, non-root ---
FROM python:3.12-slim AS runtime

RUN groupadd -r appuser && useradd -r -g appuser appuser
WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/app /app/app
COPY --from=builder /app/evals /app/evals
COPY --from=builder /app/alembic /app/alembic
COPY --from=builder /app/alembic.ini /app/alembic.ini

ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
