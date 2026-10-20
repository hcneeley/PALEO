"""Runtime settings for UPAE."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    adapter_timeout_sec: float = 3.5
    cache_ttl_sec: int = 86_400  # 24h
    host: str = "0.0.0.0"
    port: int = 8080
    default_radius_km: float = 10.0
    occurrence_limit: int = 50


settings = Settings()
