import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { JobEventMessage } from "../api/types";
import { ProgressPanel } from "./ProgressPanel";

describe("ProgressPanel", () => {
  it("shows a waiting message when no events have arrived yet", () => {
    render(<ProgressPanel phase="planning" events={[]} />);
    expect(screen.getByText(/waiting for the agent to start/i)).toBeInTheDocument();
  });

  it("renders a log line for each trace event", () => {
    const events: JobEventMessage[] = [
      {
        event: "phase_change",
        data: { seq: 1, phase: "planning", payload: { phase: "planning" }, tokens_used: 0, cost_usd: 0 },
      },
      {
        event: "tool_call",
        data: {
          seq: 2,
          phase: "researching",
          payload: { tool: "web_search", arguments: { query: "test query" } },
          tokens_used: 0,
          cost_usd: 0,
        },
      },
    ];
    render(<ProgressPanel phase="researching" events={events} />);
    expect(screen.getByText(/moved to the planning phase/i)).toBeInTheDocument();
    expect(screen.getByText(/searching: "test query"/i)).toBeInTheDocument();
  });
});
