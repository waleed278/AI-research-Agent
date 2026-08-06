from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central runtime configuration. Values are read from the environment /
    .env file so the same image can be promoted across environments without
    a rebuild."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    # LLM provider
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_judge_model: str = "gpt-4o"
    openai_request_timeout_seconds: float = 60.0

    # Search provider
    search_provider: Literal["tavily", "mock"] = "mock"
    tavily_api_key: str = ""

    # Datastores
    database_url: str = "postgresql+asyncpg://agent:agent@localhost:5432/research_agent"
    redis_url: str = "redis://localhost:6379/0"

    # Agent run limits -- the guardrails against a runaway/expensive job
    agent_max_tool_steps: int = 12
    agent_max_revision_loops: int = 1
    agent_max_tokens_per_job: int = 200_000
    agent_job_timeout_seconds: int = 300

    # API
    api_key_rate_limit_per_minute: int = 10
    dev_seed_api_key: str = "dev-local-key"

    # CORS: only needed when a browser frontend calls the API directly from
    # a different origin (local `vite dev`). The Docker Compose deployment's
    # frontend container reverse-proxies /api instead (see frontend/nginx.conf),
    # so the browser only ever sees one origin there and CORS doesn't apply.
    cors_allowed_origins: list[str] = ["http://localhost:5173"]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    """Settings are cached for the process lifetime -- cheap dependency to
    inject, and avoids re-parsing the environment on every request."""
    return Settings()
