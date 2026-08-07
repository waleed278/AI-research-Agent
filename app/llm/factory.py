from app.core.config import Settings, get_settings
from app.db.models import LlmProvider
from app.llm.base import LLMProvider
from app.llm.providers.anthropic_provider import AnthropicProvider
from app.llm.providers.gemini_provider import GeminiProvider
from app.llm.providers.openai_provider import OpenAIProvider

_ADAPTERS: dict[LlmProvider, type] = {
    LlmProvider.OPENAI: OpenAIProvider,
    LlmProvider.GEMINI: GeminiProvider,
    LlmProvider.ANTHROPIC: AnthropicProvider,
}


def build_provider(provider: LlmProvider, api_key: str, settings: Settings | None = None) -> LLMProvider:
    """Builds a fresh provider client for one decrypted, user-supplied API
    key. Always built fresh per call -- never cached/shared across jobs,
    since different jobs can belong to different users with different keys
    for the same provider (see app/workers/worker.py, which calls this once
    per job after decrypting that job's owner's credential)."""
    settings = settings or get_settings()
    adapter_cls = _ADAPTERS.get(provider)
    if adapter_cls is None:
        raise ValueError(f"Unsupported provider: {provider}")
    return adapter_cls(api_key=api_key, timeout_seconds=settings.llm_request_timeout_seconds)
