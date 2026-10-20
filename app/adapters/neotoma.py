"""Neotoma paleoecology adapter (sites / occurrences by taxon)."""

from __future__ import annotations

import httpx

from ..http import get_client

from ..config import settings
from .base import AdapterResult, QueryParams

NEOTOMA_BASE = "https://api.neotomadb.org/v2.0/data/"


def _f(v) -> float | None:
    try:
        return float(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


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
    taxa = (taxa_resp.json().get("data") or [])
    taxon_ids = [int(t["taxonid"]) for t in taxa if t.get("taxonid") is not None]
    if not taxon_ids:
        return AdapterResult(
            provider="NEOTOMA",
            status="ok",
            data={"features": []},
        )

    features = []
    remaining = settings.occurrence_limit
    for tid in taxon_ids:
        if remaining <= 0:
            break
        occ_resp = await client.get(
            NEOTOMA_BASE + "occurrences",
            params={"taxonid": tid, "limit": remaining},
        )
        occ_resp.raise_for_status()
        for rec in occ_resp.json().get("data") or []:
            sample = rec.get("sample") or {}
            site = rec.get("site") or {}
            lat = _f(site.get("latitude") or sample.get("latitude"))
            lng = _f(site.get("longitude") or sample.get("longitude"))
            geometry = None
            if lat is not None and lng is not None:
                geometry = {"type": "Point", "coordinates": [lng, lat]}
            oid = rec.get("occurrenceid") or rec.get("sampleid")
            name = (
                (rec.get("taxon") or {}).get("taxonname")
                if isinstance(rec.get("taxon"), dict)
                else params.taxon
            )
            features.append(
                {
                    "type": "Feature",
                    "geometry": geometry,
                    "properties": {
                        "occurrence_id": f"neotoma:occ:{oid}" if oid else None,
                        "database_source": "NEOTOMA",
                        "taxon_name": name,
                        "accepted_name": name,
                        "dwc_eventDate": None,
                        "max_ma": None,
                        "min_ma": None,
                    },
                }
            )
            remaining = settings.occurrence_limit - len(features)

    return AdapterResult(provider="NEOTOMA", status="ok", data={"features": features})
