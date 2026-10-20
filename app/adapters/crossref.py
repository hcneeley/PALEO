"""CrossRef bibliographic metadata — MVP stub."""

from __future__ import annotations

from .base import AdapterResult, QueryParams


async def fetch_and_parse(params: QueryParams) -> AdapterResult:
    return AdapterResult(
        provider="CROSSREF",
        status="stub",
        error="MVP stub — CrossRef not wired yet",
        data={"literature": []},
    )
