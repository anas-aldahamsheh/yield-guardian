"""Configuration. Every setting comes from an environment variable (documented in .env.example)."""

from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", frozen=True)

    app_name: str = Field("Yield Guardian", description="Product name, held in one place (D-007).")
    environment: Literal["development", "test", "production"] = "development"
    public_url: str = "http://localhost:3000"
    git_commit: str | None = None
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = True

    database_url: SecretStr | None = Field(
        None, description="postgresql+asyncpg://user:password@host:5432/yield_guardian"
    )
    migrate_on_start: bool = Field(True, description="Apply database migrations at startup.")
    artifacts_dir: Path = Path("artifacts")
    secom_data_dir: Path = Path("data/secom")

    token_factory_api_key: SecretStr | None = None
    token_factory_base_url: str = "https://developer.amd.com.cn/radeon/api/v1"  # noqa: S105

    session_secret: SecretStr | None = Field(None, description="At least 32 random bytes, base64.")
    session_ttl_minutes: int = Field(120, ge=5, le=24 * 60)
    admin_username: str | None = None
    admin_password_hash: SecretStr | None = Field(
        None, description="scrypt hash from scripts/hash_password.py"
    )
    cors_origins: list[str] = Field(default_factory=list)

    replay_epoch: datetime = datetime(2026, 10, 12, tzinfo=UTC)
    replay_seconds_per_unit: float = Field(6.0, gt=0)
    final_test_lag_units: int = Field(25, ge=0)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
