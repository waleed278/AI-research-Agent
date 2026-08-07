import type {
  AddLlmCredentialRequest,
  ApiKeyCreateResponse,
  ApiKeyResponse,
  CreateApiKeyRequest,
  LlmCredentialResponse,
  LoginRequest,
  ResearchJobCreateRequest,
  ResearchJobCreateResponse,
  ResearchJobListResponse,
  ResearchJobResponse,
  SignupRequest,
  TokenResponse,
  UploadedFileResponse,
  UserResponse,
} from "./types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
}

async function toApiError(response: Response): Promise<ApiError> {
  // The backend returns RFC 7807 application/problem+json bodies (see
  // app/core/exceptions.py) -- surface `detail` when present, otherwise
  // fall back to the raw HTTP status text.
  let detail = response.statusText;
  try {
    const problem = (await response.json()) as { detail?: string };
    detail = problem.detail ?? detail;
  } catch {
    // Non-JSON error body (e.g. a proxy error page) -- keep statusText.
  }
  return new ApiError(response.status, detail);
}

/**
 * `token` is a JWT (`Authorization: Bearer`, what the web app uses after
 * login/signup) or a developer API key passed the same way is NOT supported
 * here -- this client always uses Bearer auth. Pass `null` for the two
 * unauthenticated auth endpoints (signup/login).
 */
async function request<T>(token: string | null, path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${BASE_URL}${path}`, {
    method: options.method ?? "GET",
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });

  if (!response.ok) throw await toApiError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

// --- Auth ---

export function signup(body: SignupRequest): Promise<TokenResponse> {
  return request(null, "/v1/auth/signup", { method: "POST", body });
}

export function login(body: LoginRequest): Promise<TokenResponse> {
  return request(null, "/v1/auth/login", { method: "POST", body });
}

export function getMe(token: string): Promise<UserResponse> {
  return request(token, "/v1/auth/me");
}

// --- Research jobs ---

export function createJob(
  token: string,
  body: ResearchJobCreateRequest,
): Promise<ResearchJobCreateResponse> {
  return request(token, "/v1/research-jobs", { method: "POST", body });
}

export function getJob(token: string, jobId: string): Promise<ResearchJobResponse> {
  return request(token, `/v1/research-jobs/${jobId}`);
}

export function listJobs(token: string, limit = 20): Promise<ResearchJobListResponse> {
  return request(token, `/v1/research-jobs?limit=${limit}`);
}

export function cancelJob(token: string, jobId: string): Promise<ResearchJobResponse> {
  return request(token, `/v1/research-jobs/${jobId}`, { method: "DELETE" });
}

export function jobEventsUrl(jobId: string): string {
  return `${BASE_URL}/v1/research-jobs/${jobId}/events`;
}

// --- Developer API keys ---

export function listApiKeys(token: string): Promise<ApiKeyResponse[]> {
  return request(token, "/v1/me/api-keys");
}

export function createApiKey(token: string, body: CreateApiKeyRequest): Promise<ApiKeyCreateResponse> {
  return request(token, "/v1/me/api-keys", { method: "POST", body });
}

export function revokeApiKey(token: string, keyId: string): Promise<void> {
  return request(token, `/v1/me/api-keys/${keyId}`, { method: "DELETE" });
}

// --- LLM credentials (BYOK provider keys) ---

export function listCredentials(token: string): Promise<LlmCredentialResponse[]> {
  return request(token, "/v1/me/llm-credentials");
}

export function addCredential(
  token: string,
  body: AddLlmCredentialRequest,
): Promise<LlmCredentialResponse> {
  return request(token, "/v1/me/llm-credentials", { method: "POST", body });
}

export function deleteCredential(token: string, credentialId: string): Promise<void> {
  return request(token, `/v1/me/llm-credentials/${credentialId}`, { method: "DELETE" });
}

// --- Uploads ---

// Multipart, so it can't go through the JSON `request()` helper -- the
// browser needs to set its own `Content-Type` (with the multipart boundary).
export async function uploadFile(token: string, file: File): Promise<UploadedFileResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${BASE_URL}/v1/uploads`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });

  if (!response.ok) throw await toApiError(response);
  return (await response.json()) as UploadedFileResponse;
}
