"""In-memory SHA-256 keyed cache with TTL."""

from __future__ import annotations

import hashlib
import json
import time
from threading import Lock
from typing import Any

from .config import settings


def make_cache_key(
    *,
    lat: float | None,
    lng: float | None,
    radius_km: float | None,
    taxon: str | None,
    age_min: float | None,
    age_max: float | None,
) -> str:
    payload = {
        "lat": None if lat is None else round(float(lat), 6),
        "lng": None if lng is None else round(float(lng), 6),
        "radius_km": None if radius_km is None else round(float(radius_km), 3),
        "taxon": (taxon or "").strip().lower() or None,
        "age_min": age_min,
        "age_max": age_max,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class MemoryCache:
    def __init__(self, ttl_sec: int | None = None) -> None:
        self.ttl_sec = ttl_sec if ttl_sec is not None else settings.cache_ttl_sec
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = Lock()

    def get(self, key: str) -> Any | None:
        now = time.time()
        with self._lock:
            item = self._store.get(key)
            if not item:
                return None
            expires, value = item
            if expires < now:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._store[key] = (time.time() + self.ttl_sec, value)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


cache = MemoryCache()
