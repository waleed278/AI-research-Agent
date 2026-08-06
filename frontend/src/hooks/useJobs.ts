import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { cancelJob, createJob, getJob, listJobs } from "../api/client";
import type { ResearchJobCreateRequest, ResearchJobResponse } from "../api/types";
import { isTerminalStatus } from "../api/types";

const JOBS_KEY = ["jobs"] as const;
const jobKey = (jobId: string) => ["jobs", jobId] as const;

export function useJobsList(apiKey: string) {
  return useQuery({
    queryKey: JOBS_KEY,
    queryFn: () => listJobs(apiKey),
    enabled: apiKey.length > 0,
    // Picks up status changes (queued -> running -> completed) for jobs
    // visible in the sidebar without the user needing to click into each one.
    refetchInterval: 5000,
  });
}

export function useJob(apiKey: string, jobId: string | null) {
  return useQuery({
    queryKey: jobId ? jobKey(jobId) : ["jobs", "none"],
    queryFn: () => getJob(apiKey, jobId as string),
    enabled: apiKey.length > 0 && jobId !== null,
    // This is the authoritative source of truth for status/result -- the
    // SSE stream (useJobEvents) is purely a live-log decoration on top of
    // it, so the UI still reaches the correct final state even if the
    // stream drops (see docs/decisions/0007-frontend-sse-and-proxy.md).
    refetchInterval: (query) => {
      const data = query.state.data as ResearchJobResponse | undefined;
      if (!data || !isTerminalStatus(data.status)) return 2000;
      return false;
    },
  });
}

export function useCreateJob(apiKey: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ResearchJobCreateRequest) => createJob(apiKey, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: JOBS_KEY });
    },
  });
}

export function useCancelJob(apiKey: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => cancelJob(apiKey, jobId),
    onSuccess: (_data, jobId) => {
      void queryClient.invalidateQueries({ queryKey: JOBS_KEY });
      void queryClient.invalidateQueries({ queryKey: jobKey(jobId) });
    },
  });
}
