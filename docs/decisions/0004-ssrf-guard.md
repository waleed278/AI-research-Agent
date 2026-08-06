# ADR 0004: SSRF guard on the `fetch_url` tool

## Status
Accepted

## Context
The agent chooses which URLs to fetch itself, based on search results it
also chose to request. That is, by design, an untrusted input path: a
compromised or adversarial search result (or a compromised search
provider) could return a URL like `http://169.254.169.254/latest/meta-data/`
(the cloud metadata endpoint on AWS/GCP/Azure) or an internal service
address, and an agent with no awareness of this would fetch it exactly like
any other page.

## Decision
`app/tools/ssrf_guard.py::validate_public_url` runs before every fetch
(`app/tools/fetch_url.py`) and rejects:
- Any scheme other than `http`/`https`.
- Any hostname that resolves (via `socket.getaddrinfo`, not string
  matching) to a loopback, link-local, private (RFC1918), reserved, or
  multicast address.

Resolution happens *before* the guard's checks so that a public-looking
hostname whose DNS record points at an internal address is still caught --
rejecting by hostname string alone would miss that. The same check is
re-applied to every redirect hop: `fetch_and_extract` follows redirects
manually (capped at 5) rather than using `httpx`'s automatic redirect
following, specifically because a URL can pass validation and then 302 to
something that wouldn't.

## Consequences
- One extra DNS resolution per fetch (negligible latency cost) buys
  protection against an entire class of SSRF findings that would otherwise
  need to be caught in a security review after the fact.
- The guard is a single, independently unit-tested unit
  (`tests/unit/test_ssrf_guard.py`) -- it can be reused by any future tool
  that fetches an agent-chosen URL, not just this one.
- This does not defend against a malicious *public* page's content (e.g.
  prompt injection embedded in fetched text) -- that is a separate concern
  from SSRF and is intentionally out of scope for this ADR.
