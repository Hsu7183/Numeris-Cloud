from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.paths import DATABASE_PATH, PROJECT_ROOT


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NUMERIS_", env_file=PROJECT_ROOT / ".env", extra="ignore"
    )

    app_name: str = "Numeris 彩球分析與選號系統"
    app_version: str = "1.2.0"
    host: str = "127.0.0.1"
    port: int = 8767
    timezone: str = "Asia/Taipei"
    database_url: str = f"sqlite:///{DATABASE_PATH.as_posix()}"
    request_timeout: int = 30
    max_retries: int = 3


@lru_cache
def get_settings() -> Settings:
    return Settings()
