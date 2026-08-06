from typing import Any

import httpx
import trafilatura
from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.tools.base import Tool, ToolResult
from app.tools.ssrf_guard import UnsafeUrlError, validate_public_url

logger = get_logger(__name__)

_MAX_REDIRECTS = 5
_MAX_CONTENT_CHARS = 6000


async def fetch_and_extract(url: str, max_chars: int = _MAX_CONTENT_CHARS) -> tuple[str, str]:
    """Fetches `url` and returns (final_url, extracted_main_text).

    Redirects are followed manually (one hop at a time, capped at
    `_MAX_REDIRECTS`) with the SSRF guard re-applied to *every* hop -- a
    public-looking URL can still 302 to an internal address, and
    `httpx`'s built-in `follow_redirects` would happily do that for you.
    """
    current_url = validate_public_url(url)

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
        for _ in range(_MAX_REDIRECTS):
            response = await client.get(current_url, headers={"User-Agent": "ResearchAgent/1.0"})
            if response.is_redirect:
                next_url = str(response.next_request.url) if response.next_request else None
                if not next_url:
                    break
                current_url = validate_public_url(next_url)
                continue
            response.raise_for_status()
            html = response.text
            break
        else:
            raise UnsafeUrlError(f"Too many redirects starting from {url}")

    extracted = trafilatura.extract(html, include_comments=False, include_tables=False) or ""
    return current_url, extracted[:max_chars]


class FetchUrlArgs(BaseModel):
    url: str = Field(
        description="A public http(s) URL to fetch and read, e.g. from search results."
    )


class FetchUrlTool(Tool):
    name = "fetch_url"
    description = (
        "Fetch a public web page and return its main readable text content "
        "(scripts, nav, and boilerplate stripped). Use this to read a page "
        "found via web_search before citing it."
    )
    args_model = FetchUrlArgs

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        args = FetchUrlArgs.model_validate(arguments)
        try:
            final_url, text = await fetch_and_extract(args.url)
        except UnsafeUrlError as exc:
            logger.warning("fetch_url_blocked", url=args.url, reason=str(exc))
            return ToolResult(ok=False, content=f"Refused to fetch this URL: {exc}")
        except httpx.HTTPError as exc:
            return ToolResult(ok=False, content=f"Failed to fetch {args.url}: {exc}")

        if not text.strip():
            return ToolResult(ok=True, content=f"No extractable text content at {final_url}.")
        return ToolResult(
            ok=True,
            content=f"Content from {final_url}:\n\n{text}",
            citation={"url": final_url},
        )
