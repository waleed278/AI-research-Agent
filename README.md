# AI Research & Report Agent

[![CI](https://github.com/waleed278/AI-research-Agent/actions/workflows/ci.yml/badge.svg)](https://github.com/waleed278/AI-research-Agent/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/Frontend-React%20%2B%20TypeScript-61DAFB?logo=react&logoColor=black)
![Docker](https://img.shields.io/badge/Infra-Docker-2496ED?logo=docker&logoColor=white)

A production-grade, async, tool-using research agent: give it a question,
it plans sub-questions, searches and reads the web, critiques its own
evidence, and writes a cited Markdown report -- as a background job behind
a versioned REST API, with an offline evaluation harness to actually measure
whether the reports it writes are any good.

Built to demonstrate the full stack of skills behind shipping an LLM/agent
feature in production, not just calling a chat completion: scalable API
design, a hand-rolled agentic tool-calling loop, structured LLM outputs,
cost/safety guardrails, and a real eval suite -- not just unit tests.

## Why this exists

Most "AI agent" portfolio projects are a LangChain quickstart with a nice
README. This one is built the way a small AI team would actually build and
ship an agent feature: async job architecture (a research run takes
30s-3min, so it's not a blocking HTTP call), an agent built directly on the
provider API (so the reasoning is inspectable, not hidden inside a
framework), explicit cost/runaway-loop caps, and an evaluation harness that
scores report quality (citation validity, coverage, groundedness) instead
of stopping at "the tests pass."

See [`docs/architecture.md`](docs/architecture.md) for the full system
diagram and [`docs/decisions/`](docs/decisions) for the reasoning behind
each non-obvious engineering choice (ADRs).

## Engineering highlights

- **Async job API, not a blocking endpoint.** `POST /research-jobs` returns
  `202` immediately; the job runs on an [arq](https://github.com/samuelcolvin/arq)
  (async Redis queue) worker, pollable via `GET /research-jobs/{id}` or a
  live `GET /research-jobs/{id}/events` Server-Sent Events stream.
- **Hand-rolled agent orchestration.** A `Plan -> Research -> Critique ->
  Synthesize` state machine built directly on the OpenAI tool-calling and
  structured-output APIs -- see [ADR 0001](docs/decisions/0001-hand-rolled-orchestration.md).
- **Structured outputs everywhere an LLM call feeds code**, with an
  automatic repair-retry on an incomplete/refused response -- no
  `json.loads()` on free text anywhere ([ADR 0003](docs/decisions/0003-structured-outputs-everywhere.md)).
- **Deterministic citations.** The agent never invents a source list -- it
  cites numeric IDs the code itself assigned as evidence was gathered, so
  citation validity is a mechanical check, not a judgment call.
- **SSRF-guarded tool use.** The `fetch_url` tool resolves and validates
  every hostname (and every redirect hop) before fetching, rejecting
  loopback/private/link-local addresses including the cloud metadata IP
  ([ADR 0004](docs/decisions/0004-ssrf-guard.md)).
- **Three independent cost/safety caps**: max tool-call steps, max tokens
  per job, and a wall-clock timeout, enforced at three different layers
  ([ADR 0005](docs/decisions/0005-cost-and-safety-caps.md)).
- **A real eval harness, not just tests.** `evals/` scores the agent
  against a 15-query golden dataset on citation validity (deterministic),
  plus LLM-as-judge coverage and groundedness scores -- separate from, and
  not run on every commit of, the free/mocked CI suite
  ([ADR 0006](docs/decisions/0006-eval-strategy.md)).
- **Full observability.** Every LLM call, tool call, and phase change is
  persisted as a `TraceEvent` *as it happens* (not batched at the end), so
  a failed job still leaves a full trace of what it did.
- **A real web UI**, not just curl. `frontend/` streams live agent progress
  via a hand-written SSE-over-`fetch` reader (browsers' `EventSource` can't
  send the API key header), backed by React Query polling as the actual
  source of truth so the UI never gets stuck if the stream drops
  ([ADR 0007](docs/decisions/0007-frontend-sse-and-proxy.md)).

## Tech stack

**Backend**: Python 3.11+ / FastAPI / SQLAlchemy 2.0 (async) + PostgreSQL /
arq + Redis / OpenAI API (structured outputs + tool calling) / Tavily
(pluggable, mock provider included) / pytest / ruff + mypy.

**Frontend**: React + TypeScript / Vite / Tailwind CSS / TanStack React
Query / react-markdown / Vitest.

**Infra**: Docker Compose / GitHub Actions.

## Quickstart

```bash
cp .env.example .env          # add a real OPENAI_API_KEY to actually run the agent
uv sync                       # install dependencies (https://docs.astral.sh/uv/)

# Everything (Postgres, Redis, API, worker) via Docker Compose:
make compose-up
make migrate

# ...or run the API/worker natively against Dockerized Postgres+Redis:
docker compose -f infra/docker-compose.yml up -d postgres redis
make migrate
make run       # FastAPI on http://localhost:8000 (docs at /docs)
make worker    # in a second terminal
```

Seed a dev API key, then create a job:

```bash
uv run python scripts/seed_api_key.py
curl -X POST http://localhost:8000/api/v1/research-jobs \
  -H "X-API-Key: dev-local-key" -H "Content-Type: application/json" \
  -d '{"query": "What are the main causes of the 2008 financial crisis?"}'

curl http://localhost:8000/api/v1/research-jobs/<id> -H "X-API-Key: dev-local-key"
```

Without a real `OPENAI_API_KEY`/`TAVILY_API_KEY`, set `SEARCH_PROVIDER=mock`
(the default in `.env.example`) to exercise the API and job lifecycle with
the deterministic mock search provider -- the OpenAI key is still required
for the LLM calls themselves.

## Web UI

`make compose-up` (or `docker compose -f infra/docker-compose.yml up -d
--build`) also builds and starts the frontend, served at
**http://localhost:3000**. Its nginx container reverse-proxies `/api/*` to
the backend, so no separate configuration is needed. On first load, enter
an API key (the seeded dev default is `dev-local-key`) when prompted, then
ask a research question -- you'll see live phase/tool-call progress while
it runs, then the rendered, cited report.

For frontend-only local development (hot reload against a locally-running
backend):

```bash
cd frontend
cp .env.example .env   # set VITE_API_BASE_URL=http://localhost:8000/api
docker run --rm -it -v "$PWD:/app" -w /app -p 5173:5173 node:20-alpine sh -c "npm install && npm run dev -- --host"
```

(No Node.js is required on the host -- this project builds and tests the
frontend entirely through Docker; see `make frontend-test` below.)

## Testing & evaluation

```bash
make lint          # ruff
make typecheck      # mypy
make test           # pytest (unit + integration; integration tests need Postgres,
                     # see docker-compose above -- they skip with a clear message if it's not up)
make eval-mock       # run the eval harness fully offline -- zero cost, proves the harness works
make eval            # run the real eval suite against live OpenAI/Tavily -- costs API budget
```

CI (`.github/workflows/ci.yml`) runs lint/typecheck/tests/`eval-mock` on
every push, fully mocked -- no secrets required, zero cost. The real
`eval-live` job is manual (`workflow_dispatch`) by design; see
[ADR 0006](docs/decisions/0006-eval-strategy.md) for why.

```bash
make frontend-lint   # eslint, run inside Docker (no local Node.js needed)
make frontend-test   # vitest (unit + component tests), same way
```

## Project layout

```
app/
  api/        FastAPI routes, auth, rate limiting, middleware
  agent/      the orchestrator + planner/research-loop/critic/synthesizer
  tools/      web_search, fetch_url (SSRF-guarded), tool registry
  llm/        OpenAI client wrapper: retries, structured outputs, cost tracking
  db/         SQLAlchemy models, session, repositories
  services/   job lifecycle + the DB-backed trace sink
  workers/    the arq worker entrypoint
evals/        golden dataset, LLM-as-judge, metrics, the eval CLI
tests/        unit tests (mocked) + integration tests (real Postgres, mocked LLM)
frontend/     React/TS/Vite web UI (api client, SSE reader, hooks, components)
infra/        Dockerfile, docker-compose.yml
docs/         architecture.md + ADRs
```
