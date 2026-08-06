import type { JobEventMessage, JobPhase } from "../api/types";

export const PHASE_ORDER: JobPhase[] = [
  "planning",
  "researching",
  "critiquing",
  "synthesizing",
  "done",
];

export const PHASE_LABELS: Record<JobPhase, string> = {
  planning: "Planning",
  researching: "Researching",
  critiquing: "Critiquing",
  synthesizing: "Synthesizing",
  done: "Done",
};

/** A short, human-readable line for one trace event -- mirrors the shape
 * the backend records in app/services/research_service.py (DbTraceSink). */
export function describeEvent(message: JobEventMessage): string {
  if (message.event === "job_status") {
    return `Job status: ${message.data.status}`;
  }

  const { payload } = message.data;

  switch (message.event) {
    case "phase_change":
      return `Moved to the ${String(payload.phase)} phase`;
    case "llm_call":
      return `Model call (${String(payload.model)}): ${String(payload.summary ?? "")}`;
    case "tool_call": {
      const tool = String(payload.tool);
      const args = payload.arguments as Record<string, unknown> | undefined;
      if (tool === "web_search" && args?.query) return `Searching: "${String(args.query)}"`;
      if (tool === "fetch_url" && args?.url) return `Reading: ${String(args.url)}`;
      return `Calling tool: ${tool}`;
    }
    case "tool_result": {
      const tool = String(payload.tool);
      const ok = payload.ok ? "succeeded" : "failed";
      return `${tool} ${ok}${payload.summary ? ` -- ${String(payload.summary)}` : ""}`;
    }
    case "error":
      return `Error: ${String(payload.message ?? "unknown error")}`;
    default:
      // Exhaustive over TraceEventType -- this branch only exists as a
      // type-safe fallback if the backend ever adds a new event type.
      return "Unknown event";
  }
}
