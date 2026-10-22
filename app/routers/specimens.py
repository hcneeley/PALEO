"""GET /api/v1/specimens — paginated specimen voucher fetch (iDigBio)."""

from __future__ import annotations

from fastapi import APIRouter, Query, Response
from pydantic import ValidationError

from ..adapters import idigbio
from ..adapters.base import QueryParams, run_adapter
from ..config import settings
from ..models.schemas import SpecimenRecord

router = APIRouter(prefix="/api/v1", tags=["specimens"])

PAGEABLE = {
    "IDIGBIO": idigbio.fetch_and_parse,
}


@router.get("/specimens")
async def specimens_page(
    response: Response,
    provider: str = Query("IDIGBIO", description="Upstream provider: IDIGBIO"),
    taxon: str | None = Query(None, description="Scientific name / taxon query"),
    offset: int = Query(0, ge=0, description="Result offset"),
    limit: int = Query(100, ge=1, le=300, description="Page size (1–300)"),
) -> dict:
    if not taxon:
        response.status_code = 400
        return {"status": "error", "detail": "Provide taxon"}

    key = (provider or "").strip().upper()
    fetch = PAGEABLE.get(key)
    if fetch is None:
        response.status_code = 422
        return {
            "status": "error",
            "detail": (
                f"Unsupported provider for specimen paging: {provider}. "
                f"Supported: {', '.join(sorted(PAGEABLE))}"
            ),
        }

    params = QueryParams(taxon=taxon, limit=limit, offset=offset)
    result = await run_adapter(key, lambda: fetch(params), timeout=settings.timeout_for(key))
    if result.status != "ok":
        response.status_code = 502 if result.status == "error" else 200
        return {
            "status": result.status,
            "provider": key,
            "detail": result.error,
            "records": [],
            "returned": 0,
            "total": None,
            "offset": offset,
            "next_offset": None,
            "has_more": False,
        }

    records: list[dict] = []
    for row in (result.data or {}).get("records") or []:
        try:
            records.append(SpecimenRecord.model_validate(row).model_dump(mode="json"))
        except ValidationError:
            continue

    total = (result.data or {}).get("total_count")
    if total is not None:
        try:
            total = int(total)
        except (TypeError, ValueError):
            total = None

    returned = len(records)
    fetched = (result.data or {}).get("fetched")
    try:
        fetched_n = int(fetched) if fetched is not None else returned
    except (TypeError, ValueError):
        fetched_n = returned

    end = bool((result.data or {}).get("end_of_records"))
    if fetched_n == 0:
        end = True

    next_offset = offset + fetched_n
    has_more = (not end) and fetched_n > 0
    if isinstance(total, int) and next_offset >= total:
        has_more = False

    return {
        "status": "success",
        "provider": key,
        "records": records,
        "returned": returned,
        "total": total,
        "offset": offset,
        "next_offset": next_offset if has_more else None,
        "has_more": has_more,
    }
