from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class ToolResult(BaseModel):
    """What a tool hands back to the research loop. `content` is the text
    fed to the LLM as the tool-call result; `citation` (when present) is
    structured enough that the synthesizer can turn it into a numbered
    source without re-parsing free text."""

    ok: bool
    content: str
    citation: dict[str, Any] | None = None


class Tool(ABC):
    """Every tool the agent can call implements this. `args_model` is a
    Pydantic model -- its JSON schema *is* the OpenAI function-calling
    schema, so the argument contract is defined once and can never drift
    between what we validate and what we advertise to the model."""

    name: str
    description: str
    args_model: type[BaseModel]

    def to_openai_schema(self) -> dict[str, Any]:
        schema = self.args_model.model_json_schema()
        schema["additionalProperties"] = False
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": schema,
            },
        }

    @abstractmethod
    async def execute(self, arguments: dict[str, Any]) -> ToolResult: ...

    async def __call__(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            args = self.args_model.model_validate(arguments)
        except Exception as exc:  # noqa: BLE001 - deliberately surfaced to the LLM, not raised
            return ToolResult(ok=False, content=f"Invalid arguments for {self.name}: {exc}")
        try:
            return await self.execute(args.model_dump())
        except Exception as exc:  # noqa: BLE001 - tool failures are recoverable agent turns
            return ToolResult(ok=False, content=f"{self.name} failed: {exc}")
