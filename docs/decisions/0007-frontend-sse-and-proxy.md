# ADR 0007: Frontend SSE-over-fetch, split state, and same-origin proxy

## Status
Accepted

## Context
The web UI (`frontend/`) needs to show a research job's live progress (the
"watching it think" effect: current phase, tool calls as they happen) and
then its final report. The backend already exposes this via
`GET /research-jobs/{id}/events` (Server-Sent Events) and
`GET /research-jobs/{id}` (point-in-time status). Three problems needed a
deliberate answer rather than the obvious default:

1. The SSE endpoint is authenticated with an `X-API-Key` header, but
   browsers' native `EventSource` API cannot set custom request headers.
2. A live stream can drop (network blip, tab backgrounding) without the
   underlying job failing -- the UI must not get stuck if that happens.
3. The API and the built frontend need to end up served from the same
   origin in a real deployment, without hand-waving CORS as "good enough."

## Decisions

**SSE over `fetch`, not `EventSource`.** `frontend/src/api/sse.ts`
implements a small manual reader: `fetch` with an `X-API-Key` header,
`response.body.getReader()`, and a `TextDecoder` that accumulates chunks
and splits them into SSE frames (`event:`/`data:` lines, blank-line
delimited). The usual workaround -- pass the API key as a `?api_key=`
query parameter, since `EventSource` can't set headers -- was rejected: URL
query strings land in server access logs and browser history, which is a
real credential-leakage path even for a demo project. This costs about 60
lines of code and avoids that entirely.

**Two sources of truth, not one.** `frontend/src/hooks/useJobs.ts`'s
`useJob` polls `GET /research-jobs/{id}` via React Query
(`refetchInterval` while the job is non-terminal) -- this is what the UI
trusts for status and the final result. `frontend/src/hooks/useJobEvents.ts`
subscribes to the SSE stream purely to append lines to a live-scrolling
log (`ProgressPanel`). If the SSE connection drops, the polling loop still
carries the job to its correct final state; only the live log stops
updating mid-job. Making the "nice to have" data path (SSE) fully optional
relative to the "must be correct" data path (polling) was worth the small
duplication of hitting the API twice.

**nginx reverse proxy in the real deployment; CORS only for local dev.**
`frontend/nginx.conf` serves the built static app and proxies `/api/*`,
`/healthz`, and `/readyz` to the `api` service -- so in
`docker compose up`, the browser only ever talks to one origin
(`localhost:3000`), and no CORS configuration is in the request path at
all. `CORSMiddleware` was still added to the FastAPI app
(`app/main.py`) purely so `vite dev` (port 5173) can call the API (port
8000) directly during local frontend development, where there's no proxy
in front yet.

One consequence worth calling out: the SSE proxy needs
`proxy_buffering off` in nginx. nginx buffers upstream responses by
default, which would hold every event until the buffer filled instead of
forwarding it as the backend emits it -- silently turning a live stream
into a delayed batch. This was caught by testing the stream through the
actual proxy (`curl -N` against `localhost:3000`, not just against the API
container directly) rather than assuming the default proxy config was
fine for a streaming response.

## Consequences

- No backend auth changes were needed to support the frontend at all.
- The report/status view is correct even on a flaky connection; only the
  live trace log (a UX nicety) is affected.
- Local frontend dev (`vite dev`) and the Docker Compose deployment
  exercise two different network paths (direct + CORS vs. proxied +
  same-origin) -- both are real configurations that need to keep working,
  not one "temporary" dev setup.
