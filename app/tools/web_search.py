from abc import ABC, abstractmethod
from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings
from app.tools.base import Tool, ToolResult

TAVILY_SEARCH_URL = "https://api.tavily.com/search"


class SearchHit(BaseModel):
    title: str
    url: str
    snippet: str


class SearchProvider(ABC):
    @abstractmethod
    async def search(self, query: str, max_results: int) -> list[SearchHit]: ...


class TavilySearchProvider(SearchProvider):
    """Tavily's search API is purpose-built for LLM agents (it returns
    clean snippets instead of raw SERPs), so it needs no additional
    scraping/cleaning step before the model can reason over results."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def search(self, query: str, max_results: int) -> list[SearchHit]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                TAVILY_SEARCH_URL,
                json={
                    "api_key": self._api_key,
                    "query": query,
                    "max_results": max_results,
                    "search_depth": "basic",
                },
            )
            response.raise_for_status()
            payload = response.json()
        return [
            SearchHit(title=r.get("title", ""), url=r["url"], snippet=r.get("content", ""))
            for r in payload.get("results", [])
        ]


class MockSearchProvider(SearchProvider):
    """Deterministic, offline search provider. Used in tests, CI, and any
    `--mock` eval/demo run so the agent pipeline can be exercised end-to-end
    without a Tavily API key or network access -- and without spending
    money on every push."""

    async def search(self, query: str, max_results: int) -> list[SearchHit]:
        return [
            SearchHit(
                title=f"Mock result {i + 1} for: {query}",
                url=f"https://example.com/mock-{abs(hash(query)) % 10_000}/{i + 1}",
                snippet=(
                    f"This is a deterministic mock snippet discussing '{query}'. "
                    f"Point {i + 1}: relevant background and a plausible supporting fact."
                ),
            )
            for i in range(max_results)
        ]


def get_search_provider(settings: Settings | None = None) -> SearchProvider:
    settings = settings or get_settings()
    if settings.search_provider == "tavily" and settings.tavily_api_key:
        return TavilySearchProvider(settings.tavily_api_key)
    return MockSearchProvider()


class WebSearchArgs(BaseModel):
    query: str = Field(description="The search query to run against the web.")
    max_results: int = Field(default=5, ge=1, le=10, description="Number of results to return.")


class WebSearchTool(Tool):
    name = "web_search"
    description = "Search the public web and return a list of titled, linked snippets."
    args_model = WebSearchArgs

    def __init__(self, provider: SearchProvider | None = None) -> None:
        self._provider = provider or get_search_provider()

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        args = WebSearchArgs.model_validate(arguments)
        hits = await self._provider.search(args.query, args.max_results)
        if not hits:
            return ToolResult(ok=True, content="No results found.")
        lines = [f"[{i + 1}] {h.title}\n{h.url}\n{h.snippet}" for i, h in enumerate(hits)]
        return ToolResult(
            ok=True,
            content="\n\n".join(lines),
            citation={"hits": [h.model_dump() for h in hits]},
        )
