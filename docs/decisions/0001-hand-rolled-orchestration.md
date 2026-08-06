# ADR 0001: Hand-rolled agent orchestration instead of LangChain/LangGraph

## Status
Accepted

## Context
Every "agent" framework (LangGraph, CrewAI, AutoGen, etc.) is ultimately a
thin layer over the same primitive: an LLM call that can request a tool
call, a loop that executes the tool and feeds the result back, and some
state passed between steps. Adopting one buys convenience (built-in
persistence, visualization, community tool integrations) at the cost of a
large, fast-moving dependency and an abstraction that has to be learned on
top of the underlying API.

## Decision
The orchestrator (`app/agent/orchestrator.py`) is a plain Python class
implementing an explicit state machine -- Plan -> Research -> Critique ->
Synthesize -- built directly on the OpenAI SDK's chat completions and
structured-output APIs. The research loop (`app/agent/research_loop.py`) is
a hand-written ReAct-style tool-calling loop: call the model, check for
`tool_calls`, execute them via the `ToolRegistry`, append results, repeat.

## Consequences
- No framework version upgrades to track, no framework-specific debugging
  (stack traces are just this codebase's own functions).
- Every piece of agent behavior -- prompts, the tool-calling loop, the
  revision-loop policy, the token/step caps -- lives in this repository and
  is fully unit-testable with a fake `LLMClient` (see
  `tests/unit/test_orchestrator.py`), with no framework internals to mock.
- The cost is that some things a framework provides for free (checkpointing
  mid-run, a visual graph editor, prebuilt tool integrations) have to be
  built here if needed. For this project's scope, the trace-event table
  (`TraceEvent`, `TraceSink`) covers the checkpointing/observability need
  directly.
- If the agent's complexity grows substantially (many more node types,
  branching/parallel sub-agents), revisiting this decision in favor of
  LangGraph's graph execution model would be reasonable -- this is an ADR,
  not a permanent constraint.
