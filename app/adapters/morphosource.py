"""MorphoSource 3D media — MVP stub."""

from __future__ import annotations

from .base import AdapterResult, QueryParams


async def fetch_and_parse(params: QueryParams) -> AdapterResult:
    return AdapterResult(
        provider="MORPHOSOURCE",
        status="stub",
        error="MVP stub — MorphoSource not wired yet",
        data={"records": []},
    )
