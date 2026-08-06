import type {
  ResearchJobCreateRequest,
  ResearchJobCreateResponse,
  ResearchJobListResponse,
  ResearchJobResponse,
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

async function request<T>(apiKey: string, path: string, options: RequestOptions = {}): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    method: options.method ?? "GET",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": apiKey,
    },
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });

  if (!response.ok) {
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
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export function createJob(
  apiKey: string,
  body: ResearchJobCreateRequest,
): Promise<ResearchJobCreateResponse> {
  return request(apiKey, "/v1/research-jobs", { method: "POST", body });
}

export function getJob(apiKey: string, jobId: string): Promise<ResearchJobResponse> {
  return request(apiKey, `/v1/research-jobs/${jobId}`);
}

export function listJobs(apiKey: string, limit = 20): Promise<ResearchJobListResponse> {
  return request(apiKey, `/v1/research-jobs?limit=${limit}`);
}

export function cancelJob(apiKey: string, jobId: string): Promise<ResearchJobResponse> {
  return request(apiKey, `/v1/research-jobs/${jobId}`, { method: "DELETE" });
}

export function jobEventsUrl(jobId: string): string {
  return `${BASE_URL}/v1/research-jobs/${jobId}/events`;
}
