"""NCEI NOAA Paleo Data Search adapter.

Docs: https://www.ncei.noaa.gov/access/paleo-search/api
Endpoint: GET https://www.ncei.noaa.gov/access/paleo-search/study/search.json

Returns paleoclimate / paleoenvironmental studies near a point (and optional
taxon text / age bounds). Full study payloads are capped at 10 by NOAA.
"""

from __future__ import annotations

import math
from typing import Any

import httpx

from ..config import settings
from .base import AdapterResult, QueryParams

NOAA_SEARCH = "https://www.ncei.noaa.gov/access/paleo-search/study/search.json"
# Climate reconstructions | tree ring | pollen | paleolimnology | ice cores
DEFAULT_DATA_TYPES = "3|18|16|13|7"


def _f(v) -> float | None:
    try:
        return float(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


def _bbox(lat: float, lng: float, radius_km: float) -> dict[str, float]:
    dlat = radius_km / 111.0
    dlng = radius_km / (111.0 * max(math.cos(math.radians(lat)), 0.2))
    return {
        "minLat": max(-90.0, lat - dlat),
        "maxLat": min(90.0, lat + dlat),
        "minLon": max(-180.0, lng - dlng),
        "maxLon": min(180.0, lng + dlng),
    }


def _site_point(site: dict[str, Any]) -> tuple[float | None, float | None, str | None]:
    name = site.get("siteName")
    geo = site.get("geo") or {}
    props = geo.get("properties") or {}
    # Prefer property midpoints when geometry is a bounding box / polygon
    south = _f(props.get("southernmostLatitude"))
    north = _f(props.get("northernmostLatitude"))
    west = _f(props.get("westernmostLongitude"))
    east = _f(props.get("easternmostLongitude"))
    if None not in (south, north, west, east):
        return (south + north) / 2.0, (west + east) / 2.0, name
    geom = geo.get("geometry") or {}
    coords = geom.get("coordinates")
    if geom.get("type") == "Point" and isinstance(coords, (list, tuple)) and len(coords) >= 2:
        # NOAA examples sometimes use [lat, lon]
        a, b = _f(coords[0]), _f(coords[1])
        if a is not None and b is not None:
            if abs(a) <= 90 and abs(b) <= 180:
                return a, b, name
            return b, a, name
    return None, None, name


def _normalize_study(study: dict[str, Any]) -> dict[str, Any]:
    sites = study.get("site") or []
    lat = lng = site_name = None
    if sites:
        lat, lng, site_name = _site_point(sites[0])
    xml_id = study.get("xmlId")
    noaa_id = study.get("NOAAStudyId")
    data_types = study.get("dataType") or []
    if isinstance(data_types, list):
        dtype = ", ".join(str(x) for x in data_types) if data_types else None
    else:
        dtype = str(data_types) if data_types else None
    return {
        "study_id": str(xml_id) if xml_id is not None else None,
        "noaa_study_id": str(noaa_id) if noaa_id is not None else None,
        "study_name": study.get("studyName"),
        "doi": study.get("doi"),
        "data_type": dtype,
        "investigators": study.get("investigators"),
        "site_name": site_name,
        "lat": lat,
        "lng": lng,
        "data_publisher": study.get("dataPublisher"),
        "url": (
            f"https://www.ncei.noaa.gov/access/paleo-search/study/{xml_id}"
            if xml_id is not None
            else study.get("onlineResourceLink")
        ),
    }


async def fetch_and_parse(params: QueryParams) -> AdapterResult:
    target = None
    if params.age_min is not None and params.age_max is not None:
        target = (params.age_min + params.age_max) / 2.0
    elif params.age_max is not None:
        target = params.age_max

    if params.lat is None and params.lng is None and not params.taxon:
        return AdapterResult(
            provider="PALEOCLIMATE",
            status="skipped",
            error="lat+lng and/or taxon required",
            data={
                "proxy": {
                    "target_ma": target,
                    "estimated_mat_celsius": None,
                    "estimated_map_mm": None,
                    "estimated_pco2_ppm": None,
                    "model_source": "NCEI Paleo Search",
                    "status": "skipped",
                    "study_count": 0,
                    "studies": [],
                }
            },
        )

    # NOAA full-study responses max out at 10
    limit = min(10, max(1, settings.occurrence_limit // 5 or 10))
    q: dict[str, Any] = {
        "dataPublisher": "NOAA",
        "dataTypeId": DEFAULT_DATA_TYPES,
        "limit": limit,
    }
    if params.lat is not None and params.lng is not None:
        q.update(_bbox(params.lat, params.lng, params.radius_km or settings.default_radius_km))
    if params.taxon:
        q["searchText"] = params.taxon
    # age_max/min are Ma → years BP for NOAA time filters
    if params.age_max is not None or params.age_min is not None:
        older = params.age_max if params.age_max is not None else params.age_min
        younger = params.age_min if params.age_min is not None else 0.0
        if older is not None and younger is not None and older < younger:
            older, younger = younger, older
        q["timeFormat"] = "BP"
        q["timeMethod"] = "overAny"
        if older is not None:
            q["earliestYear"] = int(older * 1_000_000)
        if younger is not None:
            q["latestYear"] = int(younger * 1_000_000)

    async with httpx.AsyncClient(timeout=settings.adapter_timeout_sec) as client:
        resp = await client.get(NOAA_SEARCH, params=q)
        resp.raise_for_status()
        payload = resp.json()

    studies_raw = payload.get("study") or []
    studies = [_normalize_study(s) for s in studies_raw]
    return AdapterResult(
        provider="PALEOCLIMATE",
        status="ok",
        data={
            "proxy": {
                "target_ma": target,
                "estimated_mat_celsius": None,
                "estimated_map_mm": None,
                "estimated_pco2_ppm": None,
                "model_source": "NCEI Paleo Search (NOAA)",
                "status": "ok",
                "study_count": len(studies),
                "studies": studies,
            },
            "studies": studies,
        },
    )
