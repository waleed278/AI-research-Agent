from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Per-provider model allow-list for BYOK job creation (app/api/v1/routes/research.py
# validates a job's requested model against this). Keyed by plain provider strings
# (matching app.db.models.LlmProvider.value) rather than the enum itself, so this
# stays a leaf module -- core/ must not import from db/ (see docs/architecture.md's
# layering: api -> services -> agent -> llm/tools -> db). Edit freely as providers
# ship new models; this is a config default, not a hardcoded capability.
SUPPORTED_MODELS: dict[str, list[str]] = {
    "openai": ["gpt-4o", "gpt-4o-mini"],
    "gemini": ["gemini-2.0-flash", "gemini-1.5-pro"],
    "anthropic": ["claude-sonnet-5", "claude-haiku-4-5-20251001"],
}

DEFAULT_MODEL_BY_PROVIDER: dict[str, str] = {
    "openai": "gpt-4o-mini",
    "gemini": "gemini-2.0-flash",
    "anthropic": "claude-haiku-4-5-20251001",
}


class Settings(BaseSettings):
    """Central runtime configuration. Values are read from the environment /
    .env file so the same image can be promoted across environments without
    a rebuild."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    # Server-side OpenAI key: used ONLY by the offline eval harness and its
    # LLM-judge (evals/run_evals.py, evals/judge.py) -- maintainer/CI tooling,
    # not part of the multi-tenant product surface. End-user research jobs
    # always run on that user's own BYOK credential (app.db.models.LlmCredential),
    # decrypted per-job in the worker; see docs/decisions/0009-multi-provider-byok.md.
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_judge_model: str = "gpt-4o"

    # Shared across all three provider adapters (app/llm/providers/), not
    # OpenAI-specific -- named generically since app/llm/factory.py uses it
    # regardless of which provider a job's user picked.
    llm_request_timeout_seconds: float = 60.0

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
    login_rate_limit_per_minute: int = 10
    dev_seed_api_key: str = "dev-local-key"

    # Auth: JWTs for the web app, bcrypt for password storage. The default
    # below is fine for local dev but MUST be overridden with a long random
    # value (e.g. `openssl rand -hex 32`) anywhere real users sign up.
    jwt_secret_key: str = "insecure-dev-secret-change-me-in-any-shared-environment"
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 60 * 24 * 7  # 7 days

    # Fernet key encrypting `LlmCredential.encrypted_key` at rest. Generate a
    # real one with `python -c "from cryptography.fernet import Fernet;
    # print(Fernet.generate_key().decode())"` -- the default below only
    # works for local dev (it's committed, so it is definitionally not a
    # secret) and decrypting real user keys with it in any shared
    # environment would be a security bug, not a config oversight.
    secret_encryption_key: str = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

    # File uploads (see app/services/uploads_service.py). The default is a
    # relative path so bare `uv run` (local dev, tests) writes into the repo
    # instead of trying to create /data at the filesystem root; Docker
    # Compose overrides this to the absolute /data/uploads mount point (see
    # infra/docker-compose.yml) shared between the api and worker containers.
    upload_dir: str = "./.data/uploads"
    max_upload_bytes: int = 10 * 1024 * 1024  # 10 MB
    allowed_upload_extensions: list[str] = [".txt", ".md", ".csv", ".pdf"]
    max_extracted_chars_per_file: int = 15_000

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
