"""GBIF extant occurrences — MVP stub."""

from __future__ import annotations

from .base import AdapterResult, QueryParams


async def fetch_and_parse(params: QueryParams) -> AdapterResult:
    return AdapterResult(
        provider="GBIF",
        status="stub",
        error="MVP stub — GBIF not wired yet",
        data={"features": []},
    )
