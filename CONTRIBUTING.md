# Contributing to AI Research & Report Agent

## Workflow

1. Start from a scoped issue.
2. Create a focused branch from `main`.
3. Keep agent, API, worker, frontend, and infrastructure changes separated when practical.
4. Run the existing CI-quality commands locally before requesting review.
5. Update ADRs when a non-obvious architectural decision changes.
6. Add or update eval coverage when behavior changes affect report quality.

## Pull requests

Include:
- problem and approach
- affected layers
- verification/tests
- eval impact where applicable
- migration or deployment notes
- follow-up work

Never commit API keys, seeded production credentials, or user research data.
