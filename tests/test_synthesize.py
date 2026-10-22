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
NOAA_URL = "https://www.ncei.noaa.gov/access/paleo-search/study/search.json"
CROSSREF_URL = "https://api.crossref.org/works"
OPENALEX_URL = "https://api.openalex.org/works"
MINDAT_SEARCH = "https://api.mindat.org/v1/geomaterials-search/"
MINDAT_DETAIL = "https://api.mindat.org/v1/geomaterials/1/"
MINDAT_LOCS = "https://api.mindat.org/v1/localities/"
GNPARSER_URL = "https://parser.globalnames.org/api/v1/"
GBIF_MATCH = "https://api.gbif.org/v1/species/match"
PBDB_TAXA = "https://paleobiodb.org/data1.2/taxa/single.json"


def _mock_live_upstreams(router: respx.MockRouter) -> None:

    router.get(GBIF_MATCH).mock(
        return_value=httpx.Response(
            200,
            json={
                "usageKey": 99,
                "scientificName": "Hadrosaurus foulkii",
                "canonicalName": "Hadrosaurus foulkii",
                "rank": "SPECIES",
                "status": "ACCEPTED",
                "confidence": 95,
                "matchType": "EXACT",
                "kingdom": "Animalia",
                "phylum": "Chordata",
                "class": "Reptilia",
                "order": "Ornithischia",
                "family": "Hadrosauridae",
                "genus": "Hadrosaurus",
                "species": "Hadrosaurus foulkii",
            },
        )
    )
    router.get("https://api.gbif.org/v1/species/99/parents").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"rank": "KINGDOM", "canonicalName": "Animalia", "key": 1},
                {"rank": "PHYLUM", "canonicalName": "Chordata", "key": 44},
                {"rank": "CLASS", "canonicalName": "Reptilia", "key": 358},
                {"rank": "ORDER", "canonicalName": "Ornithischia", "key": 1},
                {"rank": "FAMILY", "canonicalName": "Hadrosauridae", "key": 2},
                {"rank": "GENUS", "canonicalName": "Hadrosaurus", "key": 3},
            ],
        )
    )
    router.get("https://api.gbif.org/v1/species/99").mock(
        return_value=httpx.Response(
            200,
            json={
                "key": 99,
                "canonicalName": "Hadrosaurus foulkii",
                "scientificName": "Hadrosaurus foulkii Leidy, 1858",
                "rank": "SPECIES",
                "taxonomicStatus": "ACCEPTED",
            },
        )
    )
    router.get(PBDB_TAXA).mock(
        return_value=httpx.Response(
            200,
            json={
                "records": [
                    {
                        "oid": "txn:1",
                        "nam": "Hadrosaurus foulkii",
                        "acn": "Hadrosaurus foulkii",
                        "att": "Leidy 1858",
                        "kgl": "Animalia",
                        "phl": "Chordata",
                        "cll": "Osteichthyes",
                        "odl": "Ornithischia",
                        "fml": "Hadrosauridae",
                        "gnl": "Hadrosaurus",
                    }
                ]
            },
        )
    )
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
                        "pla": 30.1,
                        "pln": -75.2,
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
                "endOfRecords": True,
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
    router.get(NOAA_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "study": [
                    {
                        "xmlId": 9101,
                        "NOAAStudyId": 10437,
                        "studyName": "Example climate reconstruction",
                        "doi": "https://doi.org/10.25921/example",
                        "dataPublisher": "NOAA",
                        "dataType": ["CLIMATE RECONSTRUCTIONS"],
                        "investigators": "Doe, J.",
                        "site": [
                            {
                                "siteName": "Test Site",
                                "geo": {
                                    "geometry": {"type": "Point", "coordinates": [34.55, -78.45]},
                                    "properties": {},
                                },
                            }
                        ],
                    }
                ],
                "page": [],
            },
        )
    )
    router.get(CROSSREF_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "ok",
                "message": {
                    "total-results": 1,
                    "items": [
                        {
                            "DOI": "10.1234/example",
                            "title": ["Dire wolves and <i>Canis dirus</i>"],
                            "author": [{"given": "Jane", "family": "Doe"}],
                            "published-print": {"date-parts": [[2020, 1, 1]]},
                            "container-title": ["Journal of Example"],
                            "type": "journal-article",
                            "URL": "https://doi.org/10.1234/example",
                        }
                    ],
                },
            },
        )
    )
    router.get(OPENALEX_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "meta": {"count": 1},
                "results": [
                    {
                        "id": "https://openalex.org/W1",
                        "doi": "https://doi.org/10.9999/openalex",
                        "display_name": "OpenAlex paper on Hadrosaurus",
                        "publication_year": 2021,
                        "type": "article",
                        "cited_by_count": 12,
                        "authorships": [
                            {"author": {"display_name": "Alex Author"}}
                        ],
                        "primary_location": {
                            "landing_page_url": "https://doi.org/10.9999/openalex",
                            "source": {"display_name": "Paleo Journal"},
                        },
                    }
                ],
            },
        )
    )
    router.post("https://api.mindat.org/v1/geomin-point/").mock(
        return_value=httpx.Response(200, json={"1": [10, 11]})
    )
    router.post("https://api.mindat.org/v1/geoloc-point/").mock(
        return_value=httpx.Response(200, json=[10, 11])
    )
    router.get(url__regex=r"https://api\.mindat\.org/v1/geomaterials/\d+/").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 1,
                "name": "Quartz",
                "mindat_formula": "SiO2",
                "csystem": "Hexagonal",
                "hmin": 7,
                "hmax": 7,
                "ima_status": ["APPROVED"],
                "locality": [10, 11],
            },
        )
    )
    router.get(MINDAT_LOCS).mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": 10,
                        "txt": "Sample locality",
                        "latitude": 34.5,
                        "longitude": -78.4,
                        "country": "USA",
                    },
                    {
                        "id": 11,
                        "txt": "Far away locality",
                        "latitude": 36.7,
                        "longitude": 3.0,
                        "country": "Algeria",
                    },
                ]
            },
        )
    )
    router.get(MINDAT_SEARCH).mock(
        return_value=httpx.Response(200, json={"results": []})
    )

    router.get(url__regex=r"https://parser\.globalnames\.org/api/v1/.+").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "parsed": True,
                    "quality": 1,
                    "verbatim": "Hadrosaurus",
                    "normalized": "Hadrosaurus",
                    "canonical": {
                        "stemmed": "Hadrosaurus",
                        "simple": "Hadrosaurus",
                        "full": "Hadrosaurus",
                    },
                    "cardinality": 1,
                    "rank": "gen.",
                    "id": "test-id",
                    "parserVersion": "v1.15.1",
                }
            ],
        )
    )


@respx.mock
def test_synthesize_happy_path(client, monkeypatch):
    monkeypatch.setenv("MINDAT_API_KEY", "test-token")
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
    assert body["occurrences"]["view_all_url"]
    assert any(l["provider"] == "PBDB" for l in body["occurrences"]["browse_links"])
    gbif_total = next(s for s in body["occurrences"]["source_totals"] if s["provider"] == "GBIF")
    assert gbif_total["returned"] >= 1
    assert gbif_total["total"] == 1
    assert body["specimens"]["voucher_count"] == 1
    providers = {d["provider"]: d["status"] for d in body["diagnostics"]}
    assert providers["PBDB"] == "ok"
    assert providers["TAXONOMY"] == "ok"
    assert body["taxonomy"]["accepted_name"] == "Hadrosaurus foulkii"
    assert len(body["taxonomy"]["hierarchy"]) >= 6
    assert body["taxonomy"]["hierarchy"][0]["rank"] == "KINGDOM"
    assert providers["MORPHOSOURCE"] == "ok"
    assert body["media_3d"]["has_3d_assets"] is True
    assert body["media_3d"]["records"][0]["media_id"] == "000852930"
    assert body["media_3d"]["records"][0]["physical_object_taxonomy"] == "Hadrosaurus sp"
    assert providers["GBIF"] == "ok"
    assert any(
        f["properties"]["database_source"] == "GBIF"
        for f in body["occurrences"]["features"]
    )
    assert providers["PALEOCLIMATE"] == "ok"
    assert body["paleoclimate_proxy"]["study_count"] == 1
    assert body["paleoclimate_proxy"]["studies"][0]["study_id"] == "9101"
    assert body["paleoclimate_proxy"]["model_source"] == "NCEI Paleo Search (NOAA)"
    assert providers["CROSSREF"] == "ok"
    assert providers["OPENALEX"] == "ok"
    assert len(body["literature"]) == 2
    assert body["literature"][0]["doi"] == "10.9999/openalex"
    assert body["literature"][0]["provider"] == "OpenAlex"
    assert body["literature"][0]["cited_by_count"] == 12
    assert body["literature"][1]["doi"] == "10.1234/example"
    assert "Canis dirus" in body["literature"][1]["title"]
    assert body["literature"][1]["authors"] == ["Jane Doe"]
    pbdb_feat = next(
        f for f in body["occurrences"]["features"] if f["properties"]["database_source"] == "PBDB"
    )
    assert pbdb_feat["properties"]["paleolat"] == 30.1
    assert pbdb_feat["properties"]["paleolng"] == -75.2
    assert providers["MINDAT"] == "ok"
    assert providers["GNPARSER"] == "ok"
    assert body["name_parse"]["parse_count"] >= 1
    assert body["name_parse"]["parses"][0]["canonical_simple"] == "Hadrosaurus"
    assert body["minerals"]["mineral_count"] == 1
    assert body["minerals"]["minerals"][0]["name"] == "Quartz"
    assert body["minerals"]["locality_count"] == 1
    assert body["minerals"]["link_mode"] == "spatial"
    assert body["minerals"]["linked_taxon"] == "Hadrosaurus"
    assert all(
        (loc.get("distance_km") is None or loc["distance_km"] <= 50.5)
        for loc in body["minerals"]["localities"]
    )
    assert not any("Algeria" in (loc.get("country") or "") for loc in body["minerals"]["localities"])


@respx.mock
def test_taxon_only_derives_coords_for_macrostrat(client, monkeypatch):
    """PBDB/GBIF run first; their coords feed Macrostrat/Mindat when lat/lng omitted."""
    monkeypatch.setenv("MINDAT_API_KEY", "test-token")
    _mock_live_upstreams(respx)
    r = client.get("/api/v1/synthesize", params={"taxon": "Hadrosaurus", "limit": 25})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    # Derived from occurrence centroids (PBDB/GBIF/Neotoma), not request params.
    assert body["query"]["coordinates"]["lat"] is not None
    assert body["query"]["coordinates"]["lng"] is not None
    providers = {d["provider"]: d["status"] for d in body["diagnostics"]}
    assert providers["PBDB"] == "ok"
    assert providers["GBIF"] == "ok"
    assert providers["MACROSTRAT"] == "ok"
    assert body["geology"]["macrostrat_units"][0]["unit_name"] == "Austin Chalk"
    assert providers["MINDAT"] == "ok"
    assert body["minerals"]["link_mode"] == "spatial"


@respx.mock
def test_adapter_failure_still_200(client, monkeypatch):
    monkeypatch.setenv("MINDAT_API_KEY", "test-token")
    respx.get(GBIF_MATCH).mock(return_value=httpx.Response(200, json={}))
    respx.get(PBDB_TAXA).mock(return_value=httpx.Response(200, json={"records": []}))
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
    respx.get(NOAA_URL).mock(
        return_value=httpx.Response(200, json={"study": [], "page": []})
    )
    respx.get(CROSSREF_URL).mock(
        return_value=httpx.Response(
            200, json={"status": "ok", "message": {"total-results": 0, "items": []}}
        )
    )
    respx.get(OPENALEX_URL).mock(
        return_value=httpx.Response(200, json={"meta": {"count": 0}, "results": []})
    )
    respx.post("https://api.mindat.org/v1/geomin-point/").mock(
        return_value=httpx.Response(200, json={})
    )
    respx.post("https://api.mindat.org/v1/geoloc-point/").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get(MINDAT_SEARCH).mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    respx.get(url__regex=r"https://parser\\.globalnames\\.org/api/v1/.+").mock(
        return_value=httpx.Response(200, json=[])
    )

    r = client.get("/api/v1/synthesize", params={"taxon": "Hadrosaurus", "lat": 1, "lng": 2})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    pbdb = next(d for d in body["diagnostics"] if d["provider"] == "PBDB")
    assert pbdb["status"] == "error"
    assert body["occurrences"]["total_records"] == 0


@respx.mock
def test_cache_hit(client, monkeypatch):
    monkeypatch.setenv("MINDAT_API_KEY", "test-token")
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


@respx.mock
def test_limit_param_changes_cache_key(client, monkeypatch):
    monkeypatch.setenv("MINDAT_API_KEY", "test-token")
    _mock_live_upstreams(respx)
    base = {"taxon": "Hadrosaurus", "lat": 34.55, "lng": -78.45}
    r1 = client.get("/api/v1/synthesize", params={**base, "limit": 5})
    assert r1.status_code == 200
    assert r1.headers.get("X-Cache") == "MISS"
    r2 = client.get("/api/v1/synthesize", params={**base, "limit": 5})
    assert r2.headers.get("X-Cache") == "HIT"
    r3 = client.get("/api/v1/synthesize", params={**base, "limit": 10})
    assert r3.status_code == 200
    assert r3.headers.get("X-Cache") == "MISS"


def test_limit_out_of_range_422(client):
    r = client.get("/api/v1/synthesize", params={"taxon": "Hadrosaurus", "limit": 0})
    assert r.status_code == 422
    r2 = client.get("/api/v1/synthesize", params={"taxon": "Hadrosaurus", "limit": 301})
    assert r2.status_code == 422


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
