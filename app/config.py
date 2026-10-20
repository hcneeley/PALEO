"""Runtime settings for UPAE."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Default hard timeout for most adapters (PBDB, Macrostrat, Crossref, …)
    adapter_timeout_sec: float = 3.5
    # Longer budgets for heavy / slow upstreams (env: ADAPTER_TIMEOUT_*_SEC)
    adapter_timeout_gbif_sec: float = 25.0
    adapter_timeout_mindat_sec: float = 30.0
    adapter_timeout_neotoma_sec: float = 25.0
    adapter_timeout_idigbio_sec: float = 20.0
    adapter_timeout_morphosource_sec: float = 20.0

    cache_ttl_sec: int = 86_400  # 24h
    host: str = "0.0.0.0"
    port: int = 8080
    default_radius_km: float = 10.0
    occurrence_limit: int = 50

    def timeout_for(self, provider: str) -> float:
        """Per-adapter timeout; global ADAPTER_TIMEOUT_SEC raises the floor."""
        overrides = {
            "GBIF": self.adapter_timeout_gbif_sec,
            "MINDAT": self.adapter_timeout_mindat_sec,
            "NEOTOMA": self.adapter_timeout_neotoma_sec,
            "IDIGBIO": self.adapter_timeout_idigbio_sec,
            "MORPHOSOURCE": self.adapter_timeout_morphosource_sec,
        }
        specific = overrides.get(provider.upper())
        if specific is None:
            return self.adapter_timeout_sec
        return max(self.adapter_timeout_sec, specific)

    def max_adapter_timeout_sec(self) -> float:
        return max(
            self.adapter_timeout_sec,
            self.adapter_timeout_gbif_sec,
            self.adapter_timeout_mindat_sec,
            self.adapter_timeout_neotoma_sec,
            self.adapter_timeout_idigbio_sec,
            self.adapter_timeout_morphosource_sec,
        )


settings = Settings()
