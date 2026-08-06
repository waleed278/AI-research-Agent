# ADR 0003: Structured outputs for every LLM call that feeds code

## Status
Accepted

## Context
The planner, critic, and synthesizer stages all produce output that the
orchestrator immediately parses and acts on (a list of sub-questions, a
pass/fail verdict with follow-up queries, a final report). The naive
approach -- ask the model to "respond in JSON" in the prompt and
`json.loads()` the result -- is exactly the kind of thing that works in a
demo and then intermittently breaks in production when the model wraps the
JSON in prose, uses trailing commas, or truncates mid-object.

## Decision
Every such call goes through `LLMClient.structured()`
(`app/llm/client.py`), which uses OpenAI's structured-outputs mode
(`client.chat.completions.parse(..., response_format=SomePydanticModel)`)
and validates the result against a Pydantic model
(`PlannerOutput`, `CriticVerdict`, `SynthesizerOutput` in `app/agent/state.py`,
plus `CoverageVerdict`/`GroundednessVerdict` in `evals/judge.py`). If the
response is refused or incomplete (e.g. truncated by a length limit), the
client retries once with an explicit instruction to comply, and raises
`StructuredOutputError` rather than returning something the caller would
have to defensively re-validate.

## Consequences
- No `json.loads()` + manual field-checking anywhere in the agent code --
  the moment `.structured()` returns, the caller has a real, type-checked
  Pydantic instance.
- The "one repair retry" behavior is itself unit-tested
  (`tests/unit/test_llm_client.py::test_structured_repairs_once_on_incomplete_response`)
  against a mocked incomplete-then-complete response sequence, without
  needing a real flaky model call to reproduce it.
- Free-form tool-calling (the research loop) intentionally does *not* go
  through `.structured()` -- `LLMClient.chat()` is used instead, because
  that call's job is to *decide which tool to call next*, not to produce a
  final answer; OpenAI's function/tool-calling mechanism already gives that
  a well-typed contract (`ToolCallRequest`) without needing the stricter
  structured-output mode.
