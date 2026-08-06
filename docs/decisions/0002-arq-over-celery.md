# ADR 0002: arq (async Redis queue) instead of Celery

## Status
Accepted

## Context
Research jobs need to run in a background worker, not inline in the HTTP
request (see `docs/architecture.md`). Celery is the default answer most
Python developers reach for; arq is a smaller, asyncio-native alternative
built on Redis.

The actual workload here -- calling the OpenAI API and fetching web pages --
is I/O-bound and already written against `asyncio` (the OpenAI SDK's async
client, `httpx.AsyncClient`). Celery's worker model is fundamentally
synchronous (prefork/threads); running async code inside it means wrapping
every task body in `asyncio.run(...)`, bridging between two concurrency
models for no benefit, since nothing here is CPU-bound.

## Decision
Use [arq](https://github.com/samuelcolvin/arq) for the job queue
(`app/workers/worker.py`). Jobs are plain `async def` functions; the worker
process runs them on a single asyncio event loop with real concurrency
across jobs, matching how the orchestrator itself already works.

## Consequences
- No sync/async bridging code anywhere in the worker path.
- Meaningfully simpler local development on Windows, where Celery's
  prefork worker pool has long-standing compatibility issues -- arq's
  asyncio-based worker has none of that.
- Smaller dependency surface than Celery (no separate result backend
  configuration, no Flower needed for basic visibility -- job state lives in
  Postgres via `TraceEvent`/`ResearchJob` instead).
- Trade-off: arq is far less widely known than Celery, and lacks some of
  Celery's ecosystem (scheduled/periodic tasks, richer routing, a mature
  monitoring UI). None of that is needed for this workload; if the project
  grew multiple heterogeneous background job types with complex routing
  needs, Celery would be worth reconsidering.
