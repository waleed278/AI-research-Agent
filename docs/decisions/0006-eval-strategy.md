# ADR 0006: Separate the free/mocked CI gate from the paid eval suite

## Status
Accepted

## Context
This project has two different kinds of "does this still work" checks that
are easy to conflate but should not run on the same trigger:

1. **Does the code behave correctly given a specific input?** -- ordinary
   software correctness, answerable deterministically with mocks (does the
   SSRF guard reject `169.254.169.254`, does the orchestrator stop at the
   step cap, does the API return 404 for an unknown job).
2. **Is the agent's actual output any good?** -- a report-quality question
   that fundamentally requires a real LLM call (and, for a full check, a
   real search provider), is not fully deterministic, and costs real money
   per run.

Running (2) on every push would make CI slow, flaky (model output varies
run to run), and expensive purely as a side effect of opening a PR.

## Decision
- **CI** (`.github/workflows/ci.yml`, `lint-and-test` job): lint, type
  check, and the full `pytest` suite (unit + integration), all against
  mocked LLM/search providers -- zero API calls, zero cost, fully
  deterministic. It also runs `evals/run_evals.py --mock`, which exercises
  the *eval harness's own plumbing* (scoring, aggregation, report writing)
  end to end using a scripted fake LLM (`MockAgentLLM`) -- this proves the
  harness works without paying to find that out.
- **The real eval suite** (`make eval`, or the `eval-live` GitHub Actions
  job) runs the agent against the golden dataset
  (`evals/golden_dataset.jsonl`) with a real `LLMClient` and the configured
  search provider, scores each result with a deterministic citation check
  (`evals/metrics.py`) plus two LLM-as-judge checks (`evals/judge.py`:
  coverage against a must-cover checklist, and groundedness against the
  actual retrieved source snippets), and exits non-zero if the aggregate
  score falls below `--fail-under`. This only runs when a developer
  deliberately invokes it (or via `workflow_dispatch`) -- e.g. before
  merging a prompt or model change.

## Consequences
- Every PR gets a fast, free, deterministic signal. No PR is ever blocked
  or slowed down by LLM API latency or cost.
- The eval suite exists as the actual pre-merge gate for changes that could
  affect output quality (a prompt edit, a model swap, a change to the
  critic's acceptance criteria) -- run it manually, read the per-query
  report in `evals/reports/`, and decide.
- The judge itself is a real LLM call and therefore an imperfect oracle --
  it is deliberately rubric-based and temperature-0 (see `evals/judge.py`)
  to reduce variance, but is not a substitute for a human spot-checking the
  reports before shipping a change that scores lower than expected.
