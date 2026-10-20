"""OpenMindat geomaterials + localities adapter.

Docs: https://api.mindat.org/v1/schema/redoc/
Patterns: https://github.com/ChuBL/How-to-Use-Mindat-API

Ties minerals to taxonomic queries by **place**:
  - With lat/lng: POST geomin-point / geoloc-point within radius_km
  - Name search only when no coordinates (mineral/geomaterial queries)

Requires MINDAT_API_KEY (env, key.env, or Render secret file).
"""

from __future__ import annotations

import math
from typing import Any

import httpx

from ..config import settings
from ..http import get_client
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


def _normalize_mineral(rec: dict[str, Any], *, link_mode: str | None = None) -> dict[str, Any]:
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
        "link_mode": link_mode,
    }


def _normalize_locality(
    rec: dict[str, Any],
    mineral_name: str | None = None,
    *,
    link_mode: str | None = None,
) -> dict[str, Any]:
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
        "link_mode": link_mode,
    }


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _ids(values: Any) -> list[int]:
    out: list[int] = []
    if isinstance(values, dict):
        # geomin-point: {mineral_id: [locality_ids]}
        for k in values.keys():
            if str(k).isdigit():
                out.append(int(k))
        return out
    if isinstance(values, list):
        for x in values:
            if isinstance(x, int) or (isinstance(x, str) and x.isdigit()):
                out.append(int(x))
    return out


def _locality_ids_from_geomin(payload: Any) -> list[int]:
    seen: list[int] = []
    if not isinstance(payload, dict):
        return seen
    for locs in payload.values():
        if not isinstance(locs, list):
            continue
        for x in locs:
            if isinstance(x, int) or (isinstance(x, str) and str(x).isdigit()):
                i = int(x)
                if i not in seen:
                    seen.append(i)
    return seen


async def _hydrate_minerals(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    mineral_ids: list[int],
    *,
    link_mode: str,
    limit: int,
) -> list[dict[str, Any]]:
    minerals: list[dict[str, Any]] = []
    for mid in mineral_ids[:limit]:
        try:
            resp = await client.get(
                MINDAT_BASE + f"geomaterials/{mid}/",
                params={"fields": MINERAL_FIELDS, "format": "json"},
                headers=headers,
                timeout=min(settings.timeout_for("MINDAT"), 8.0),
            )
            if resp.status_code < 400:
                body = resp.json()
                rows = _results(body) or ([body] if isinstance(body, dict) else [])
                if rows:
                    minerals.append(_normalize_mineral(rows[0], link_mode=link_mode))
        except httpx.HTTPError:
            continue
    return minerals


async def _hydrate_localities(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    loc_ids: list[int],
    *,
    link_mode: str,
    limit: int,
    origin: tuple[float, float] | None = None,
) -> list[dict[str, Any]]:
    if not loc_ids:
        return []
    try:
        resp = await client.get(
            MINDAT_BASE + "localities/",
            params={
                "id__in": ",".join(str(i) for i in loc_ids[:limit]),
                "fields": "id,txt,latitude,longitude,country",
                "page_size": min(limit, 50),
                "page": 1,
                "format": "json",
            },
            headers=headers,
            timeout=min(settings.timeout_for("MINDAT"), 12.0),
        )
        if resp.status_code >= 400:
            return []
        rows = _results(resp.json())
    except httpx.HTTPError:
        return []

    out: list[dict[str, Any]] = []
    for r in rows[:limit]:
        loc = _normalize_locality(r, link_mode=link_mode)
        if origin and loc.get("lat") is not None and loc.get("lon") is not None:
            loc["distance_km"] = round(
                _haversine_km(origin[0], origin[1], float(loc["lat"]), float(loc["lon"])),
                2,
            )
        out.append(loc)
    if origin:
        out.sort(key=lambda x: x.get("distance_km") if x.get("distance_km") is not None else 1e12)
    return out


async def fetch_spatial(
    params: QueryParams,
    *,
    lat: float | None = None,
    lng: float | None = None,
) -> AdapterResult:
    """Mindat minerals/localities near a point — used to link taxa by shared place."""
    key = mindat_api_key()
    if not key:
        return AdapterResult(
            provider="MINDAT",
            status="skipped",
            error="MINDAT_API_KEY not configured",
            data={"minerals": [], "localities": [], "link_mode": "spatial"},
        )
    lat = params.lat if lat is None else lat
    lng = params.lng if lng is None else lng
    if lat is None or lng is None:
        return AdapterResult(
            provider="MINDAT",
            status="skipped",
            error="lat/lng required for spatial Mindat link",
            data={"minerals": [], "localities": [], "link_mode": "spatial"},
        )

    headers = {
        "Authorization": f"Token {key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    limit = min(params.result_limit(), 20)
    radius = params.radius_km or settings.default_radius_km
    # Mindat expects distance like "50km"
    distance = f"{max(1, int(round(radius)))}km"
    body = {"point": {"lat": float(lat), "lon": float(lng)}, "distance": distance}
    client = get_client()

    minerals: list[dict[str, Any]] = []
    localities: list[dict[str, Any]] = []
    mineral_ids: list[int] = []
    loc_ids: list[int] = []
    # mineral_id -> locality ids from geomin (used to drop minerals whose
    # Mindat-linked localities all fall outside radius_km)
    mineral_to_locs: dict[int, list[int]] = {}

    try:
        geomin = await client.post(
            MINDAT_BASE + "geomin-point/",
            json=body,
            headers=headers,
            timeout=min(settings.timeout_for("MINDAT"), 20.0),
        )
        if geomin.status_code < 400:
            payload = geomin.json()
            if isinstance(payload, dict):
                for k, locs in payload.items():
                    if not str(k).isdigit():
                        continue
                    mid = int(k)
                    cleaned = [
                        int(x)
                        for x in (locs or [])
                        if isinstance(x, int) or (isinstance(x, str) and str(x).isdigit())
                    ]
                    mineral_to_locs[mid] = cleaned
                mineral_ids = list(mineral_to_locs.keys())[: max(limit * 2, limit)]
                loc_ids = _locality_ids_from_geomin(payload)[: max(limit * 3, 30)]
            else:
                mineral_ids = _ids(payload)[:limit]
                loc_ids = []
    except httpx.HTTPError:
        mineral_ids = []

    if not loc_ids:
        try:
            geoloc = await client.post(
                MINDAT_BASE + "geoloc-point/",
                json=body,
                headers=headers,
                timeout=min(settings.timeout_for("MINDAT"), 20.0),
            )
            if geoloc.status_code < 400:
                loc_ids = _ids(geoloc.json())[: max(limit * 3, 30)]
        except httpx.HTTPError:
            loc_ids = []

    if mineral_ids:
        minerals = await _hydrate_minerals(
            client, headers, mineral_ids, link_mode="spatial", limit=max(limit * 2, limit)
        )
    localities = await _hydrate_localities(
        client,
        headers,
        loc_ids,
        link_mode="spatial",
        limit=max(limit * 3, 30),
        origin=(float(lat), float(lng)),
    )

    # Mindat geomin/geoloc sometimes returns far-away IDs — enforce radius client-side.
    radius_f = float(radius)
    in_radius = [
        loc
        for loc in localities
        if loc.get("distance_km") is not None and float(loc["distance_km"]) <= radius_f + 0.5
    ]
    in_radius_ids = {
        int(str(loc.get("locality_id") or "").rsplit(":", 1)[-1])
        for loc in in_radius
        if loc.get("locality_id") and str(loc.get("locality_id")).rsplit(":", 1)[-1].isdigit()
    }

    if mineral_to_locs and in_radius_ids:
        keep_mids = {
            mid
            for mid, locs in mineral_to_locs.items()
            if any(lid in in_radius_ids for lid in locs)
        }
        minerals = [
            m
            for m in minerals
            if (m.get("mineral_id") or "").rsplit(":", 1)[-1].isdigit()
            and int((m.get("mineral_id") or "").rsplit(":", 1)[-1]) in keep_mids
        ]
    elif mineral_to_locs and not in_radius_ids:
        # No verified nearby localities — don't claim distant minerals as linked.
        minerals = []

    localities = in_radius[:limit]
    minerals = minerals[:limit]

    return AdapterResult(
        provider="MINDAT",
        status="ok",
        data={
            "minerals": minerals,
            "localities": localities,
            "link_mode": "spatial",
            "linked_taxon": params.taxon,
            "link_lat": lat,
            "link_lng": lng,
            "link_radius_km": radius,
        },
    )


async def fetch_by_name(params: QueryParams) -> AdapterResult:
    """Direct geomaterial name search (for mineral queries, not fossil taxa)."""
    key = mindat_api_key()
    if not key:
        return AdapterResult(
            provider="MINDAT",
            status="skipped",
            error="MINDAT_API_KEY not configured",
            data={"minerals": [], "localities": [], "link_mode": "name"},
        )
    if not params.taxon:
        return AdapterResult(
            provider="MINDAT",
            status="skipped",
            error="taxon required for name search",
            data={"minerals": [], "localities": [], "link_mode": "name"},
        )

    headers = {
        "Authorization": f"Token {key}",
        "Accept": "application/json",
    }
    limit = min(params.result_limit(), 25)
    minerals: list[dict[str, Any]] = []
    localities: list[dict[str, Any]] = []
    client = get_client()

    try:
        resp = await client.get(
            MINDAT_BASE + "geomaterials-search/",
            params={"q": params.taxon, "size": limit, "ima": 1, "format": "json"},
            headers=headers,
        )
        if resp.status_code < 400:
            minerals = [
                _normalize_mineral(r, link_mode="name")
                for r in _results(resp.json())[:limit]
            ]
    except httpx.HTTPError:
        minerals = []

    if not minerals:
        try:
            resp = await client.get(
                MINDAT_BASE + "minerals-ima/",
                params={"q": params.taxon, "page": 1, "page_size": limit, "format": "json"},
                headers=headers,
            )
            if resp.status_code < 400:
                minerals = [
                    _normalize_mineral(r, link_mode="name")
                    for r in _results(resp.json())[:limit]
                ]
        except httpx.HTTPError:
            minerals = []

    if minerals:
        mid = (minerals[0].get("mineral_id") or "").split(":")[-1]
        if mid.isdigit():
            try:
                detail = await client.get(
                    MINDAT_BASE + f"geomaterials/{mid}/",
                    params={"fields": "id,name,locality", "format": "json"},
                    headers=headers,
                    timeout=min(settings.timeout_for("MINDAT"), 12.0),
                )
                loc_ids: list[int] = []
                if detail.status_code < 400:
                    body = detail.json()
                    rows = _results(body) or ([body] if isinstance(body, dict) else [])
                    raw_ids = (rows[0].get("locality") if rows else None) or []
                    loc_ids = [int(x) for x in raw_ids if str(x).isdigit()][: min(limit, 10)]
                if loc_ids:
                    localities = await _hydrate_localities(
                        client,
                        headers,
                        loc_ids,
                        link_mode="name",
                        limit=min(limit, 10),
                    )
                    name = minerals[0].get("name")
                    for loc in localities:
                        loc["mineral"] = name
            except httpx.HTTPError:
                localities = []

    return AdapterResult(
        provider="MINDAT",
        status="ok",
        data={
            "minerals": minerals,
            "localities": localities,
            "link_mode": "name",
            "linked_taxon": params.taxon,
        },
    )


async def fetch_and_parse(params: QueryParams) -> AdapterResult:
    """Prefer spatial link when coordinates exist; otherwise mineral name search."""
    if params.lat is not None and params.lng is not None:
        return await fetch_spatial(params)
    if params.taxon:
        return await fetch_by_name(params)
    return AdapterResult(
        provider="MINDAT",
        status="skipped",
        error="Provide lat/lng (spatial link to taxon area) or a mineral name",
        data={"minerals": [], "localities": []},
    )
