"""iDigBio specimen voucher adapter."""

from __future__ import annotations

import json

import httpx

from ..http import get_client

from .base import AdapterResult, QueryParams

IDIGBIO_SEARCH = "https://search.idigbio.org/v2/search/records"


async def fetch_and_parse(params: QueryParams) -> AdapterResult:
    if not params.taxon:
        return AdapterResult(
            provider="IDIGBIO",
            status="skipped",
            error="taxon required",
            data={"records": []},
        )

    taxon = params.taxon.strip()
    if " " in taxon:
        rq: dict = {"scientificname": taxon}
    else:
        rq = {"genus": taxon}

    q = {
        "rq": json.dumps(rq),
        "limit": min(params.result_limit(), 100),
        "offset": 0,
    }
    client = get_client()
    resp = await client.get(IDIGBIO_SEARCH, params=q)
    resp.raise_for_status()
    payload = resp.json()

    records = []
    for item in payload.get("items") or []:
        idx = item.get("indexTerms") or {}
        data = item.get("data") or {}
        uuid = item.get("uuid") or idx.get("uuid")
        sci = (
            data.get("dwc:scientificName")
            or idx.get("canonicalname")
            or idx.get("scientificname")
            or data.get("dwc:genus")
        )
        records.append(
            {
                "provider": "iDigBio",
                "institution_code": data.get("dwc:institutionCode")
                or idx.get("institutioncode"),
                "catalog_number": data.get("dwc:catalogNumber")
                or idx.get("catalognumber"),
                "scientific_name": sci,
                "epandda_matched": False,
                "uuid": uuid,
                "url": (
                    f"https://www.idigbio.org/portal/records/{uuid}" if uuid else None
                ),
            }
        )

    return AdapterResult(provider="IDIGBIO", status="ok", data={"records": records})
