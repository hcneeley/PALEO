"""GET /api/v1/synthesize — federated paleontology synthesis."""

from __future__ import annotations

import asyncio
import time
from functools import partial
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Query, Request, Response
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
    NameParseBlock,
    NameParseRecord,
    TaxonomyBlock,
    TaxonomyRank,
    OccurrenceBrowseLink,
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


def _occurrence_browse_links(params: QueryParams) -> list[OccurrenceBrowseLink]:
    """Upstream portals to browse the full occurrence catalogs for this query."""
    links: list[OccurrenceBrowseLink] = []
    taxon = (params.taxon or "").strip()
    if taxon:
        links.append(
            OccurrenceBrowseLink(
                provider="PBDB",
                label="All PBDB occurrences",
                url=(
                    "https://paleobiodb.org/data1.2/occs/list.json?"
                    + urlencode(
                        {
                            "base_name": taxon,
                            "show": "coords,attr,class,paleoloc",
                            "limit": 500,
                        }
                    )
                ),
            )
        )
        links.append(
            OccurrenceBrowseLink(
                provider="GBIF",
                label="Browse all on GBIF",
                url="https://www.gbif.org/occurrence/search?"
                + urlencode({"q": taxon, "hasCoordinate": "true"}),
            )
        )
        links.append(
            OccurrenceBrowseLink(
                provider="Neotoma",
                label="Browse on Neotoma Explorer",
                url="https://apps.neotomadb.org/explorer/?"
                + urlencode({"taxonsearch": taxon}),
            )
        )
    return links


def _assemble(params: QueryParams, results: dict[str, Any], *, elapsed_ms: float, cache_status: str, view_all_url: str | None = None) -> dict:
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
    mindat_data = (mindat.data or {}) if mindat else {}
    minerals_raw = mindat_data.get("minerals") or []
    localities_raw = mindat_data.get("localities") or []
    mindat_status = mindat.status if mindat else "skipped"
    minerals_block = MineralsBlock(
        mineral_count=len(minerals_raw),
        locality_count=len(localities_raw),
        minerals=_safe_models(MineralRecord, minerals_raw),
        localities=_safe_models(MineralLocality, localities_raw),
        status=None if mindat_status == "ok" else mindat_status,
        link_mode=mindat_data.get("link_mode"),
        linked_taxon=mindat_data.get("linked_taxon") or params.taxon,
        link_lat=mindat_data.get("link_lat"),
        link_lng=mindat_data.get("link_lng"),
        link_radius_km=mindat_data.get("link_radius_km"),
    )

    gn = results.get("GNPARSER")
    gn_data = (gn.data or {}) if gn else {}
    parses_raw = gn_data.get("parses") or []
    gn_status = gn.status if gn else "skipped"
    name_parse_block = NameParseBlock(
        parse_count=len(parses_raw),
        parses=_safe_models(NameParseRecord, parses_raw),
        status=None if gn_status == "ok" else gn_status,
    )

    tax = results.get("TAXONOMY")
    tax_data = (tax.data or {}) if tax else {}
    tax_status = tax.status if tax else "skipped"
    taxonomy_block = TaxonomyBlock(
        query=tax_data.get("query") or params.taxon,
        accepted_name=tax_data.get("accepted_name"),
        scientific_name=tax_data.get("scientific_name"),
        rank=tax_data.get("rank"),
        taxonomic_status=tax_data.get("taxonomic_status"),
        confidence=tax_data.get("confidence"),
        match_type=tax_data.get("match_type"),
        hierarchy=_safe_models(TaxonomyRank, tax_data.get("hierarchy") or []),
        pbdb_hierarchy=_safe_models(TaxonomyRank, tax_data.get("pbdb_hierarchy") or []),
        gbif_usage_key=tax_data.get("gbif_usage_key"),
        gbif_url=tax_data.get("gbif_url"),
        pbdb_url=tax_data.get("pbdb_url"),
        status=None if tax_status == "ok" else tax_status,
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
        taxonomy=taxonomy_block,
        geology=geology,
        paleoclimate_proxy=paleoclimate,
        occurrences=OccurrencesBlock(
            total_records=len(features),
            features=features,
            view_all_url=view_all_url,
            browse_links=_occurrence_browse_links(params),
        ),
        specimens=specimens,
        media_3d=media,
        minerals=minerals_block,
        name_parse=name_parse_block,
        literature=literature,
        diagnostics=diagnostics,
    )
    return body.model_dump(mode="json")


@router.get("/synthesize")
async def synthesize(
    request: Request,
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
        # Refresh self-link for this host/request
        occ = dict(out.get("occurrences") or {})
        occ["view_all_url"] = str(request.url)
        out["occurrences"] = occ
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
        ("TAXONOMY", adapters.taxonomy.fetch_and_parse),
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
        ("GNPARSER", adapters.gnparser.fetch_and_parse),
    ]
    gathered = await asyncio.gather(
        *[
            run_adapter(
                name,
                partial(fn, params),
                timeout=settings.timeout_for(name),
            )
            for name, fn in names
        ],
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

    # If the query had no lat/lng but fossil occurrences do, spatially link Mindat
    # to the taxon's occurrence centroid (place bridge taxa ↔ minerals).
    mindat = results.get("MINDAT")
    need_spatial = (
        (params.lat is None or params.lng is None)
        and params.taxon
        and (
            mindat is None
            or mindat.status != "ok"
            or not (mindat.data or {}).get("minerals")
            or (mindat.data or {}).get("link_mode") == "name"
        )
    )
    if need_spatial:
        coords: list[tuple[float, float]] = []
        for src in ("PBDB", "NEOTOMA", "GBIF"):
            for feat in (results.get(src).data or {}).get("features") or [] if results.get(src) else []:
                geom = feat.get("geometry") or {}
                c = geom.get("coordinates")
                if isinstance(c, list) and len(c) >= 2:
                    try:
                        coords.append((float(c[1]), float(c[0])))
                    except (TypeError, ValueError):
                        continue
        if coords:
            clat = sum(p[0] for p in coords) / len(coords)
            clng = sum(p[1] for p in coords) / len(coords)
            spatial_params = QueryParams(
                lat=clat,
                lng=clng,
                radius_km=params.radius_km,
                taxon=params.taxon,
                age_min=params.age_min,
                age_max=params.age_max,
            )
            spatial = await run_adapter(
                "MINDAT",
                partial(adapters.mindat.fetch_spatial, spatial_params),
                timeout=settings.timeout_for("MINDAT"),
            )
            if spatial.status == "ok" and (spatial.data or {}).get("minerals"):
                results["MINDAT"] = spatial

    elapsed_ms = (time.perf_counter() - t0) * 1000
    view_all_url = str(request.url)
    payload = _assemble(
        params,
        results,
        elapsed_ms=elapsed_ms,
        cache_status="MISS",
        view_all_url=view_all_url,
    )
    cache.set(key, payload)
    response.headers["X-Cache"] = "MISS"
    return payload
