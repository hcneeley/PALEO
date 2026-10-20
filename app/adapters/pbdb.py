"""Paleobiology Database occurrences adapter."""

from __future__ import annotations

import httpx

from ..config import settings
from .base import AdapterResult, QueryParams

PBDB_OCCS = "https://paleobiodb.org/data1.2/occs/list.json"


def _f(v) -> float | None:
    try:
        return float(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


async def fetch_and_parse(params: QueryParams) -> AdapterResult:
    if not params.taxon and (params.lat is None or params.lng is None):
        return AdapterResult(provider="PBDB", status="skipped", data={"features": []})

    q: dict = {
        "show": "coords,attr,class,paleoloc",
        "limit": settings.occurrence_limit,
    }
    if params.taxon:
        q["base_name"] = params.taxon
    if params.lat is not None and params.lng is not None:
        # PBDB circle: lng,lat,radius_km (approx; API uses deg in some versions —
        # use loc=lng,lat with a small box via cluster if needed; circle param:
        # https://paleobiodb.org/data1.2/occs/list — `loc` is WKT / circle
        r = params.radius_km or settings.default_radius_km
        q["loc"] = f"circle(Point({params.lng} {params.lat}),{r})"
    if params.age_max is not None:
        q["max_ma"] = params.age_max
    if params.age_min is not None:
        q["min_ma"] = params.age_min

    async with httpx.AsyncClient(timeout=settings.adapter_timeout_sec) as client:
        resp = await client.get(PBDB_OCCS, params=q)
        resp.raise_for_status()
        payload = resp.json()

    features = []
    for rec in payload.get("records") or []:
        oid = (rec.get("oid") or "").replace("occ:", "") or rec.get("oid")
        lat, lng = _f(rec.get("lat")), _f(rec.get("lng"))
        geometry = None
        if lat is not None and lng is not None:
            geometry = {"type": "Point", "coordinates": [lng, lat]}
        max_ma, min_ma = _f(rec.get("eag")), _f(rec.get("lag"))
        event = None
        if max_ma is not None:
            # Approximate mid-age years before present for DwC-ish field
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
                },
            }
        )

    return AdapterResult(provider="PBDB", status="ok", data={"features": features})
