"""$/token pricing table used to attribute a real dollar cost to every LLM
call, across every provider a user might BYOK. Keeping this as an explicit
table (rather than trusting a downstream billing dashboard) is what lets
the orchestrator enforce a per-job cost cap and lets the eval report show
cost-per-query as a first-class metric. Keyed by exact model string across
all providers -- collisions are not expected since provider model names
are namespaced by convention (gpt-*, gemini-*, claude-*).

Prices are USD per 1M tokens. Update as providers change pricing.
"""

PRICING_PER_MILLION_TOKENS: dict[str, dict[str, float]] = {
    # OpenAI
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o-2024-08-06": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini-2024-07-18": {"input": 0.15, "output": 0.60},
    # Gemini
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
    # Anthropic
    "claude-sonnet-5": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00},
}

_DEFAULT_PRICE = {"input": 5.00, "output": 15.00}


def calculate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    price = PRICING_PER_MILLION_TOKENS.get(model, _DEFAULT_PRICE)
    return (prompt_tokens * price["input"] + completion_tokens * price["output"]) / 1_000_000
