"""OpenMindat geomaterials + localities adapter.

Docs: https://api.mindat.org/v1/schema/redoc/
Patterns: https://github.com/ChuBL/How-to-Use-Mindat-API

Requires MINDAT_API_KEY (env, key.env, or Render secret file).
"""

from __future__ import annotations

from typing import Any

import httpx

from ..config import settings
from ..secrets import mindat_api_key
from .base import AdapterResult, QueryParams

MINDAT_BASE = "https://api.mindat.org/v1/"
MINERAL_FIELDS = "id,name,mindat_formula,ima_formula,csystem,hmin,hmax,ima_status"


def _results(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        rows = data.get("results")
        if isinstance(rows, list):
            return [r for r in rows if isinstance(r, dict)]
        if "id" in data and ("name" in data or "txt" in data):
            return [data]
    return []


def _normalize_mineral(rec: dict[str, Any]) -> dict[str, Any]:
    mid = rec.get("id")
    return {
        "provider": "Mindat",
        "mineral_id": f"mindat:min:{mid}" if mid is not None else None,
        "name": rec.get("name") or rec.get("title"),
        "formula": rec.get("mindat_formula") or rec.get("ima_formula") or rec.get("formula"),
        "ima_status": rec.get("ima_status"),
        "crystal_system": rec.get("csystem") or rec.get("crystal_system"),
        "hardness_min": rec.get("hmin"),
        "hardness_max": rec.get("hmax"),
        "url": f"https://www.mindat.org/min-{mid}.html" if mid is not None else None,
    }


def _normalize_locality(rec: dict[str, Any], mineral_name: str | None = None) -> dict[str, Any]:
    lid = rec.get("id")
    lat, lon = rec.get("latitude"), rec.get("longitude")
    try:
        lat_f = float(lat) if lat is not None else None
        lon_f = float(lon) if lon is not None else None
    except (TypeError, ValueError):
        lat_f = lon_f = None
    if lat_f == 0.0 and lon_f == 0.0:
        lat_f = lon_f = None
    return {
        "provider": "Mindat",
        "locality_id": f"mindat:loc:{lid}" if lid is not None else None,
        "name": rec.get("txt") or rec.get("name"),
        "country": rec.get("country"),
        "lat": lat_f,
        "lon": lon_f,
        "mineral": mineral_name,
        "url": f"https://www.mindat.org/loc-{lid}.html" if lid is not None else None,
    }


async def fetch_and_parse(params: QueryParams) -> AdapterResult:
    key = mindat_api_key()
    if not key:
        return AdapterResult(
            provider="MINDAT",
            status="skipped",
            error="MINDAT_API_KEY not configured",
            data={"minerals": [], "localities": []},
        )
    if not params.taxon:
        return AdapterResult(
            provider="MINDAT",
            status="skipped",
            error="taxon required (used as mineral / geomaterial query)",
            data={"minerals": [], "localities": []},
        )

    headers = {
        "Authorization": f"Token {key}",
        "Accept": "application/json",
    }
    limit = min(settings.occurrence_limit, 25)
    minerals: list[dict[str, Any]] = []
    localities: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=settings.adapter_timeout_sec, headers=headers) as client:
        # 1) geomaterials-search
        try:
            resp = await client.get(
                MINDAT_BASE + "geomaterials-search/",
                params={"q": params.taxon, "size": limit, "ima": 1, "format": "json"},
            )
            if resp.status_code < 400:
                minerals = [_normalize_mineral(r) for r in _results(resp.json())[:limit]]
        except httpx.HTTPError:
            minerals = []

        # 2) fallback minerals-ima
        if not minerals:
            resp = await client.get(
                MINDAT_BASE + "minerals-ima/",
                params={"q": params.taxon, "page": 1, "page_size": limit, "format": "json"},
            )
            resp.raise_for_status()
            minerals = [_normalize_mineral(r) for r in _results(resp.json())[:limit]]

        # 3) localities for top hit (cap IDs — common minerals like quartz can hang on full expand)
        if minerals:
            mid = (minerals[0].get("mineral_id") or "").split(":")[-1]
            if mid.isdigit():
                try:
                    detail = await client.get(
                        MINDAT_BASE + f"geomaterials/{mid}/",
                        params={
                            "fields": "id,name,locality",
                            "format": "json",
                        },
                        timeout=min(settings.adapter_timeout_sec, 8.0),
                    )
                    loc_ids: list[int] = []
                    if detail.status_code < 400:
                        body = detail.json()
                        rows = _results(body) or ([body] if isinstance(body, dict) else [])
                        raw_ids = (rows[0].get("locality") if rows else None) or []
                        loc_ids = [int(x) for x in raw_ids if str(x).isdigit()][: min(limit, 10)]
                    if loc_ids:
                        loc_resp = await client.get(
                            MINDAT_BASE + "localities/",
                            params={
                                "id__in": ",".join(str(i) for i in loc_ids),
                                "fields": "id,txt,latitude,longitude,country",
                                "page_size": min(limit, 10),
                                "page": 1,
                                "format": "json",
                            },
                            timeout=min(settings.adapter_timeout_sec, 8.0),
                        )
                        if loc_resp.status_code < 400:
                            mineral_name = minerals[0].get("name")
                            localities = [
                                _normalize_locality(r, mineral_name)
                                for r in _results(loc_resp.json())[:limit]
                            ]
                except httpx.HTTPError:
                    localities = []

    return AdapterResult(
        provider="MINDAT",
        status="ok",
        data={"minerals": minerals, "localities": localities},
    )
