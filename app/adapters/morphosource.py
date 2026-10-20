"""MorphoSource 3D / CT media adapter.

Fields follow MorphoSource JSON media record shape (as of 2021 field list +
current /api/media response): id, title, media_type, modality, device_facility,
physical object metadata, descriptions, part, DOI/ARK, dates.

API: https://www.morphosource.org/api/media
Docs: https://github.com/MorphoSource/morphosource-api
"""

from __future__ import annotations

from typing import Any

import httpx

from ..config import settings
from .base import AdapterResult, QueryParams

MORPHOSOURCE_MEDIA = "https://www.morphosource.org/api/media"
WEBSITE = "https://www.morphosource.org"


def _first(value: Any) -> str | None:
    """MorphoSource returns most fields as single-element arrays."""
    if value is None:
        return None
    if isinstance(value, list):
        if not value:
            return None
        item = value[0]
        return None if item is None or item == "" else str(item)
    return str(value) if value != "" else None


def _normalize_media(rec: dict[str, Any]) -> dict[str, Any]:
    mid = _first(rec.get("id"))
    return {
        "provider": "MorphoSource",
        "media_id": mid,
        "title": _first(rec.get("title")),
        "media_type": _first(rec.get("media_type")),
        "modality": _first(rec.get("modality")),
        "device_facility": _first(rec.get("device_facility")),
        "physical_object_id": _first(rec.get("physical_object_id")),
        "physical_object_title": _first(rec.get("physical_object_title")),
        "physical_object_organization": _first(rec.get("physical_object_organization")),
        "physical_object_type": _first(rec.get("physical_object_type")),
        "physical_object_taxonomy": _first(rec.get("physical_object_taxonomy_name")),
        "short_description": _first(rec.get("short_description")),
        "description": _first(rec.get("description")),
        "element_part": _first(rec.get("part")),
        "doi": _first(rec.get("doi")),
        "ark": _first(rec.get("ark")),
        "date_upload": _first(rec.get("date_uploaded") or rec.get("create_date")),
        "date_modified": _first(rec.get("date_modified")),
        "url": f"{WEBSITE}/concern/media/{mid}" if mid else None,
    }


async def fetch_and_parse(params: QueryParams) -> AdapterResult:
    if not params.taxon:
        return AdapterResult(
            provider="MORPHOSOURCE",
            status="skipped",
            error="taxon required",
            data={"records": []},
        )

    q = {
        "q": params.taxon,
        "search_field": "all_fields",
        "per_page": min(settings.occurrence_limit, 25),
        "page": 1,
    }
    async with httpx.AsyncClient(timeout=settings.adapter_timeout_sec) as client:
        resp = await client.get(MORPHOSOURCE_MEDIA, params=q)
        resp.raise_for_status()
        payload = resp.json()

    media = (payload.get("response") or {}).get("media") or []
    records = [_normalize_media(rec) for rec in media]
    return AdapterResult(provider="MORPHOSOURCE", status="ok", data={"records": records})
