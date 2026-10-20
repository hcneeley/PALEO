"""Synthesize endpoint tests with mocked upstream HTTP."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.adapters.base import AdapterResult, QueryParams
from app.cache import cache


PBDB_URL = "https://paleobiodb.org/data1.2/occs/list.json"
MACRO_URL = "https://macrostrat.org/api/v2/units"
NEOTOMA_TAXA = "https://api.neotomadb.org/v2.0/data/taxa"
NEOTOMA_OCC = "https://api.neotomadb.org/v2.0/data/occurrences"
IDIG_URL = "https://search.idigbio.org/v2/search/records"
MS_URL = "https://www.morphosource.org/api/media"
GBIF_URL = "https://api.gbif.org/v1/occurrence/search"


def _mock_live_upstreams(router: respx.MockRouter) -> None:
    router.get(PBDB_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "records": [
                    {
                        "oid": "occ:1",
                        "tna": "Hadrosaurus foulkii",
                        "lat": 34.55,
                        "lng": -78.45,
                        "eag": 83.6,
                        "lag": 72.1,
                    }
                ]
            },
        )
    )
    router.get(MACRO_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "success": {
                    "data": [
                        {
                            "unit_id": 1,
                            "unit_name": "Austin Chalk",
                            "strat_name_long": "Austin Chalk",
                            "b_age": 89.8,
                            "t_age": 83.6,
                            "lith": [{"name": "chalk", "prop": 1}],
                            "environ": [{"name": "shallow marine"}],
                        }
                    ]
                }
            },
        )
    )
    router.get(NEOTOMA_TAXA).mock(
        return_value=httpx.Response(200, json={"data": [{"taxonid": 99}]})
    )
    router.get(NEOTOMA_OCC).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "occurrenceid": 7,
                        "taxon": {"taxonname": "Hadrosaurus"},
                        "site": {"latitude": 40.0, "longitude": -75.0},
                    }
                ]
            },
        )
    )
    router.get(IDIG_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {
                        "uuid": "abc-123",
                        "data": {
                            "dwc:institutionCode": "TMM",
                            "dwc:catalogNumber": "40001",
                            "dwc:scientificName": "Hadrosaurus",
                        },
                        "indexTerms": {},
                    }
                ]
            },
        )
    )
    router.get(MS_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "response": {
                    "media": [
                        {
                            "id": ["000852930"],
                            "title": ["Jaw [CTImageSeries] [CT]"],
                            "media_type": ["Volumetric Image Series"],
                            "modality": ["MicroNanoXRayComputedTomography"],
                            "device_facility": ["AMNH Microscopy and Imaging Facility (MIF)"],
                            "physical_object_id": ["000852927"],
                            "physical_object_title": ["pss-mae:MAE:19-46"],
                            "physical_object_organization": ["AMNH"],
                            "physical_object_type": ["Biological Specimen"],
                            "physical_object_taxonomy_name": ["Hadrosaurus sp"],
                            "part": ["Jaw"],
                            "doi": [],
                            "ark": [],
                        }
                    ],
                    "pages": {"total_count": 1},
                }
            },
        )
    )
    router.get(GBIF_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "count": 1,
                "results": [
                    {
                        "key": 111,
                        "scientificName": "Hadrosaurus foulkii",
                        "acceptedScientificName": "Hadrosaurus foulkii",
                        "decimalLatitude": 34.55,
                        "decimalLongitude": -78.45,
                        "eventDate": "2020-01-01",
                        "basisOfRecord": "PRESERVED_SPECIMEN",
                        "country": "United States of America",
                        "datasetKey": "abc",
                    }
                ],
            },
        )
    )


@respx.mock
def test_synthesize_happy_path(client):
    _mock_live_upstreams(respx)
    r = client.get(
        "/api/v1/synthesize",
        params={"taxon": "Hadrosaurus", "lat": 34.55, "lng": -78.45, "radius_km": 50},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert body["cache_status"] == "MISS"
    assert r.headers.get("X-Cache") == "MISS"
    assert body["geology"]["macrostrat_units"][0]["unit_name"] == "Austin Chalk"
    assert body["occurrences"]["total_records"] >= 1
    assert body["specimens"]["voucher_count"] == 1
    providers = {d["provider"]: d["status"] for d in body["diagnostics"]}
    assert providers["PBDB"] == "ok"
    assert providers["MORPHOSOURCE"] == "ok"
    assert body["media_3d"]["has_3d_assets"] is True
    assert body["media_3d"]["records"][0]["media_id"] == "000852930"
    assert body["media_3d"]["records"][0]["physical_object_taxonomy"] == "Hadrosaurus sp"
    assert providers["GBIF"] == "ok"
    assert any(
        f["properties"]["database_source"] == "GBIF"
        for f in body["occurrences"]["features"]
    )


@respx.mock
def test_adapter_failure_still_200(client):
    respx.get(PBDB_URL).mock(return_value=httpx.Response(500, text="boom"))
    respx.get(MACRO_URL).mock(
        return_value=httpx.Response(200, json={"success": {"data": []}})
    )
    respx.get(NEOTOMA_TAXA).mock(return_value=httpx.Response(200, json={"data": []}))
    respx.get(IDIG_URL).mock(return_value=httpx.Response(200, json={"items": []}))
    respx.get(MS_URL).mock(
        return_value=httpx.Response(200, json={"response": {"media": [], "pages": {}}})
    )
    respx.get(GBIF_URL).mock(
        return_value=httpx.Response(200, json={"count": 0, "results": []})
    )

    r = client.get("/api/v1/synthesize", params={"taxon": "Hadrosaurus", "lat": 1, "lng": 2})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    pbdb = next(d for d in body["diagnostics"] if d["provider"] == "PBDB")
    assert pbdb["status"] == "error"
    assert body["occurrences"]["total_records"] == 0


@respx.mock
def test_cache_hit(client):
    _mock_live_upstreams(respx)
    params = {"taxon": "Hadrosaurus", "lat": 34.55, "lng": -78.45}
    r1 = client.get("/api/v1/synthesize", params=params)
    assert r1.headers.get("X-Cache") == "MISS"
    r2 = client.get("/api/v1/synthesize", params=params)
    assert r2.status_code == 200
    assert r2.headers.get("X-Cache") == "HIT"
    assert r2.json()["cache_status"] == "HIT"


def test_missing_params_400(client):
    r = client.get("/api/v1/synthesize")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_run_adapter_timeout():
    from app.adapters.base import run_adapter

    async def slow():
        import asyncio

        await asyncio.sleep(10)
        return AdapterResult(provider="X", status="ok")

    result = await run_adapter("X", slow, timeout=0.05)
    assert result.status == "error"
    assert "timeout" in (result.error or "")
