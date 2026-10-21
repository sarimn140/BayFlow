"""The agent's settings (spec 05 §10; glossary §12). Canonical names only: the LiveKit and OpenAI
SDK defaults (`LIVEKIT_*`, `OPENAI_API_KEY`) are never read; every value is passed explicitly.

Sources, highest first: the process environment, then the repo-root `.env` (local development).
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# apps/agent/src/bayflow_agent/config.py -> parents[4] = the repository root
ENV_FILE = Path(__file__).resolve().parents[4] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE, env_ignore_empty=True, extra="ignore", case_sensitive=False
    )

    call_provider_url: str | None = None
    call_provider_api_key: SecretStr | None = None
    call_provider_api_secret: SecretStr | None = None
    llm_api_key: SecretStr | None = None
    ai_provider: Literal["openai", "gemini"] = "openai"
    ai_realtime_model: str | None = None  # blank: the plugin's default model
    ai_summary_model: str | None = None  # blank: gpt-5-mini / gemini-2.5-flash
    agent_service_token: SecretStr | None = None
    api_internal_url: str = "http://localhost:4000"
    agent_port: int = 8081  # the worker's health server (Railway health check `/`)
    log_level: str = "INFO"

    @property
    def summary_model(self) -> str:
        if self.ai_summary_model:
            return self.ai_summary_model
        return "gemini-2.5-flash" if self.ai_provider == "gemini" else "gpt-5-mini"

    def missing(self) -> list[str]:
        """Required values that are blank (the worker refuses to start without them)."""
        required = {
            "CALL_PROVIDER_URL": self.call_provider_url,
            "CALL_PROVIDER_API_KEY": self.call_provider_api_key,
            "CALL_PROVIDER_API_SECRET": self.call_provider_api_secret,
            "LLM_API_KEY": self.llm_api_key,
            "AGENT_SERVICE_TOKEN": self.agent_service_token,
        }
        return [name for name, value in required.items() if not value]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
