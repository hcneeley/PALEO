"""Paginated /api/v1/specimens tests (iDigBio)."""

from __future__ import annotations

import httpx
import respx

IDIG_URL = "https://search.idigbio.org/v2/search/records"


def _idig_page(*, item_count: int, items: list):
    return httpx.Response(200, json={"itemCount": item_count, "items": items})


@respx.mock
def test_specimens_page_idigbio(client):
    respx.get(IDIG_URL).mock(
        return_value=_idig_page(
            item_count=250,
            items=[
                {
                    "uuid": "abc-1",
                    "data": {
                        "dwc:institutionCode": "TMM",
                        "dwc:catalogNumber": "1",
                        "dwc:scientificName": "Hadrosaurus",
                    },
                    "indexTerms": {},
                },
                {
                    "uuid": "abc-2",
                    "data": {
                        "dwc:institutionCode": "AMNH",
                        "dwc:catalogNumber": "2",
                        "dwc:scientificName": "Hadrosaurus foulkii",
                    },
                    "indexTerms": {},
                },
            ],
        )
    )
    r = client.get(
        "/api/v1/specimens",
        params={"provider": "IDIGBIO", "taxon": "Hadrosaurus", "offset": 0, "limit": 2},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert body["provider"] == "IDIGBIO"
    assert body["returned"] == 2
    assert body["total"] == 250
    assert body["has_more"] is True
    assert body["next_offset"] == 2
    assert body["records"][0]["uuid"] == "abc-1"


@respx.mock
def test_specimens_end_of_records(client):
    respx.get(IDIG_URL).mock(
        return_value=_idig_page(
            item_count=3,
            items=[
                {
                    "uuid": "last",
                    "data": {"dwc:scientificName": "Hadrosaurus"},
                    "indexTerms": {},
                }
            ],
        )
    )
    r = client.get(
        "/api/v1/specimens",
        params={"provider": "IDIGBIO", "taxon": "Hadrosaurus", "offset": 2, "limit": 50},
    )
    body = r.json()
    assert body["has_more"] is False
    assert body["next_offset"] is None


def test_specimens_missing_taxon_400(client):
    r = client.get("/api/v1/specimens", params={"provider": "IDIGBIO"})
    assert r.status_code == 400


def test_specimens_bad_provider_422(client):
    r = client.get("/api/v1/specimens", params={"provider": "GBIF", "taxon": "x"})
    assert r.status_code == 422
