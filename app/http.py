"""Shared httpx.AsyncClient lifecycle for all upstream adapters."""

from __future__ import annotations

import httpx

from .config import settings

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    if _client is None:
        raise RuntimeError("HTTP client not initialized; is the app lifespan running?")
    return _client


async def startup_http_client() -> httpx.AsyncClient:
    global _client
    _client = httpx.AsyncClient(
        timeout=httpx.Timeout(settings.adapter_timeout_sec),
        limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
        headers={"User-Agent": "UPAE/0.1 (https://github.com/hcneeley/upae)"},
        follow_redirects=True,
    )
    return _client


async def shutdown_http_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
