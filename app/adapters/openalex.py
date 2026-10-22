"""OpenAlex works search adapter.

Docs: https://docs.openalex.org/api-entities/works/search-works
Endpoint: GET https://api.openalex.org/works

Polite use: set OPENALEX_MAILTO (or CROSSREF_MAILTO). Optional OPENALEX_API_KEY
raises the shared IP budget (https://openalex.org/settings/api).
"""

from __future__ import annotations

import os
import re
from typing import Any

import httpx

from ..http import get_client

from .base import AdapterResult, QueryParams

OPENALEX_WORKS = "https://api.openalex.org/works"
_DOI_RE = re.compile(r"^https?://(dx\.)?doi\.org/", re.I)


def _bare_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    return _DOI_RE.sub("", doi.strip()).strip() or None


def _authors(work: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for row in work.get("authorships") or []:
        name = ((row.get("author") or {}).get("display_name") or "").strip()
        if name:
            out.append(name)
    return out


def _container(work: dict[str, Any]) -> str | None:
    loc = work.get("primary_location") or {}
    source = loc.get("source") or {}
    name = source.get("display_name")
    return name.strip() if isinstance(name, str) and name.strip() else None


def _normalize(work: dict[str, Any]) -> dict[str, Any]:
    doi = _bare_doi(work.get("doi"))
    title = work.get("display_name") or work.get("title")
    oa_url = (work.get("primary_location") or {}).get("landing_page_url")
    return {
        "provider": "OpenAlex",
        "doi": doi,
        "title": title.strip() if isinstance(title, str) else title,
        "authors": _authors(work),
        "year": work.get("publication_year"),
        "container_title": _container(work),
        "type": work.get("type"),
        "url": oa_url or (f"https://doi.org/{doi}" if doi else work.get("id")),
        "cited_by_count": work.get("cited_by_count"),
    }


async def fetch_and_parse(params: QueryParams) -> AdapterResult:
    if not params.taxon:
        return AdapterResult(
            provider="OPENALEX",
            status="skipped",
            error="taxon required",
            data={"literature": []},
        )

    mailto = (
        (os.environ.get("OPENALEX_MAILTO") or "").strip()
        or (os.environ.get("CROSSREF_MAILTO") or "").strip()
    )
    api_key = (os.environ.get("OPENALEX_API_KEY") or "").strip()
    q: dict[str, Any] = {
        "search": params.taxon,
        "per_page": min(params.result_limit(), 25),
        # OR values for one field: type:article|review (not type:article|type:review)
        "filter": "type:article|review",
    }
    if mailto:
        q["mailto"] = mailto
    if api_key:
        q["api_key"] = api_key

    ua = "UPAE/0.1 (https://github.com/hcneeley/upae)"
    if mailto:
        ua = f"{ua}; mailto:{mailto}"
    headers = {
        "Accept": "application/json",
        "User-Agent": ua,
    }
    client = get_client()
    resp = await client.get(OPENALEX_WORKS, params=q, headers=headers)
    resp.raise_for_status()
    payload = resp.json()

    results = payload.get("results") or []
    literature = [_normalize(w) for w in results]
    meta = payload.get("meta") or {}
    return AdapterResult(
        provider="OPENALEX",
        status="ok",
        data={
            "literature": literature,
            "total_results": meta.get("count"),
        },
    )
