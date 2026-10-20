"""Crossref works search adapter.

Docs: https://www.crossref.org/documentation/retrieve-metadata/rest-api/
Endpoint: GET https://api.crossref.org/works

Uses the polite pool via mailto= when CROSSREF_MAILTO is set (recommended).
"""

from __future__ import annotations

import html
import os
import re
from typing import Any

import httpx

from ..config import settings
from .base import AdapterResult, QueryParams

CROSSREF_WORKS = "https://api.crossref.org/works"
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str | None) -> str | None:
    if not text:
        return None
    return html.unescape(_TAG_RE.sub("", text)).strip() or None


def _year_from_parts(item: dict[str, Any]) -> int | None:
    for key in ("published-print", "published-online", "created", "issued"):
        parts = (item.get(key) or {}).get("date-parts") or []
        if parts and parts[0]:
            try:
                return int(parts[0][0])
            except (TypeError, ValueError, IndexError):
                continue
    return None


def _authors(item: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for a in item.get("author") or []:
        given = (a.get("given") or "").strip()
        family = (a.get("family") or "").strip()
        name = (a.get("name") or "").strip()
        if family and given:
            out.append(f"{given} {family}")
        elif family:
            out.append(family)
        elif name:
            out.append(name)
    return out


def _normalize(item: dict[str, Any]) -> dict[str, Any]:
    titles = item.get("title") or []
    containers = item.get("container-title") or []
    doi = item.get("DOI")
    return {
        "doi": doi,
        "title": _strip_html(titles[0] if titles else None),
        "authors": _authors(item),
        "year": _year_from_parts(item),
        "container_title": _strip_html(containers[0] if containers else None),
        "type": item.get("type"),
        "url": item.get("URL") or (f"https://doi.org/{doi}" if doi else None),
    }


async def fetch_and_parse(params: QueryParams) -> AdapterResult:
    if not params.taxon:
        return AdapterResult(
            provider="CROSSREF",
            status="skipped",
            error="taxon required",
            data={"literature": []},
        )

    mailto = (os.environ.get("CROSSREF_MAILTO") or "").strip()
    q: dict[str, Any] = {
        "query": params.taxon,
        "rows": min(settings.occurrence_limit, 20),
        "select": "DOI,title,author,published-print,published-online,created,issued,container-title,type,URL",
        # Prefer journal articles over supplemental components
        "filter": "type:journal-article",
    }
    if mailto:
        q["mailto"] = mailto

    headers = {
        "Accept": "application/json",
        "User-Agent": f"UPAE/0.1 (https://github.com/hcneeley/upae; mailto:{mailto or 'hcneeley@icloud.com'})",
    }
    async with httpx.AsyncClient(timeout=settings.adapter_timeout_sec, headers=headers) as client:
        resp = await client.get(CROSSREF_WORKS, params=q)
        resp.raise_for_status()
        payload = resp.json()

    message = payload.get("message") or {}
    items = message.get("items") or []
    literature = [_normalize(it) for it in items]
    return AdapterResult(
        provider="CROSSREF",
        status="ok",
        data={
            "literature": literature,
            "total_results": message.get("total-results"),
        },
    )
