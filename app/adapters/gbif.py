"""GBIF occurrence search adapter.

Uses the public Occurrence Search API:
  GET https://api.gbif.org/v1/occurrence/search
Docs: https://techdocs.gbif.org/en/openapi/
      https://techdocs.gbif.org/en/openapi/v1/occurrence

Maps core fields into GeoJSON features for the synthesize payload.
"""

from __future__ import annotations

import httpx

from ..http import get_client

from ..config import settings
from .base import AdapterResult, QueryParams

GBIF_OCC_SEARCH = "https://api.gbif.org/v1/occurrence/search"
USER_AGENT = "UPAE/0.1 (https://github.com/hcneeley/upae; paleontology-synthesis)"


def _f(v) -> float | None:
    try:
        return float(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


async def fetch_and_parse(params: QueryParams) -> AdapterResult:
    if not params.taxon and (params.lat is None or params.lng is None):
        return AdapterResult(
            provider="GBIF",
            status="skipped",
            error="taxon and/or lat+lng required",
            data={"features": []},
        )

    q: dict = {
        "limit": min(settings.occurrence_limit, 100),
        "offset": 0,
        "hasCoordinate": "true",
    }
    if params.taxon:
        q["scientificName"] = params.taxon
    if params.lat is not None and params.lng is not None:
        # GBIF geoDistance: "lat,lng,distance" e.g. "30.2,-97.7,500km"
        r = params.radius_km or settings.default_radius_km
        q["geoDistance"] = f"{params.lat},{params.lng},{r}km"

    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    client = get_client()
    resp = await client.get(GBIF_OCC_SEARCH, params=q, headers=headers)
    resp.raise_for_status()
    payload = resp.json()

    features = []
    for rec in payload.get("results") or []:
        lat, lng = _f(rec.get("decimalLatitude")), _f(rec.get("decimalLongitude"))
        geometry = None
        if lat is not None and lng is not None:
            geometry = {"type": "Point", "coordinates": [lng, lat]}
        key = rec.get("key")
        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "occurrence_id": f"gbif:occ:{key}" if key is not None else None,
                    "database_source": "GBIF",
                    "taxon_name": rec.get("scientificName") or rec.get("species"),
                    "accepted_name": rec.get("acceptedScientificName")
                    or rec.get("scientificName"),
                    "dwc_eventDate": rec.get("eventDate") or (
                        str(rec.get("year")) if rec.get("year") else None
                    ),
                    "max_ma": None,
                    "min_ma": None,
                    "basis_of_record": rec.get("basisOfRecord"),
                    "country": rec.get("country"),
                    "dataset_key": rec.get("datasetKey"),
                    "gbif_url": (
                        f"https://www.gbif.org/occurrence/{key}" if key is not None else None
                    ),
                },
            }
        )

    return AdapterResult(
        provider="GBIF",
        status="ok",
        data={
            "features": features,
            "total_count": payload.get("count"),
        },
    )
