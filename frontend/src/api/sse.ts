import { jobEventsUrl } from "./client";
import type { JobEventMessage } from "./types";

export interface SseHandlers {
  onEvent: (message: JobEventMessage) => void;
  onError?: (error: unknown) => void;
  onDone?: () => void;
}

const FRAME_BOUNDARY = /\r\n\r\n|\n\n|\r\r/;
const LINE_SPLIT = /\r\n|\n|\r/;

/**
 * Subscribes to a job's SSE stream via `fetch` + `ReadableStream` instead of
 * the browser's native `EventSource`. `EventSource` cannot set custom
 * request headers, and this endpoint is authenticated with an
 * `Authorization: Bearer` header (see docs/decisions/0007-frontend-sse-and-proxy.md
 * for why the token isn't just passed as a query param instead). Returns an
 * unsubscribe function that aborts the underlying request.
 */
export function streamJobEvents(token: string, jobId: string, handlers: SseHandlers): () => void {
  const controller = new AbortController();

  (async () => {
    try {
      const response = await fetch(jobEventsUrl(jobId), {
        headers: { Authorization: `Bearer ${token}` },
        signal: controller.signal,
      });
      if (!response.ok || !response.body) {
        throw new Error(`Event stream request failed with status ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      // eslint-disable-next-line no-constant-condition -- standard stream-reading loop, exits via `break` below
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        let match = buffer.match(FRAME_BOUNDARY);
        while (match?.index !== undefined) {
          const rawFrame = buffer.slice(0, match.index);
          buffer = buffer.slice(match.index + match[0].length);
          const message = parseFrame(rawFrame);
          if (message) handlers.onEvent(message);
          match = buffer.match(FRAME_BOUNDARY);
        }
      }
      handlers.onDone?.();
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      handlers.onError?.(error);
    }
  })();

  return () => controller.abort();
}

function parseFrame(rawFrame: string): JobEventMessage | null {
  let eventType = "message";
  const dataLines: string[] = [];

  for (const line of rawFrame.split(LINE_SPLIT)) {
    if (line.startsWith("event:")) {
      eventType = line.slice("event:".length).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trim());
    }
  }

  if (dataLines.length === 0) return null;

  try {
    const data = JSON.parse(dataLines.join("\n"));
    return { event: eventType, data } as JobEventMessage;
  } catch {
    return null;
  }
}
