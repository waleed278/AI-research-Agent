import { useEffect, useRef, useState } from "react";

import { streamJobEvents } from "../api/sse";
import type { JobEventMessage } from "../api/types";

/**
 * Live trace log for one job, via the manual SSE-over-fetch reader. Only
 * subscribes while `active` is true (the caller passes this as "job is
 * running") -- there's no reason to open a stream for a job that's already
 * finished and is just being viewed from history.
 */
export function useJobEvents(apiKey: string, jobId: string | null, active: boolean) {
  const [events, setEvents] = useState<JobEventMessage[]>([]);
  const currentJobId = useRef(jobId);

  useEffect(() => {
    setEvents([]);
    currentJobId.current = jobId;

    if (!jobId || !active || !apiKey) return;

    const unsubscribe = streamJobEvents(apiKey, jobId, {
      onEvent: (message) => {
        // Guards against a stale subscription's callback firing after the
        // user has already switched to a different job.
        if (currentJobId.current !== jobId) return;
        setEvents((prev) => [...prev, message]);
      },
      onError: (error) => {
        console.warn(`Job event stream for ${jobId} failed`, error);
      },
    });

    return unsubscribe;
  }, [apiKey, jobId, active]);

  return events;
}
