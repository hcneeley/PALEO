"""Paginated /api/v1/occurrences tests."""

from __future__ import annotations

import httpx
import respx

GBIF_URL = "https://api.gbif.org/v1/occurrence/search"


def _gbif_page(*, count: int, offset: int, results: list, end: bool = False):
    return httpx.Response(
        200,
        json={"count": count, "offset": offset, "endOfRecords": end, "results": results},
    )


@respx.mock
def test_occurrences_page_gbif(client):
    respx.get(GBIF_URL).mock(
        return_value=_gbif_page(
            count=500,
            offset=50,
            end=False,
            results=[
                {
                    "key": 222,
                    "scientificName": "Hadrosaurus foulkii",
                    "acceptedScientificName": "Hadrosaurus foulkii",
                    "decimalLatitude": 34.1,
                    "decimalLongitude": -78.2,
                }
            ],
        )
    )
    r = client.get(
        "/api/v1/occurrences",
        params={"provider": "GBIF", "taxon": "Hadrosaurus", "offset": 50, "limit": 100},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert body["provider"] == "GBIF"
    assert body["returned"] == 1
    assert body["total"] == 500
    assert body["offset"] == 50
    assert body["next_offset"] == 51
    assert body["has_more"] is True
    assert body["features"][0]["properties"]["database_source"] == "GBIF"


@respx.mock
def test_occurrences_end_of_records(client):
    respx.get(GBIF_URL).mock(
        return_value=_gbif_page(
            count=2,
            offset=1,
            end=True,
            results=[
                {
                    "key": 3,
                    "scientificName": "Hadrosaurus",
                    "decimalLatitude": 1.0,
                    "decimalLongitude": 2.0,
                }
            ],
        )
    )
    r = client.get(
        "/api/v1/occurrences",
        params={"provider": "GBIF", "taxon": "Hadrosaurus", "offset": 1, "limit": 50},
    )
    body = r.json()
    assert body["has_more"] is False
    assert body["next_offset"] is None


def test_occurrences_bad_provider_422(client):
    r = client.get("/api/v1/occurrences", params={"provider": "PBDB", "taxon": "x"})
    assert r.status_code == 422


def test_occurrences_missing_query_400(client):
    r = client.get("/api/v1/occurrences", params={"provider": "GBIF"})
    assert r.status_code == 400


def test_occurrences_limit_out_of_range_422(client):
    r = client.get(
        "/api/v1/occurrences",
        params={"provider": "GBIF", "taxon": "x", "limit": 301},
    )
    assert r.status_code == 422
