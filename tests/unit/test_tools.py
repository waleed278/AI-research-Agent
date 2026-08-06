import pytest

from app.tools.fetch_url import FetchUrlTool
from app.tools.web_search import MockSearchProvider, WebSearchTool


@pytest.mark.asyncio
async def test_web_search_tool_returns_citable_hits() -> None:
    tool = WebSearchTool(provider=MockSearchProvider())
    result = await tool({"query": "large language model evals", "max_results": 3})

    assert result.ok
    assert result.citation is not None
    hits = result.citation["hits"]
    assert len(hits) == 3
    assert all("url" in h and "title" in h and "snippet" in h for h in hits)
    assert "large language model evals" in result.content


@pytest.mark.asyncio
async def test_web_search_tool_rejects_invalid_arguments() -> None:
    tool = WebSearchTool(provider=MockSearchProvider())
    # max_results=0 violates the ge=1 constraint on WebSearchArgs
    result = await tool({"query": "x", "max_results": 0})

    assert result.ok is False
    assert "Invalid arguments" in result.content


@pytest.mark.asyncio
async def test_fetch_url_tool_refuses_unsafe_url() -> None:
    tool = FetchUrlTool()
    result = await tool({"url": "http://169.254.169.254/latest/meta-data/"})

    assert result.ok is False
    assert "Refused to fetch" in result.content


def test_web_search_tool_openai_schema_matches_its_args_model() -> None:
    tool = WebSearchTool(provider=MockSearchProvider())
    schema = tool.to_openai_schema()

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "web_search"
    properties = schema["function"]["parameters"]["properties"]
    assert set(properties) == {"query", "max_results"}
