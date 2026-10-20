"""PaleoDAP / deep-time climate — MVP stub."""

from __future__ import annotations

from .base import AdapterResult, QueryParams


async def fetch_and_parse(params: QueryParams) -> AdapterResult:
    target = None
    if params.age_min is not None and params.age_max is not None:
        target = (params.age_min + params.age_max) / 2.0
    elif params.age_max is not None:
        target = params.age_max
    return AdapterResult(
        provider="PALEOCLIMATE",
        status="stub",
        error="MVP stub — PaleoDAP not wired yet",
        data={
            "proxy": {
                "target_ma": target,
                "estimated_mat_celsius": None,
                "estimated_map_mm": None,
                "estimated_pco2_ppm": None,
                "model_source": None,
                "status": "stub",
            }
        },
    )
