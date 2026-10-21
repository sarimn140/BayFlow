"""Application settings (spec 01 "Configuration", spec 04, spec 07, glossary §12).

Sources, highest priority first: process environment, the repo-root `.env` (resolved from this
file's location, never from the working directory), then the defaults below, which make local
development work out of the box. Blank values count as "not set" (`env_ignore_empty`), so a blank
optional variable means "feature disabled".
"""

import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

# apps/api/app/core/config.py -> parents[2] = apps/api (or /app inside the Docker image).
API_DIR = Path(__file__).resolve().parents[2]
# <repo>/apps/api -> <repo>. Inside the image this resolves to "/", where no .env exists (skipped).
REPO_ROOT = API_DIR.parent.parent
ENV_FILE = REPO_ROOT / ".env"

DEFAULT_DATABASE_URL = "postgresql://bayflow:bayflow@localhost:5434/bayflow"

# Used only when APP_ENV=development and JWT_SECRET is missing. Letters and hyphens only, so the
# repository's secret scanner does not flag it (spec 07); production refuses it (markers below).
DEV_JWT_SECRET = "dev-only-insecure-jwt-secret-never-use-in-production"  # noqa: S105
# Production refuses any JWT_SECRET containing one of these markers (D85). They cover every
# placeholder shipped in the repository, e.g. `.env.example`'s
# `local-dev-secret-replace-me-with-random-chars`, CI's `ci-placeholder-…` and DEV_JWT_SECRET.
PLACEHOLDER_SECRET_MARKERS = ("change-me", "replace-me", "dev-only", "placeholder")
MIN_SECRET_BYTES = 32  # RFC 7518 §3.2: HS256 keys need at least 256 bits (D8)

# --- Durations (`JWT_EXPIRES_IN`, spec 04) ----------------------------------------------------

_DURATION_RE = re.compile(r"(\d+)([smhd]?)")
_UNIT_SECONDS = {"": 1, "s": 1, "m": 60, "h": 3_600, "d": 86_400}
MIN_TOKEN_LIFETIME_S = 300
MAX_TOKEN_LIFETIME_S = 30 * 86_400


def parse_duration(value: str) -> int:
    """Parse `<integer><s|m|h|d>` (or a bare integer = seconds) into seconds.

    Spec 04: the lifetime must lie between 5 minutes and 30 days; anything else (`""`, `0`,
    `7days`, `1w`, `-1d`) is rejected so the API refuses to start with a clear message.
    """
    match = _DURATION_RE.fullmatch(value)
    if match is None:
        msg = f"invalid duration {value!r}: use <number><s|m|h|d>, e.g. '7d', '12h' or '3600'"
        raise ValueError(msg)
    seconds = int(match.group(1)) * _UNIT_SECONDS[match.group(2)]
    if not MIN_TOKEN_LIFETIME_S <= seconds <= MAX_TOKEN_LIFETIME_S:
        msg = (
            f"duration {value!r} is {seconds} s; it must be between "
            f"{MIN_TOKEN_LIFETIME_S} s and {MAX_TOKEN_LIFETIME_S} s (30 days)"
        )
        raise ValueError(msg)
    return seconds


# --- DATABASE_URL normalisation (glossary §12) --------------------------------------------------

_ASYNC_DRIVER = "postgresql+asyncpg"
_ACCEPTED_DRIVERS = frozenset({"postgres", "postgresql", _ASYNC_DRIVER})
# libpq-only query parameters that asyncpg's connect() does not accept.
_DROPPED_LIBPQ_PARAMS = ("channel_binding",)


def normalize_database_url(raw: str) -> str:
    """Convert `postgres://` / `postgresql://` URLs to `postgresql+asyncpg://`.

    A libpq `sslmode` query parameter is translated to asyncpg's `ssl` (same value names), because
    SQLAlchemy passes URL query parameters straight to `asyncpg.connect()`.
    """
    try:
        url = make_url(raw.strip())
    except ArgumentError as exc:
        msg = "DATABASE_URL is not a valid database URL"
        raise ValueError(msg) from exc
    if url.drivername not in _ACCEPTED_DRIVERS:
        msg = f"DATABASE_URL must be a PostgreSQL URL (postgresql://...), not {url.drivername!r}"
        raise ValueError(msg)
    url = url.set(drivername=_ASYNC_DRIVER)
    query = dict(url.query)
    if "sslmode" in query:
        query.setdefault("ssl", query.pop("sslmode"))
    for name in _DROPPED_LIBPQ_PARAMS:
        query.pop(name, None)
    url = url.set(query=query)
    return url.render_as_string(hide_password=False)


class Settings(BaseSettings):
    """Every variable the API reads (glossary §12). Field names are the snake_case env names."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        hide_input_in_errors=True,  # a start-up error must never print a secret value
    )

    # --- App ---
    app_env: Literal["development", "production"] = "development"
    port: int = Field(default=4000, ge=1, le=65_535)
    client_url: str = "http://localhost:3000"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    seed_on_deploy: bool = False

    # --- Database ---
    database_url: SecretStr = SecretStr(DEFAULT_DATABASE_URL)

    # --- Auth ---
    jwt_secret: SecretStr = SecretStr("")
    jwt_expires_in: str = "7d"
    cookie_secure: bool = False

    # --- E-mail (optional, D26) ---
    email_provider: Literal["none", "smtp", "http"] = "none"
    email_api_key: SecretStr | None = None
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65_535)
    smtp_user: str | None = None
    smtp_pass: SecretStr | None = None
    smtp_from: str = "no-reply@bayflow.test"

    # --- Bonus: calling and AI Front Desk (spec 05 §10; blank = disabled) ---
    call_provider_url: str | None = None
    call_provider_api_key: SecretStr | None = None
    call_provider_api_secret: SecretStr | None = None
    llm_api_key: SecretStr | None = None
    agent_service_token: SecretStr | None = None
    ai_ring_timeout_seconds: int = Field(default=20, ge=1, le=300)
    ai_daily_call_cap: int = Field(default=100, ge=0)
    call_monthly_minutes_cap: int = Field(default=4_000, ge=0)

    # --- Bonus: text AI in the API (D103, modules/ai.md; no key = off) ---
    ai_text_provider: Literal["gemini", "fake"] = "gemini"
    ai_text_model: str = "gemini-2.5-flash"
    ai_text_api_key: SecretStr | None = None  # blank -> LLM_API_KEY
    ai_features: str = ""  # comma-separated AiFeature names, or "*"; blank = none
    ai_shop_daily_cap: int = Field(default=200, ge=0)
    ai_shop_monthly_cap: int = Field(default=3_000, ge=0)
    ai_timeout_seconds: int = Field(default=30, ge=1, le=300)

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_database_url(cls, value: object) -> object:
        if isinstance(value, SecretStr):
            value = value.get_secret_value()
        if isinstance(value, str):
            return normalize_database_url(value)
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_log_level(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("client_url")
    @classmethod
    def _strip_client_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value.startswith(("http://", "https://")):
            msg = "CLIENT_URL must be an http(s) origin such as http://localhost:3000"
            raise ValueError(msg)
        return value

    @field_validator("jwt_expires_in")
    @classmethod
    def _check_jwt_expires_in(cls, value: str) -> str:
        value = value.strip()
        parse_duration(value)
        return value

    @model_validator(mode="after")
    def _check_secrets(self) -> "Settings":
        secret = self.jwt_secret.get_secret_value()
        if self.is_production:
            problems: list[str] = []
            if not secret:
                problems.append("JWT_SECRET is not set")
            elif len(secret.encode("utf-8")) < MIN_SECRET_BYTES:
                problems.append(f"JWT_SECRET must be at least {MIN_SECRET_BYTES} bytes")
            elif any(marker in secret.lower() for marker in PLACEHOLDER_SECRET_MARKERS):
                problems.append("JWT_SECRET is still a placeholder value")
            if not self.cookie_secure:
                problems.append("COOKIE_SECURE must be true")
            if problems:
                msg = (
                    "refusing to start with APP_ENV=production: "
                    + "; ".join(problems)
                    + ". Generate a secret with: "
                    + 'python -c "import secrets; print(secrets.token_urlsafe(48))"'
                )
                raise ValueError(msg)
        elif not secret:
            self.jwt_secret = SecretStr(DEV_JWT_SECRET)
        return self

    @model_validator(mode="after")
    def _check_email_settings(self) -> "Settings":
        """D26 / spec 01: the chosen e-mail provider must be fully configured (every APP_ENV)."""
        missing: list[str] = []
        if self.email_provider == "smtp" and not self.smtp_host:
            missing.append("SMTP_HOST")
        if self.email_provider == "http" and self.email_api_key is None:
            missing.append("EMAIL_API_KEY")
        if self.email_provider != "none" and not self.smtp_from.strip():
            missing.append("SMTP_FROM")
        if missing:
            msg = f"EMAIL_PROVIDER={self.email_provider} requires {', '.join(missing)}"
            raise ValueError(msg)
        return self

    # --- Derived values ---

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def jwt_lifetime_seconds(self) -> int:
        """`JWT_EXPIRES_IN` in seconds; feeds both the token `exp` and the cookie `Max-Age`."""
        return parse_duration(self.jwt_expires_in)

    @property
    def uses_dev_jwt_secret(self) -> bool:
        return self.jwt_secret.get_secret_value() == DEV_JWT_SECRET

    @property
    def email_enabled(self) -> bool:
        return self.email_provider != "none"

    @property
    def calling_enabled(self) -> bool:
        """Spec 05 §10: all three `CALL_PROVIDER_*` variables are set."""
        return bool(
            self.call_provider_url and self.call_provider_api_key and self.call_provider_api_secret
        )

    @property
    def ai_enabled(self) -> bool:
        """Spec 05 §10: calling enabled and `LLM_API_KEY` and `AGENT_SERVICE_TOKEN` set."""
        return bool(self.calling_enabled and self.llm_api_key and self.agent_service_token)

    def text_ai_key(self) -> SecretStr | None:
        """D103: the text provider's key; `AI_TEXT_API_KEY`, else `LLM_API_KEY`."""
        return self.ai_text_api_key or self.llm_api_key

    @property
    def text_ai_configured(self) -> bool:
        """D103: a provider can be built. The fake provider never counts in production."""
        if self.ai_text_provider == "fake":
            return not self.is_production
        return self.text_ai_key() is not None

    @property
    def enabled_ai_features(self) -> frozenset[str]:
        """`AI_FEATURES` as upper-case names (`*` kept as is); unknown names are ignored later."""
        return frozenset(
            name.strip().upper() for name in self.ai_features.split(",") if name.strip()
        )

    def startup_warnings(self) -> list[str]:
        """Non-fatal configuration problems, logged once at start-up (development only)."""
        if self.is_production:
            return []
        warnings: list[str] = []
        secret = self.jwt_secret.get_secret_value()
        if self.uses_dev_jwt_secret:
            warnings.append(
                "JWT_SECRET is not set: using a development-only secret. "
                "Never deploy like this (APP_ENV=production refuses to start)."
            )
        elif len(secret.encode("utf-8")) < MIN_SECRET_BYTES:
            warnings.append(
                f"JWT_SECRET is shorter than {MIN_SECRET_BYTES} bytes; "
                "production refuses to start with it."
            )
        return warnings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The process-wide settings, read once (call `get_settings.cache_clear()` in tests)."""
    return Settings()
