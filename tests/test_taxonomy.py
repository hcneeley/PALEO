"""Taxonomy adapter: PBDB field mapping + GBIF rank reconciliation."""

from __future__ import annotations

import httpx
import respx

from app.adapters.base import QueryParams
from app.adapters.taxonomy import (
    _build_pbdb_hierarchy,
    _reconcile_gbif_ranks_with_pbdb,
    fetch_and_parse,
)
from app.http import shutdown_http_client, startup_http_client


def test_pbdb_hierarchy_does_not_reuse_parent_as_subgenus_or_species():
    """ipl is immediate parent; genus leaf must not become SPECIES."""
    rec = {
        "oid": "txn:37902",
        "nam": "Coleonyx",
        "att": "Gray 1845",
        "rnk": 5,
        "kgl": "Animalia",
        "phl": "Chordata",
        "cll": "Reptilia",
        "odl": "Squamata",
        "fml": "Gekkonidae",
        "gnl": "Coleonyx",
        "ipl": "Gekkonidae",
        "sgs": [],
    }
    rows = _build_pbdb_hierarchy(rec)
    by_rank = {r["rank"]: r["name"] for r in rows}
    assert by_rank["CLASS"] == "Reptilia"
    assert by_rank["ORDER"] == "Squamata"
    assert by_rank["FAMILY"] == "Gekkonidae"
    assert by_rank["GENUS"] == "Coleonyx"
    assert "SUBGENUS" not in by_rank
    assert "SPECIES" not in by_rank
    assert [r["name"] for r in rows].count("Gekkonidae") == 1
    assert [r["name"] for r in rows].count("Coleonyx") == 1


def test_pbdb_hierarchy_adds_species_leaf_when_rnk_is_species():
    rec = {
        "oid": "txn:1",
        "nam": "Hadrosaurus foulkii",
        "acn": "Hadrosaurus foulkii",
        "rnk": 3,
        "kgl": "Animalia",
        "phl": "Chordata",
        "cll": "Reptilia",
        "odl": "Ornithischia",
        "fml": "Hadrosauridae",
        "gnl": "Hadrosaurus",
        "ipl": "Hadrosaurus",
        "sgs": [],
    }
    rows = _build_pbdb_hierarchy(rec)
    by_rank = {r["rank"]: r["name"] for r in rows}
    assert by_rank["GENUS"] == "Hadrosaurus"
    assert by_rank["SPECIES"] == "Hadrosaurus foulkii"
    assert "SUBGENUS" not in by_rank


def test_reconcile_moves_squamata_to_order_and_fills_reptilia():
    gbif = [
        {"rank": "KINGDOM", "name": "Animalia", "source": "GBIF"},
        {"rank": "PHYLUM", "name": "Chordata", "source": "GBIF"},
        {"rank": "CLASS", "name": "Squamata", "source": "GBIF"},
        {"rank": "FAMILY", "name": "Eublepharidae", "source": "GBIF"},
        {"rank": "GENUS", "name": "Coleonyx", "source": "GBIF"},
    ]
    pbdb = [
        {"rank": "KINGDOM", "name": "Animalia", "source": "PBDB"},
        {"rank": "PHYLUM", "name": "Chordata", "source": "PBDB"},
        {"rank": "CLASS", "name": "Reptilia", "source": "PBDB"},
        {"rank": "ORDER", "name": "Squamata", "source": "PBDB"},
        {"rank": "FAMILY", "name": "Gekkonidae", "source": "PBDB"},
        {"rank": "GENUS", "name": "Coleonyx", "source": "PBDB"},
    ]
    out = _reconcile_gbif_ranks_with_pbdb(gbif, pbdb)
    by_rank = {r["rank"]: r["name"] for r in out}
    assert by_rank["CLASS"] == "Reptilia"
    assert by_rank["ORDER"] == "Squamata"
    # Keep GBIF's family when the slot is already filled
    assert by_rank["FAMILY"] == "Eublepharidae"
    assert by_rank["GENUS"] == "Coleonyx"


@respx.mock
async def test_fetch_coleonyx_hierarchy_live_shape():
    respx.get("https://api.gbif.org/v1/species/match").mock(
        return_value=httpx.Response(
            200,
            json={
                "usageKey": 2447230,
                "canonicalName": "Coleonyx",
                "rank": "GENUS",
                "status": "ACCEPTED",
                "kingdom": "Animalia",
                "phylum": "Chordata",
                "class": "Squamata",
                "family": "Eublepharidae",
                "genus": "Coleonyx",
            },
        )
    )
    respx.get("https://api.gbif.org/v1/species/2447230/parents").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"rank": "KINGDOM", "canonicalName": "Animalia", "key": 1},
                {"rank": "PHYLUM", "canonicalName": "Chordata", "key": 44},
                {"rank": "CLASS", "canonicalName": "Squamata", "key": 11592253},
                {"rank": "FAMILY", "canonicalName": "Eublepharidae", "key": 4287502},
            ],
        )
    )
    respx.get("https://api.gbif.org/v1/species/2447230").mock(
        return_value=httpx.Response(
            200,
            json={"key": 2447230, "canonicalName": "Coleonyx", "rank": "GENUS"},
        )
    )
    respx.get("https://paleobiodb.org/data1.2/taxa/single.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "records": [
                    {
                        "oid": "txn:37902",
                        "nam": "Coleonyx",
                        "att": "Gray 1845",
                        "rnk": 5,
                        "kgl": "Animalia",
                        "phl": "Chordata",
                        "cll": "Reptilia",
                        "odl": "Squamata",
                        "fml": "Gekkonidae",
                        "gnl": "Coleonyx",
                        "ipl": "Gekkonidae",
                        "sgs": [],
                    }
                ]
            },
        )
    )
    await startup_http_client()
    try:
        result = await fetch_and_parse(QueryParams(taxon="Coleonyx"))
    finally:
        await shutdown_http_client()

    assert result.status == "ok"
    pbdb = {r["rank"]: r["name"] for r in (result.data or {}).get("pbdb_hierarchy") or []}
    assert pbdb["ORDER"] == "Squamata"
    assert pbdb["GENUS"] == "Coleonyx"
    assert "SUBGENUS" not in pbdb
    assert "SPECIES" not in pbdb

    gbif = {r["rank"]: r["name"] for r in (result.data or {}).get("hierarchy") or []}
    assert gbif["CLASS"] == "Reptilia"
    assert gbif["ORDER"] == "Squamata"
