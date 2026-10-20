"""Macrostrat units-at-point adapter."""

from __future__ import annotations

import httpx

from ..http import get_client

from ..config import settings
from .base import AdapterResult, QueryParams

MACROSTRAT_UNITS = "https://macrostrat.org/api/v2/units"


def _primary_lith(unit: dict) -> str | None:
    liths = unit.get("lith") or []
    if not liths:
        return None
    best = max(liths, key=lambda L: L.get("prop") or 0)
    return best.get("name")


def _primary_env(unit: dict) -> str | None:
    envs = unit.get("environ") or []
    if not envs:
        return None
    return envs[0].get("name")


async def fetch_and_parse(params: QueryParams) -> AdapterResult:
    if params.lat is None or params.lng is None:
        return AdapterResult(
            provider="MACROSTRAT",
            status="skipped",
            error="lat and lng required",
            data={"units": []},
        )

    q = {
        "lat": params.lat,
        "lng": params.lng,
        "response": "long",
        "format": "json",
    }
    client = get_client()
    resp = await client.get(MACROSTRAT_UNITS, params=q)
    resp.raise_for_status()
    payload = resp.json()

    raw = (payload.get("success") or {}).get("data") or []
    units = []
    for unit in raw[: settings.occurrence_limit]:
        units.append(
            {
                "unit_id": unit.get("unit_id"),
                "unit_name": unit.get("strat_name_long") or unit.get("unit_name"),
                "lithology": _primary_lith(unit),
                "age_bottom_ma": unit.get("b_age"),
                "age_top_ma": unit.get("t_age"),
                "environment": _primary_env(unit),
            }
        )
    return AdapterResult(provider="MACROSTRAT", status="ok", data={"units": units})
