"""Paginated /api/v1/occurrences tests."""

from __future__ import annotations

import httpx
import respx

GBIF_URL = "https://api.gbif.org/v1/occurrence/search"
PBDB_URL = "https://paleobiodb.org/data1.2/occs/list.json"
NEOTOMA_TAXA = "https://api.neotomadb.org/v2.0/data/taxa"
NEOTOMA_OCC = "https://api.neotomadb.org/v2.0/data/occurrences"


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


@respx.mock
def test_occurrences_page_pbdb(client):
    # Full page ⇒ has_more; next_offset advances by fetched raw count.
    records = [
        {
            "oid": f"occ:{i}",
            "tna": "Canis dirus",
            "lat": 34.0,
            "lng": -118.0,
            "eag": 0.1,
            "lag": 0.01,
        }
        for i in range(3)
    ]
    respx.get(PBDB_URL).mock(return_value=httpx.Response(200, json={"records": records}))
    r = client.get(
        "/api/v1/occurrences",
        params={"provider": "PBDB", "taxon": "Canis", "offset": 0, "limit": 3},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "PBDB"
    assert body["returned"] == 3
    assert body["has_more"] is True
    assert body["next_offset"] == 3
    assert body["total"] is None


@respx.mock
def test_occurrences_pbdb_short_page_ends(client):
    respx.get(PBDB_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "records": [
                    {
                        "oid": "occ:9",
                        "tna": "Canis",
                        "lat": 1.0,
                        "lng": 2.0,
                        "eag": 1.0,
                        "lag": 0.5,
                    }
                ]
            },
        )
    )
    r = client.get(
        "/api/v1/occurrences",
        params={"provider": "PBDB", "taxon": "Canis", "offset": 10, "limit": 50},
    )
    body = r.json()
    assert body["has_more"] is False
    assert body["next_offset"] is None
    assert body["returned"] == 1


@respx.mock
def test_occurrences_page_neotoma(client):
    respx.get(NEOTOMA_TAXA).mock(
        return_value=httpx.Response(
            200,
            json={"data": [{"taxonid": 5912, "taxonname": "Canis dirus"}]},
        )
    )
    respx.get(NEOTOMA_OCC).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "occid": 100 + i,
                        "sample": {"taxonname": "Canis dirus"},
                        "age": {"ageolder": 150000, "ageyounger": 14000},
                        "site": {
                            "location": '{"type":"Point","coordinates":[-82.55,28.875]}'
                        },
                    }
                    for i in range(2)
                ]
            },
        )
    )
    r = client.get(
        "/api/v1/occurrences",
        params={"provider": "NEOTOMA", "taxon": "Canis dirus", "offset": 0, "limit": 2},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "NEOTOMA"
    assert body["returned"] == 2
    assert body["has_more"] is True
    assert body["next_offset"] == 2


def test_occurrences_bad_provider_422(client):
    r = client.get("/api/v1/occurrences", params={"provider": "MINDAT", "taxon": "x"})
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
