"""Shared adapter types and safe runner."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

from ..config import settings
from ..models.schemas import AdapterDiagnostic


@dataclass
class QueryParams:
    lat: float | None = None
    lng: float | None = None
    radius_km: float = 10.0
    taxon: str | None = None
    age_min: float | None = None
    age_max: float | None = None
    limit: int | None = None
    offset: int = 0

    def result_limit(self) -> int:
        """Per-source page size for this request (clamped 1–300)."""
        n = self.limit if self.limit is not None else settings.occurrence_limit
        return max(1, min(int(n), 300))

    def result_offset(self) -> int:
        return max(0, int(self.offset or 0))


@dataclass
class AdapterResult:
    provider: str
    status: str = "ok"  # ok | error | stub | skipped
    error: str | None = None
    elapsed_ms: float = 0.0
    data: dict[str, Any] = field(default_factory=dict)

    def diagnostic(self) -> AdapterDiagnostic:
        # Prefer upstream catalog totals over the capped page currently in hand.
        if self.status in ("waiting", "skipped", "error"):
            count = 0
        else:
            total = self.data.get("total_count")
            if total is None:
                total = self.data.get("total_results")
            if total is not None:
                try:
                    count = int(total)
                except (TypeError, ValueError):
                    count = 0
            elif "features" in self.data:
                count = len(self.data.get("features") or [])
            elif "units" in self.data:
                count = len(self.data.get("units") or [])
            elif "literature" in self.data:
                count = len(self.data.get("literature") or [])
            elif "hierarchy" in self.data:
                count = len(self.data.get("hierarchy") or [])
            elif "parses" in self.data:
                count = len(self.data.get("parses") or [])
            elif "minerals" in self.data:
                count = len(self.data.get("minerals") or []) + len(
                    self.data.get("localities") or []
                )
            elif "records" in self.data and "hierarchy" not in self.data:
                # Specimen / media style payloads (avoid taxonomy's alias "records").
                count = len(self.data.get("records") or [])
            elif isinstance(self.data.get("proxy"), dict):
                count = int((self.data["proxy"] or {}).get("study_count") or 0)
            else:
                count = 0
        return AdapterDiagnostic(
            provider=self.provider,
            status=self.status,
            error=self.error,
            record_count=count,
            elapsed_ms=round(self.elapsed_ms, 2),
        )


class Adapter(Protocol):
    name: str

    async def fetch_and_parse(self, params: QueryParams) -> AdapterResult: ...


async def run_adapter(
    name: str,
    coro_factory: Callable[[], Awaitable[AdapterResult]],
    timeout: float | None = None,
) -> AdapterResult:
    """Run an adapter with hard timeout and error isolation."""
    limit = timeout if timeout is not None else settings.adapter_timeout_sec
    t0 = time.perf_counter()
    try:
        result = await asyncio.wait_for(coro_factory(), timeout=limit)
        result.elapsed_ms = (time.perf_counter() - t0) * 1000
        return result
    except asyncio.TimeoutError:
        return AdapterResult(
            provider=name,
            status="error",
            error=f"timeout after {limit}s",
            elapsed_ms=(time.perf_counter() - t0) * 1000,
        )
    except Exception as exc:  # noqa: BLE001 — isolate upstream failures
        return AdapterResult(
            provider=name,
            status="error",
            error=str(exc),
            elapsed_ms=(time.perf_counter() - t0) * 1000,
        )
