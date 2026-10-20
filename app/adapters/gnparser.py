"""Global Names Parser (GNparser) adapter.

Docs: https://parser.globalnames.org/doc/api
API: GET/POST https://parser.globalnames.org/api/v1/

Parses the query taxon into canonical form, rank, authorship, etc.
Related: https://globalnames.org/ · ZooBank registry via Global Names apps.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from ..http import get_client
from .base import AdapterResult, QueryParams

GNPARSER_API = "https://parser.globalnames.org/api/v1/"


def _normalize(row: dict[str, Any]) -> dict[str, Any]:
    canonical = row.get("canonical") or {}
    authorship = row.get("authorship") or {}
    details = row.get("details") or []
    genus = species = infraspecies = None
    # details is often a list of rank dicts; keep common fields if present
    if isinstance(details, list):
        for block in details:
            if not isinstance(block, dict):
                continue
            if "genus" in block and isinstance(block["genus"], dict):
                genus = block["genus"].get("value")
            if "species" in block and isinstance(block["species"], dict):
                species = block["species"].get("value")
            if "infraspecies" in block and isinstance(block["infraspecies"], list):
                parts = [
                    p.get("value")
                    for p in block["infraspecies"]
                    if isinstance(p, dict) and p.get("value")
                ]
                infraspecies = " ".join(parts) if parts else None

    # Fallback: split simple canonical
    simple = canonical.get("simple") if isinstance(canonical, dict) else None
    if not genus and isinstance(simple, str) and simple.strip():
        bits = simple.split()
        genus = bits[0] if bits else None
        species = bits[1] if len(bits) > 1 else None

    return {
        "provider": "GNparser",
        "parsed": bool(row.get("parsed")),
        "quality": row.get("quality"),
        "verbatim": row.get("verbatim"),
        "normalized": row.get("normalized"),
        "canonical_simple": (canonical or {}).get("simple") if isinstance(canonical, dict) else None,
        "canonical_full": (canonical or {}).get("full") if isinstance(canonical, dict) else None,
        "canonical_stemmed": (canonical or {}).get("stemmed") if isinstance(canonical, dict) else None,
        "cardinality": row.get("cardinality"),
        "rank": row.get("rank"),
        "genus": genus,
        "species": species,
        "infraspecies": infraspecies,
        "authorship_verbatim": authorship.get("verbatim") if isinstance(authorship, dict) else None,
        "authorship_normalized": authorship.get("normalized") if isinstance(authorship, dict) else None,
        "authorship_year": authorship.get("year") if isinstance(authorship, dict) else None,
        "authors": list(authorship.get("authors") or []) if isinstance(authorship, dict) else [],
        "name_id": row.get("id"),
        "parser_version": row.get("parserVersion"),
        "url": f"https://parser.globalnames.org/?q={quote(str(row.get('verbatim') or ''))}",
    }


async def fetch_and_parse(params: QueryParams) -> AdapterResult:
    if not params.taxon:
        return AdapterResult(
            provider="GNPARSER",
            status="skipped",
            error="taxon required",
            data={"parses": []},
        )

    client = get_client()
    # GET path encodes the name; spaces as +
    path = quote(params.taxon.strip(), safe="")
    # quote uses %20; GNparser docs prefer + for spaces
    path = path.replace("%20", "+")
    resp = await client.get(
        GNPARSER_API + path,
        headers={"Accept": "application/json"},
    )
    resp.raise_for_status()
    payload = resp.json()
    rows = payload if isinstance(payload, list) else [payload]
    parses = [_normalize(r) for r in rows if isinstance(r, dict)]
    return AdapterResult(
        provider="GNPARSER",
        status="ok",
        data={"parses": parses, "records": parses},
    )
