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

// Mirrors app.db.models.LlmProvider.
export type LlmProvider = "openai" | "gemini" | "anthropic";

// Mirrors SUPPORTED_MODELS / DEFAULT_MODEL_BY_PROVIDER in app/core/config.py.
// Kept in sync by hand -- update both sides if the backend's allow-list changes.
export const SUPPORTED_MODELS: Record<LlmProvider, string[]> = {
  openai: ["gpt-4o", "gpt-4o-mini"],
  gemini: ["gemini-2.0-flash", "gemini-1.5-pro"],
  anthropic: ["claude-sonnet-5", "claude-haiku-4-5-20251001"],
};

export const DEFAULT_MODEL_BY_PROVIDER: Record<LlmProvider, string> = {
  openai: "gpt-4o-mini",
  gemini: "gemini-2.0-flash",
  anthropic: "claude-haiku-4-5-20251001",
};

export const PROVIDER_LABELS: Record<LlmProvider, string> = {
  openai: "OpenAI",
  gemini: "Gemini",
  anthropic: "Anthropic",
};

export interface ResearchJobCreateRequest {
  query: string;
  provider: LlmProvider;
  model?: string;
  max_iterations?: number;
  max_sources?: number;
  attachment_ids?: string[];
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
  llm_provider: LlmProvider;
  llm_model: string;
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

// --- Auth (mirrors app/schemas/auth.py) ---

export interface SignupRequest {
  email: string;
  password: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface UserResponse {
  id: string;
  email: string;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: UserResponse;
}

// --- Developer API keys (mirrors app/schemas/api_keys.py) ---

export interface CreateApiKeyRequest {
  name: string;
}

export interface ApiKeyCreateResponse {
  id: string;
  name: string;
  raw_key: string;
  created_at: string;
}

export interface ApiKeyResponse {
  id: string;
  name: string;
  is_active: boolean;
  created_at: string;
}

// --- LLM credentials, i.e. BYOK provider keys (mirrors app/schemas/credentials.py) ---

export interface AddLlmCredentialRequest {
  provider: LlmProvider;
  api_key: string;
  label?: string;
}

export interface LlmCredentialResponse {
  id: string;
  provider: LlmProvider;
  label: string | null;
  is_valid: boolean;
  created_at: string;
  last_validated_at: string | null;
}

// --- Uploads (mirrors app/schemas/uploads.py) ---

export interface UploadedFileResponse {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  extracted_chars: number;
  created_at: string;
}
