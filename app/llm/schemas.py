from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ToolCallRequest(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any]


class ChatResult(BaseModel):
    """Result of a free-form (possibly tool-calling) chat completion."""

    content: str | None
    tool_calls: list[ToolCallRequest] = []
    usage: LLMUsage
    cost_usd: float
    finish_reason: str


class StructuredResult(BaseModel, Generic[T]):
    """Result of a schema-constrained call -- `data` is a validated instance
    of whatever Pydantic model the caller asked for."""

    data: T
    usage: LLMUsage
    cost_usd: float
    repaired: bool = False
