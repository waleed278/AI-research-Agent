from typing import Any

from app.tools.base import Tool, ToolResult
from app.tools.fetch_url import FetchUrlTool
from app.tools.web_search import WebSearchTool, get_search_provider


class ToolRegistry:
    """Central place tools are registered and dispatched from. Adding a new
    tool means writing a `Tool` subclass and registering it here -- nothing
    else in the agent (the research loop, the prompts) needs to change,
    since the OpenAI function schema is derived from the tool itself."""

    def __init__(self, tools: list[Tool]) -> None:
        self._tools = {t.name: t for t in tools}

    def openai_schemas(self) -> list[dict[str, Any]]:
        return [t.to_openai_schema() for t in self._tools.values()]

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(ok=False, content=f"Unknown tool: {name}")
        return await tool(arguments)


def default_registry() -> ToolRegistry:
    return ToolRegistry([WebSearchTool(get_search_provider()), FetchUrlTool()])
