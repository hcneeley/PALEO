"""Neotoma adapter: real v2 payload shape + skip empty rows."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.adapters.base import QueryParams
from app.adapters.neotoma import _coords_from_site, fetch_and_parse
from app.http import shutdown_http_client, startup_http_client

NEOTOMA_TAXA = "https://api.neotomadb.org/v2.0/data/taxa"
NEOTOMA_OCC = "https://api.neotomadb.org/v2.0/data/occurrences"


def test_coords_from_location_geojson():
    lat, lng = _coords_from_site(
        {"location": '{"type":"Point","coordinates":[-82.55,28.875]}'}
    )
    assert lat == pytest.approx(28.875)
    assert lng == pytest.approx(-82.55)


@respx.mock
async def test_neotoma_parses_occid_and_skips_empty():
    respx.get(NEOTOMA_TAXA).mock(
        return_value=httpx.Response(200, json={"data": [{"taxonid": 5912}]})
    )
    respx.get(NEOTOMA_OCC).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "occid": 4812242,
                        "sample": {"taxonname": "Canis dirus"},
                        "age": {"ageolder": 150000, "ageyounger": 14000},
                        "site": {
                            "location": (
                                '{"type":"Point","coordinates":[-82.55,28.875]}'
                            )
                        },
                    },
                    {"occid": None, "sample": {}, "site": {}, "age": {}},
                    {
                        "occid": 99,
                        "sample": {"taxonname": "ghost"},
                        "site": {"location": None},
                        "age": {},
                    },
                ]
            },
        )
    )
    await startup_http_client()
    try:
        result = await fetch_and_parse(QueryParams(taxon="Canis dirus", limit=50))
    finally:
        await shutdown_http_client()

    assert result.status == "ok"
    feats = (result.data or {}).get("features") or []
    assert len(feats) == 1
    props = feats[0]["properties"]
    assert props["database_source"] == "NEOTOMA"
    assert props["occurrence_id"] == "neotoma:occ:4812242"
    assert props["taxon_name"] == "Canis dirus"
    assert props["max_ma"] == pytest.approx(0.15)
    assert props["min_ma"] == pytest.approx(0.014)
    assert feats[0]["geometry"]["coordinates"] == [-82.55, 28.875]
