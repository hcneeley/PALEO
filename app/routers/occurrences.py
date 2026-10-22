"""GET /api/v1/occurrences — paginated single-provider occurrence fetch."""

from __future__ import annotations

from fastapi import APIRouter, Query, Response
from pydantic import ValidationError

from ..adapters import gbif, neotoma, pbdb
from ..adapters.base import QueryParams, run_adapter
from ..config import settings
from ..models.schemas import OccurrenceFeature

router = APIRouter(prefix="/api/v1", tags=["occurrences"])

PAGEABLE = {
    "GBIF": gbif.fetch_and_parse,
    "PBDB": pbdb.fetch_and_parse,
    "NEOTOMA": neotoma.fetch_and_parse,
}

# GBIF occurrence search hard window.
GBIF_SEARCH_WINDOW = 100_000


@router.get("/occurrences")
async def occurrences_page(
    response: Response,
    provider: str = Query(..., description="Upstream provider: GBIF, PBDB, or NEOTOMA"),
    lat: float | None = Query(None, description="Latitude (decimal degrees)"),
    lng: float | None = Query(None, description="Longitude (decimal degrees)"),
    radius_km: float | None = Query(None, description="Search radius in km"),
    taxon: str | None = Query(None, description="Scientific name / taxon query"),
    age_min: float | None = Query(None, description="Younger age bound (Ma)"),
    age_max: float | None = Query(None, description="Older age bound (Ma)"),
    offset: int = Query(0, ge=0, description="Result offset"),
    limit: int = Query(100, ge=1, le=300, description="Page size (1–300)"),
) -> dict:
    if lat is None and lng is None and not taxon:
        response.status_code = 400
        return {"status": "error", "detail": "Provide taxon and/or lat+lng"}

    key = (provider or "").strip().upper()
    fetch = PAGEABLE.get(key)
    if fetch is None:
        response.status_code = 422
        return {
            "status": "error",
            "detail": (
                f"Unsupported provider for paging: {provider}. "
                f"Supported: {', '.join(sorted(PAGEABLE))}"
            ),
        }

    radius = radius_km if radius_km is not None else settings.default_radius_km
    params = QueryParams(
        lat=lat,
        lng=lng,
        radius_km=radius,
        taxon=taxon,
        age_min=age_min,
        age_max=age_max,
        limit=limit,
        offset=offset,
    )

    result = await run_adapter(key, lambda: fetch(params), timeout=settings.timeout_for(key))
    if result.status != "ok":
        response.status_code = 502 if result.status == "error" else 200
        return {
            "status": result.status,
            "provider": key,
            "detail": result.error,
            "features": [],
            "returned": 0,
            "total": None,
            "offset": offset,
            "next_offset": None,
            "has_more": False,
        }

    features: list[dict] = []
    for feat in (result.data or {}).get("features") or []:
        try:
            features.append(OccurrenceFeature.model_validate(feat).model_dump(mode="json"))
        except ValidationError:
            continue

    total = (result.data or {}).get("total_count")
    if total is not None:
        try:
            total = int(total)
        except (TypeError, ValueError):
            total = None

    returned = len(features)
    fetched = (result.data or {}).get("fetched")
    try:
        fetched_n = int(fetched) if fetched is not None else returned
    except (TypeError, ValueError):
        fetched_n = returned

    end = bool((result.data or {}).get("end_of_records"))
    if fetched_n == 0:
        end = True

    next_offset = offset + fetched_n
    window_hit = key == "GBIF" and next_offset >= GBIF_SEARCH_WINDOW
    has_more = (not end) and fetched_n > 0 and not window_hit
    if isinstance(total, int) and next_offset >= total:
        has_more = False

    return {
        "status": "success",
        "provider": key,
        "features": features,
        "returned": returned,
        "total": total,
        "offset": offset,
        "next_offset": next_offset if has_more else None,
        "has_more": has_more,
        "search_window": GBIF_SEARCH_WINDOW if key == "GBIF" else None,
        "window_exhausted": bool(
            window_hit and (total is None or (isinstance(total, int) and total > GBIF_SEARCH_WINDOW))
        ),
    }
