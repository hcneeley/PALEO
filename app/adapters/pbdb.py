"""Paleobiology Database occurrences adapter."""

from __future__ import annotations

import math

import httpx

from ..http import get_client

from ..config import settings
from .base import AdapterResult, QueryParams

PBDB_OCCS = "https://paleobiodb.org/data1.2/occs/list.json"


def _f(v) -> float | None:
    try:
        return float(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


async def fetch_and_parse(params: QueryParams) -> AdapterResult:
    if not params.taxon and (params.lat is None or params.lng is None):
        return AdapterResult(
            provider="PBDB",
            status="skipped",
            data={
                "features": [],
                "total_count": None,
                "offset": 0,
                "end_of_records": True,
                "fetched": 0,
            },
        )

    page = min(params.result_limit(), 300)
    offset = params.result_offset()

    q: dict = {
        "show": "coords,attr,class,paleoloc",
        "limit": page,
        "offset": offset,
    }
    if params.taxon:
        q["base_name"] = params.taxon
    elif params.lat is not None and params.lng is not None:
        r = params.radius_km or settings.default_radius_km
        dlat = r / 111.0
        dlng = r / (111.0 * max(math.cos(math.radians(params.lat)), 0.2))
        q["lngmin"] = params.lng - dlng
        q["lngmax"] = params.lng + dlng
        q["latmin"] = params.lat - dlat
        q["latmax"] = params.lat + dlat
    if params.age_max is not None:
        q["max_ma"] = params.age_max
    if params.age_min is not None:
        q["min_ma"] = params.age_min

    client = get_client()
    resp = await client.get(PBDB_OCCS, params=q)
    resp.raise_for_status()
    payload = resp.json()
    raw = payload.get("records") or []

    radius = params.radius_km or settings.default_radius_km
    features = []
    for rec in raw:
        oid = (rec.get("oid") or "").replace("occ:", "") or rec.get("oid")
        lat, lng = _f(rec.get("lat")), _f(rec.get("lng"))
        if (
            params.lat is not None
            and params.lng is not None
            and lat is not None
            and lng is not None
            and params.taxon
        ):
            if _haversine_km(params.lat, params.lng, lat, lng) > radius:
                continue
        geometry = None
        if lat is not None and lng is not None:
            geometry = {"type": "Point", "coordinates": [lng, lat]}
        max_ma, min_ma = _f(rec.get("eag")), _f(rec.get("lag"))
        paleolat = _f(rec.get("pla") if rec.get("pla") is not None else rec.get("paleolat"))
        paleolng = _f(rec.get("pln") if rec.get("pln") is not None else rec.get("paleolng"))
        event = None
        if max_ma is not None:
            mid = (max_ma + (min_ma or max_ma)) / 2.0
            event = str(int(-mid * 1_000_000))
        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "occurrence_id": f"pbdb:occ:{oid}" if oid else None,
                    "database_source": "PBDB",
                    "taxon_name": rec.get("tna"),
                    "accepted_name": rec.get("tna"),
                    "dwc_eventDate": event,
                    "max_ma": max_ma,
                    "min_ma": min_ma,
                    "paleolat": paleolat,
                    "paleolng": paleolng,
                },
            }
        )

    # PBDB has no catalog total; a short page means we're done.
    fetched = len(raw)
    end = fetched < page
    return AdapterResult(
        provider="PBDB",
        status="ok",
        data={
            "features": features,
            "total_count": None,
            "offset": offset,
            "end_of_records": end,
            "fetched": fetched,
        },
    )
