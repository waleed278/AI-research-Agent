.PHONY: install lint typecheck test test-cov eval eval-mock run worker migrate compose-up compose-down

install:
	uv sync

lint:
	uv run ruff check .

typecheck:
	uv run mypy app

test:
	uv run pytest -q

test-cov:
	uv run pytest --cov=app --cov-report=term-missing

# Real eval run against live OpenAI/Tavily APIs -- spends API budget, run deliberately.
eval:
	uv run python -m evals.run_evals --fail-under 0.8

# Offline eval run against the mock providers -- proves the scoring harness works, costs nothing.
eval-mock:
	uv run python -m evals.run_evals --mock --fail-under 0.0

run:
	uv run uvicorn app.main:app --reload --port 8000

worker:
	uv run arq app.workers.worker.WorkerSettings

migrate:
	uv run alembic upgrade head

compose-up:
	docker compose -f infra/docker-compose.yml up -d --build

compose-down:
	docker compose -f infra/docker-compose.yml down
