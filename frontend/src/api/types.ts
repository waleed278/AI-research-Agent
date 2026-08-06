// Mirrors app/schemas/research.py and app/db/models.py -- kept as plain
// types (not generated) since the API surface is small and stable; if it
// grows, generating these from the FastAPI OpenAPI schema would be the
// next step.

export type JobStatus = "queued" | "running" | "completed" | "failed" | "cancelled";

export type JobPhase = "planning" | "researching" | "critiquing" | "synthesizing" | "done";

export type TraceEventType =
  | "phase_change"
  | "llm_call"
  | "tool_call"
  | "tool_result"
  | "error";

export interface ResearchJobCreateRequest {
  query: string;
  max_iterations?: number;
  max_sources?: number;
}

export interface ResearchJobCreateResponse {
  id: string;
  status: JobStatus;
}

export interface SourceResponse {
  id: number;
  url: string;
  title: string;
}

export interface ResearchResultResponse {
  report_markdown: string;
  sources: SourceResponse[];
}

export interface ResearchJobResponse {
  id: string;
  query: string;
  status: JobStatus;
  phase: JobPhase | null;
  error: string | null;
  total_tokens: number;
  total_cost_usd: number;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  result: ResearchResultResponse | null;
}

export interface ResearchJobListResponse {
  items: ResearchJobResponse[];
  next_cursor: string | null;
}

export const TERMINAL_STATUSES: readonly JobStatus[] = ["completed", "failed", "cancelled"];

export function isTerminalStatus(status: JobStatus): boolean {
  return (TERMINAL_STATUSES as string[]).includes(status);
}

// --- SSE event payloads (see app/api/v1/routes/research.py: stream_job_events) ---

export interface JobTraceEventPayload {
  seq: number;
  phase: JobPhase;
  payload: Record<string, unknown>;
  tokens_used: number;
  cost_usd: number;
}

export interface JobStatusEventPayload {
  status: JobStatus;
}

export type JobEventMessage =
  | { event: TraceEventType; data: JobTraceEventPayload }
  | { event: "job_status"; data: JobStatusEventPayload };
