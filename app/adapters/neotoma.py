"""Neotoma paleoecology adapter (sites / occurrences by taxon)."""

from __future__ import annotations

import json

import httpx

from ..http import get_client

from .base import AdapterResult, QueryParams

NEOTOMA_BASE = "https://api.neotomadb.org/v2.0/data/"


def _f(v) -> float | None:
    try:
        return float(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


def _coords_from_site(site: dict) -> tuple[float | None, float | None]:
    """Neotoma v2 sites expose WGS84 as a GeoJSON string in ``location``."""
    lat = _f(site.get("latitude"))
    lng = _f(site.get("longitude"))
    if lat is not None and lng is not None:
        return lat, lng
    raw = site.get("location")
    if not raw:
        return None, None
    try:
        geom = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError, json.JSONDecodeError):
        return None, None
    if not isinstance(geom, dict):
        return None, None
    coords = geom.get("coordinates")
    if not isinstance(coords, (list, tuple)) or len(coords) < 2:
        return None, None
    lng_f, lat_f = _f(coords[0]), _f(coords[1])
    return lat_f, lng_f


def _ma_from_years_bp(years: float | None) -> float | None:
    if years is None:
        return None
    try:
        y = float(years)
    except (TypeError, ValueError):
        return None
    if y < 0:
        return None
    return round(y / 1_000_000.0, 6)


async def fetch_and_parse(params: QueryParams) -> AdapterResult:
    if not params.taxon:
        return AdapterResult(
            provider="NEOTOMA",
            status="skipped",
            error="taxon required",
            data={"features": []},
        )

    client = get_client()
    taxa_resp = await client.get(
        NEOTOMA_BASE + "taxa",
        params={"taxonname": params.taxon, "lower": "true"},
    )
    taxa_resp.raise_for_status()
    taxa = taxa_resp.json().get("data") or []
    taxon_ids = [int(t["taxonid"]) for t in taxa if t.get("taxonid") is not None]
    if not taxon_ids:
        return AdapterResult(
            provider="NEOTOMA",
            status="ok",
            data={"features": []},
        )

    features = []
    remaining = params.result_limit()
    for tid in taxon_ids:
        if remaining <= 0:
            break
        occ_resp = await client.get(
            NEOTOMA_BASE + "occurrences",
            params={"taxonid": tid, "limit": remaining},
        )
        occ_resp.raise_for_status()
        for rec in occ_resp.json().get("data") or []:
            if not isinstance(rec, dict):
                continue
            sample = rec.get("sample") or {}
            site = rec.get("site") or {}
            age = rec.get("age") or {}
            if not isinstance(sample, dict):
                sample = {}
            if not isinstance(site, dict):
                site = {}
            if not isinstance(age, dict):
                age = {}

            lat, lng = _coords_from_site(site)
            oid = rec.get("occid") or rec.get("occurrenceid") or rec.get("sampleid")
            name = sample.get("taxonname") or params.taxon
            # Skip hollow rows (no id and no place) — they render as blank table lines.
            if oid is None and lat is None and lng is None:
                continue
            if lat is None or lng is None:
                # Occurrences without coordinates are not useful on the map/table.
                continue

            geometry = {"type": "Point", "coordinates": [lng, lat]}
            older_ma = _ma_from_years_bp(age.get("ageolder"))
            younger_ma = _ma_from_years_bp(age.get("ageyounger"))
            if older_ma is None and younger_ma is None:
                older_ma = younger_ma = _ma_from_years_bp(age.get("age"))

            features.append(
                {
                    "type": "Feature",
                    "geometry": geometry,
                    "properties": {
                        "occurrence_id": f"neotoma:occ:{oid}" if oid is not None else None,
                        "database_source": "NEOTOMA",
                        "taxon_name": name,
                        "accepted_name": name,
                        "dwc_eventDate": None,
                        "max_ma": older_ma,
                        "min_ma": younger_ma,
                    },
                }
            )
            remaining = params.result_limit() - len(features)

    return AdapterResult(provider="NEOTOMA", status="ok", data={"features": features})
