"""Settings: DATABASE_URL conversion, production guards, durations, sources (spec 01, 04, 07)."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import (
    API_DIR,
    DEFAULT_DATABASE_URL,
    DEV_JWT_SECRET,
    ENV_FILE,
    REPO_ROOT,
    Settings,
    normalize_database_url,
    parse_duration,
)

STRONG_SECRET = "a-strong-random-production-secret-value-of-48-chars"

# Every variable these tests depend on; cleared so a developer's shell or .env cannot leak in.
_ENV_VARS = (
    "APP_ENV",
    "PORT",
    "CLIENT_URL",
    "DATABASE_URL",
    "JWT_SECRET",
    "JWT_EXPIRES_IN",
    "COOKIE_SECURE",
    "LOG_LEVEL",
    "SEED_ON_DEPLOY",
    "EMAIL_PROVIDER",
    "EMAIL_API_KEY",
    "SMTP_HOST",
    "SMTP_FROM",
)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name in _ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def build(**values: object) -> Settings:
    return Settings(_env_file=None, **values)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("postgres://u:p@db:5432/app", "postgresql+asyncpg://u:p@db:5432/app"),
        ("postgresql://u:p@db:5432/app", "postgresql+asyncpg://u:p@db:5432/app"),
        ("postgresql+asyncpg://u:p@db:5432/app", "postgresql+asyncpg://u:p@db:5432/app"),
        ("  postgresql://u:p@localhost/app  ", "postgresql+asyncpg://u:p@localhost/app"),
        (
            "postgresql://u:p@db/app?sslmode=require",
            "postgresql+asyncpg://u:p@db/app?ssl=require",
        ),
        (
            "postgresql://u:p@db/app?sslmode=require&channel_binding=require",
            "postgresql+asyncpg://u:p@db/app?ssl=require",
        ),
    ],
)
def test_database_url_is_converted_to_asyncpg(raw: str, expected: str) -> None:
    assert normalize_database_url(raw) == expected


@pytest.mark.parametrize("raw", ["mysql://u:p@db/app", "sqlite:///app.db", "not a url"])
def test_non_postgres_database_url_is_rejected(raw: str) -> None:
    with pytest.raises(ValueError, match="DATABASE_URL"):
        normalize_database_url(raw)


def test_settings_convert_database_url_and_keep_it_secret(clean_env: pytest.MonkeyPatch) -> None:
    settings = build(database_url="postgres://bayflow:s3cret@db:5432/bayflow")
    assert settings.database_url.get_secret_value() == (
        "postgresql+asyncpg://bayflow:s3cret@db:5432/bayflow"
    )
    assert "s3cret" not in repr(settings)


def test_defaults_make_local_development_work(clean_env: pytest.MonkeyPatch) -> None:
    settings = build()
    assert settings.app_env == "development"
    assert settings.port == 4000
    assert settings.client_url == "http://localhost:3000"
    assert settings.database_url.get_secret_value() == normalize_database_url(DEFAULT_DATABASE_URL)
    assert settings.database_url.get_secret_value().endswith("@localhost:5434/bayflow")
    assert settings.jwt_expires_in == "7d"
    assert settings.jwt_lifetime_seconds == 604_800
    assert settings.cookie_secure is False
    assert settings.email_provider == "none"
    assert settings.log_level == "INFO"
    assert settings.seed_on_deploy is False


def test_root_env_file_is_resolved_from_the_file_location() -> None:
    assert Path(__file__).resolve().parents[3] == API_DIR
    assert ENV_FILE == REPO_ROOT / ".env"
    assert (REPO_ROOT / "apps" / "api" / "pyproject.toml").is_file()


def test_process_environment_wins_over_the_env_file(
    clean_env: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("PORT=4100\nLOG_LEVEL=debug\nCLIENT_URL=http://from-file:3000/\n")
    clean_env.setenv("PORT", "4200")
    settings = Settings(_env_file=env_file)
    assert settings.port == 4200  # environment
    assert settings.log_level == "DEBUG"  # .env file, normalised
    assert settings.client_url == "http://from-file:3000"  # trailing slash removed


def test_blank_values_fall_back_to_defaults(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("SMTP_HOST", "")
    clean_env.setenv("JWT_EXPIRES_IN", "")
    settings = build()
    assert settings.smtp_host is None
    assert settings.jwt_expires_in == "7d"


# --- JWT secret and production guards (spec 04 "Secrets and rotation", SEC-37) -----------------


def test_development_without_secret_uses_a_dev_only_secret_and_warns(
    clean_env: pytest.MonkeyPatch,
) -> None:
    settings = build()
    assert settings.jwt_secret.get_secret_value() == DEV_JWT_SECRET
    assert settings.uses_dev_jwt_secret
    assert any("development-only secret" in warning for warning in settings.startup_warnings())


def test_development_with_a_short_secret_only_warns(clean_env: pytest.MonkeyPatch) -> None:
    settings = build(jwt_secret="short-secret")
    assert any("shorter than 32 bytes" in warning for warning in settings.startup_warnings())


def test_production_accepts_a_strong_configuration(clean_env: pytest.MonkeyPatch) -> None:
    settings = build(app_env="production", jwt_secret=STRONG_SECRET, cookie_secure=True)
    assert settings.is_production
    assert settings.startup_warnings() == []


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"jwt_secret": "change-me", "cookie_secure": True}, "at least 32 bytes"),
        ({"jwt_secret": "", "cookie_secure": True}, "JWT_SECRET is not set"),
        ({"cookie_secure": True}, "JWT_SECRET is not set"),
        (
            {"jwt_secret": "change-me-to-a-long-random-string", "cookie_secure": True},
            "placeholder",
        ),
        (
            {"jwt_secret": "ci-placeholder-not-a-real-secret-value", "cookie_secure": True},
            "placeholder",
        ),
        ({"jwt_secret": DEV_JWT_SECRET, "cookie_secure": True}, "placeholder"),
        # The `.env.example` placeholder (45 chars, so it passes the length rule) — D85.
        (
            {"jwt_secret": "local-dev-secret-replace-me-with-random-chars", "cookie_secure": True},
            "placeholder",
        ),
        (
            {"jwt_secret": "my-SECRET-placeholder-value-for-prod-xx", "cookie_secure": True},
            "placeholder",
        ),
        ({"jwt_secret": STRONG_SECRET, "cookie_secure": False}, "COOKIE_SECURE must be true"),
    ],
)
def test_production_refuses_weak_or_placeholder_settings(
    clean_env: pytest.MonkeyPatch, overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        build(app_env="production", **overrides)


def test_production_guard_reads_the_environment(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("APP_ENV", "production")
    clean_env.setenv("JWT_SECRET", "change-me")
    with pytest.raises(ValidationError, match="refusing to start"):
        build()


# --- JWT_EXPIRES_IN (spec 04, SEC-24) -------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "seconds"),
    [
        ("7d", 604_800),
        ("12h", 43_200),
        ("90m", 5_400),
        ("3600", 3_600),
        ("300s", 300),
        ("30d", 2_592_000),
    ],
)
def test_parse_duration_accepts_the_documented_forms(value: str, seconds: int) -> None:
    assert parse_duration(value) == seconds


@pytest.mark.parametrize("value", ["", "0", "7days", "1w", "-1d", "45s", "31d", "1.5h", "d"])
def test_parse_duration_rejects_everything_else(value: str) -> None:
    with pytest.raises(ValueError, match="duration"):
        parse_duration(value)


def test_invalid_jwt_expires_in_refuses_to_start(clean_env: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError, match="duration"):
        build(jwt_expires_in="1w")


# --- E-mail provider (D26) ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "missing"),
    [
        ({"email_provider": "smtp"}, "SMTP_HOST"),
        ({"email_provider": "http"}, "EMAIL_API_KEY"),
        ({"email_provider": "smtp", "smtp_host": "localhost", "smtp_from": " "}, "SMTP_FROM"),
    ],
)
def test_email_provider_must_be_fully_configured(
    clean_env: pytest.MonkeyPatch, overrides: dict[str, object], missing: str
) -> None:
    with pytest.raises(ValidationError, match=missing):
        build(**overrides)


def test_feature_switches_follow_the_bonus_variables(clean_env: pytest.MonkeyPatch) -> None:
    assert not build().calling_enabled
    settings = build(
        call_provider_url="wss://example.livekit.cloud",
        call_provider_api_key="key",
        call_provider_api_secret="secret",
        llm_api_key="llm",
        agent_service_token="token",
    )
    assert settings.calling_enabled
    assert settings.ai_enabled


def test_startup_errors_never_echo_secret_values(clean_env: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError) as caught:
        build(
            app_env="production", jwt_secret="change-me-but-SUPER-SECRET-1234", cookie_secure=True
        )
    assert "SUPER-SECRET" not in str(caught.value)
