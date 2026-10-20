"""GET /api/v1/synthesize — federated paleontology synthesis."""

from __future__ import annotations

import asyncio
import time
from functools import partial
from typing import Any

from fastapi import APIRouter, Query, Response

from .. import adapters
from ..adapters.base import QueryParams, run_adapter
from ..cache import cache, make_cache_key
from ..config import settings
from ..gts import normalize_age_bounds
from ..models.schemas import (
    Coordinates,
    GeologyBlock,
    GtsNormalizedAge,
    MacrostratUnit,
    Media3dBlock,
    Media3dRecord,
    OccurrenceFeature,
    OccurrencesBlock,
    PaleoclimateProxy,
    QueryBlock,
    SpecimenRecord,
    SpecimensBlock,
    SynthesizeResponse,
)

router = APIRouter(prefix="/api/v1", tags=["synthesize"])


def _assemble(params: QueryParams, results: dict[str, Any], *, elapsed_ms: float, cache_status: str) -> dict:
    diagnostics = [r.diagnostic() for r in results.values()]

    units_raw = (results["MACROSTRAT"].data or {}).get("units") or []
    geology = GeologyBlock(
        macrostrat_units=[MacrostratUnit(**u) for u in units_raw]
    )

    features: list[OccurrenceFeature] = []
    for key in ("PBDB", "NEOTOMA", "GBIF"):
        for feat in (results[key].data or {}).get("features") or []:
            features.append(OccurrenceFeature.model_validate(feat))

    specimens_raw = (results["IDIGBIO"].data or {}).get("records") or []
    specimens = SpecimensBlock(
        voucher_count=len(specimens_raw),
        records=[SpecimenRecord.model_validate(r) for r in specimens_raw],
    )

    media_raw = (results["MORPHOSOURCE"].data or {}).get("records") or []
    media = Media3dBlock(
        has_3d_assets=bool(media_raw),
        records=[Media3dRecord.model_validate(r) for r in media_raw],
        status=results["MORPHOSOURCE"].status if results["MORPHOSOURCE"].status != "ok" else None,
    )

    climate_raw = (results["PALEOCLIMATE"].data or {}).get("proxy") or {}
    paleoclimate = PaleoclimateProxy.model_validate(climate_raw)

    literature = (results["CROSSREF"].data or {}).get("literature") or []

    gts = normalize_age_bounds(params.age_min, params.age_max)
    body = SynthesizeResponse(
        status="success",
        execution_time_ms=round(elapsed_ms, 2),
        cache_status=cache_status,
        query=QueryBlock(
            taxon=params.taxon,
            coordinates=Coordinates(lat=params.lat, lng=params.lng),
            radius_km=params.radius_km,
            gts_normalized_age=GtsNormalizedAge(
                epoch=gts.get("epoch"),  # type: ignore[arg-type]
                stage=gts.get("stage"),  # type: ignore[arg-type]
                age_min_ma=gts.get("age_min_ma"),  # type: ignore[arg-type]
                age_max_ma=gts.get("age_max_ma"),  # type: ignore[arg-type]
            ),
        ),
        geology=geology,
        paleoclimate_proxy=paleoclimate,
        occurrences=OccurrencesBlock(
            total_records=len(features),
            features=features,
        ),
        specimens=specimens,
        media_3d=media,
        literature=literature,
        diagnostics=diagnostics,
    )
    return body.model_dump(mode="json")


@router.get("/synthesize")
async def synthesize(
    response: Response,
    lat: float | None = Query(None, description="Latitude (decimal degrees)"),
    lng: float | None = Query(None, description="Longitude (decimal degrees)"),
    radius_km: float | None = Query(None, description="Search radius in km"),
    taxon: str | None = Query(None, description="Clade, genus, or species"),
    age_min: float | None = Query(None, description="Younger age bound (Ma)"),
    age_max: float | None = Query(None, description="Older age bound (Ma)"),
) -> dict:
    if lat is None and lng is None and not taxon:
        response.status_code = 400
        return {
            "status": "error",
            "detail": "Provide taxon and/or lat+lng",
        }

    radius = radius_km if radius_km is not None else settings.default_radius_km
    key = make_cache_key(
        lat=lat,
        lng=lng,
        radius_km=radius,
        taxon=taxon,
        age_min=age_min,
        age_max=age_max,
    )
    cached = cache.get(key)
    if cached is not None:
        response.headers["X-Cache"] = "HIT"
        out = dict(cached)
        out["cache_status"] = "HIT"
        return out

    params = QueryParams(
        lat=lat,
        lng=lng,
        radius_km=radius,
        taxon=taxon,
        age_min=age_min,
        age_max=age_max,
    )

    t0 = time.perf_counter()
    names = [
        ("PBDB", adapters.pbdb.fetch_and_parse),
        ("MACROSTRAT", adapters.macrostrat.fetch_and_parse),
        ("NEOTOMA", adapters.neotoma.fetch_and_parse),
        ("IDIGBIO", adapters.idigbio.fetch_and_parse),
        ("MORPHOSOURCE", adapters.morphosource.fetch_and_parse),
        ("GBIF", adapters.gbif.fetch_and_parse),
        ("PALEOCLIMATE", adapters.paleoclimate.fetch_and_parse),
        ("CROSSREF", adapters.crossref.fetch_and_parse),
    ]
    gathered = await asyncio.gather(
        *[run_adapter(name, partial(fn, params)) for name, fn in names]
    )
    results = {r.provider: r for r in gathered}
    elapsed_ms = (time.perf_counter() - t0) * 1000
    payload = _assemble(params, results, elapsed_ms=elapsed_ms, cache_status="MISS")
    cache.set(key, payload)
    response.headers["X-Cache"] = "MISS"
    return payload
