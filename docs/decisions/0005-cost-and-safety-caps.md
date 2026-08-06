# ADR 0005: Explicit cost and runaway-loop caps in the orchestrator

## Status
Accepted

## Context
An autonomous agent that decides for itself how many times to call a tool
or an LLM has no natural stopping point if a query is ambiguous, a tool
starts returning unhelpful results, or a model gets stuck re-issuing
similar searches. Left unchecked, that is a direct path to an unexpectedly
large OpenAI bill or a job that never terminates.

## Decision
Three independent caps, enforced at three different layers so no single bug
removes all of them:

1. **Step cap** (`AGENT_MAX_TOOL_STEPS`) -- the research loop
   (`research_loop.py`) counts *tool calls*, not LLM turns, and stops
   issuing new ones once the budget is spent, returning whatever summary it
   has.
2. **Token/cost cap** (`AGENT_MAX_TOKENS_PER_JOB`) -- `_UsageTracker` in
   `orchestrator.py` accumulates `total_tokens` across *every* phase
   (planning, research, critique, synthesis) and raises
   `AgentRunLimitExceeded` the moment the running total exceeds budget,
   even if the step cap above was never hit (e.g. a query that produces
   very long tool results).
3. **Wall-clock timeout** (`AGENT_JOB_TIMEOUT_SECONDS`) -- the entire
   `Orchestrator.run()` call is wrapped in `asyncio.wait_for`, so a single
   slow/hanging call anywhere in the pipeline can't leave a job (and the
   worker slot running it) stuck indefinitely.

All three surface as the job ending in `status=failed` with a specific
`error` message, not a crashed worker process (`workers/worker.py` catches
`AgentRunLimitExceeded` explicitly and records it).

## Consequences
- A misbehaving query costs at most one job's worth of budget, not an
  unbounded amount.
- The caps are deliberately conservative defaults
  (`agent_max_tool_steps=12`, `agent_max_tokens_per_job=200_000`,
  `agent_job_timeout_seconds=300`) meant to be tuned per deployment via
  environment variables, not hardcoded.
- This is intentionally *not* a token-bucket-style spend limit across jobs
  or across time (e.g. "$50/day org-wide") -- that's a billing/ops concern
  best enforced at the OpenAI project level or an API gateway, not
  duplicated in application code.
