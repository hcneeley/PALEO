"""GET /api/v1/synthesize — federated paleontology synthesis."""

from __future__ import annotations

import asyncio
import time
from functools import partial
from typing import Any

from fastapi import APIRouter, Query, Response
from pydantic import ValidationError

from .. import adapters
from ..adapters.base import AdapterResult, QueryParams, run_adapter
from ..cache import cache, make_cache_key
from ..config import settings
from ..gts import normalize_age_bounds
from ..models.schemas import (
    Coordinates,
    GeologyBlock,
    GtsNormalizedAge,
    LiteratureRecord,
    MacrostratUnit,
    Media3dBlock,
    Media3dRecord,
    MineralLocality,
    MineralRecord,
    MineralsBlock,
    OccurrenceFeature,
    OccurrencesBlock,
    PaleoclimateProxy,
    QueryBlock,
    SpecimenRecord,
    SpecimensBlock,
    SynthesizeResponse,
)

router = APIRouter(prefix="/api/v1", tags=["synthesize"])

def _safe_models(model, rows: list) -> list:
    out = []
    for row in rows:
        try:
            out.append(model.model_validate(row))
        except ValidationError:
            continue
    return out




def _assemble(params: QueryParams, results: dict[str, Any], *, elapsed_ms: float, cache_status: str) -> dict:
    diagnostics = [r.diagnostic() for r in results.values()]

    macro = results.get("MACROSTRAT")
    units_raw = (macro.data or {}).get("units") or [] if macro else []
    geology = GeologyBlock(
        macrostrat_units=_safe_models(MacrostratUnit, units_raw)
    )

    features: list[OccurrenceFeature] = []
    for key in ("PBDB", "NEOTOMA", "GBIF"):
        adapter = results.get(key)
        if not adapter:
            continue
        for feat in (adapter.data or {}).get("features") or []:
            try:
                features.append(OccurrenceFeature.model_validate(feat))
            except ValidationError:
                continue

    idig = results.get("IDIGBIO")
    specimens_raw = (idig.data or {}).get("records") or [] if idig else []
    specimen_records = _safe_models(SpecimenRecord, specimens_raw)
    specimens = SpecimensBlock(
        voucher_count=len(specimen_records),
        records=specimen_records,
    )

    ms = results.get("MORPHOSOURCE")
    media_raw = (ms.data or {}).get("records") or [] if ms else []
    ms_status = ms.status if ms else "skipped"
    media_records = _safe_models(Media3dRecord, media_raw)
    media = Media3dBlock(
        has_3d_assets=bool(media_records),
        records=media_records,
        status=None if ms_status == "ok" else ms_status,
    )

    climate = results.get("PALEOCLIMATE")
    climate_raw = (climate.data or {}).get("proxy") or {} if climate else {}
    try:
        paleoclimate = PaleoclimateProxy.model_validate(climate_raw)
    except ValidationError:
        paleoclimate = PaleoclimateProxy(status="error")

    # OpenAlex first (relevance), then Crossref; dedupe by DOI
    literature_raw: list[Any] = []
    seen_doi: set[str] = set()
    for key in ("OPENALEX", "CROSSREF"):
        adapter = results.get(key)
        for row in ((adapter.data or {}).get("literature") or [] if adapter else []):
            doi = (row.get("doi") or "").strip().lower()
            if doi and doi in seen_doi:
                continue
            if doi:
                seen_doi.add(doi)
            literature_raw.append(row)
    literature = _safe_models(LiteratureRecord, literature_raw)

    mindat = results.get("MINDAT")
    minerals_raw = (mindat.data or {}).get("minerals") or [] if mindat else []
    localities_raw = (mindat.data or {}).get("localities") or [] if mindat else []
    mindat_status = mindat.status if mindat else "skipped"
    minerals_block = MineralsBlock(
        mineral_count=len(minerals_raw),
        locality_count=len(localities_raw),
        minerals=_safe_models(MineralRecord, minerals_raw),
        localities=_safe_models(MineralLocality, localities_raw),
        status=None if mindat_status == "ok" else mindat_status,
    )

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
        minerals=minerals_block,
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
    taxon: str | None = Query(
        None, description="Clade, genus, species, or mineral/geomaterial name"
    ),
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
        ("OPENALEX", adapters.openalex.fetch_and_parse),
        ("MINDAT", adapters.mindat.fetch_and_parse),
    ]
    gathered = await asyncio.gather(
        *[run_adapter(name, partial(fn, params)) for name, fn in names],
        return_exceptions=True,
    )
    results: dict[str, AdapterResult] = {}
    for (name, _), item in zip(names, gathered):
        if isinstance(item, Exception):
            results[name] = AdapterResult(
                provider=name, status="error", error=str(item)
            )
        else:
            results[item.provider] = item
    elapsed_ms = (time.perf_counter() - t0) * 1000
    payload = _assemble(params, results, elapsed_ms=elapsed_ms, cache_status="MISS")
    cache.set(key, payload)
    response.headers["X-Cache"] = "MISS"
    return payload
