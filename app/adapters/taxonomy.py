"""Full taxonomic hierarchy from GBIF Backbone + PBDB.

GBIF: /species/match + /species/{key}/parents (+ species record for leaf rank)
PBDB: /taxa/single.json with class/parent/nav for paleo classification

Together these cover supra-specific ranks (kingdom→…→family→genus) and
infra ranks when present (subspecies, etc.), plus paleo accepted names.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from ..http import get_client
from .base import AdapterResult, QueryParams

GBIF_MATCH = "https://api.gbif.org/v1/species/match"
GBIF_SPECIES = "https://api.gbif.org/v1/species"
PBDB_TAXA = "https://paleobiodb.org/data1.2/taxa/single.json"

# Preferred display order (GBIF-style ranks, high → low)
_RANK_ORDER = [
    "DOMAIN",
    "SUPERKINGDOM",
    "KINGDOM",
    "SUBKINGDOM",
    "INFRAKINGDOM",
    "SUPERPHYLUM",
    "PHYLUM",
    "SUBPHYLUM",
    "INFRAPHYLUM",
    "SUPERCLASS",
    "CLASS",
    "SUBCLASS",
    "INFRACLASS",
    "PARVCLASS",
    "SUPERCOHORT",
    "COHORT",
    "LEGION",
    "SUPERORDER",
    "ORDER",
    "SUBORDER",
    "INFRAORDER",
    "PARVORDER",
    "SUPERFAMILY",
    "FAMILY",
    "SUBFAMILY",
    "TRIBE",
    "SUBTRIBE",
    "GENUS",
    "SUBGENUS",
    "SECTION",
    "SUBSECTION",
    "SERIES",
    "SPECIES",
    "SUBSPECIES",
    "VARIETY",
    "SUBVARIETY",
    "FORM",
    "SUBFORM",
    "CULTIVAR",
]

# PBDB data1.2 taxonomic rank codes (config.json?show=ranks)
_PBDB_RNK = {
    2: "SUBSPECIES",
    3: "SPECIES",
    4: "SUBGENUS",
    5: "GENUS",
    6: "SUBTRIBE",
    7: "TRIBE",
    8: "SUBFAMILY",
    9: "FAMILY",
    10: "SUPERFAMILY",
    11: "INFRAORDER",
    12: "SUBORDER",
    13: "ORDER",
    14: "SUPERORDER",
    15: "INFRACLASS",
    16: "SUBCLASS",
    17: "CLASS",
    18: "SUPERCLASS",
    19: "SUBPHYLUM",
    20: "PHYLUM",
    21: "SUPERPHYLUM",
    22: "SUBKINGDOM",
    23: "KINGDOM",
}

# Linnaean slots from PBDB show=class (not immparent — ipl is immediate parent name)
_PBDB_CLASS_FIELDS = (
    ("KINGDOM", "kgl"),
    ("PHYLUM", "phl"),
    ("CLASS", "cll"),
    ("ORDER", "odl"),
    ("FAMILY", "fml"),
    ("GENUS", "gnl"),
)


def _rank_key(rank: str | None) -> int:
    if not rank:
        return 10_000
    r = rank.upper().replace(".", "")
    aliases = {"SP": "SPECIES", "SSP": "SUBSPECIES", "VAR": "VARIETY", "F": "FORM", "GEN": "GENUS"}
    r = aliases.get(r, r)
    try:
        return _RANK_ORDER.index(r)
    except ValueError:
        return 5_000


def _rank_row(
    *,
    rank: str | None,
    name: str | None,
    source: str,
    taxon_key: str | int | None = None,
    authorship: str | None = None,
    status: str | None = None,
) -> dict[str, Any] | None:
    if not name:
        return None
    return {
        "rank": (rank or "UNRANKED").upper(),
        "name": name,
        "source": source,
        "taxon_key": str(taxon_key) if taxon_key is not None else None,
        "authorship": authorship,
        "status": status,
    }


def _pbdb_leaf_rank(pbdb_rec: dict[str, Any]) -> str | None:
    raw = pbdb_rec.get("rnk")
    try:
        return _PBDB_RNK.get(int(raw)) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _build_pbdb_hierarchy(pbdb_rec: dict[str, Any]) -> list[dict[str, Any]]:
    """Linnaean chain from PBDB class fields + leaf at its true rank.

    Do not map ``ipl`` (immediate parent from ``immparent``) to SUBGENUS — that
    repeats the parent family/genus. Subgenera come from ``sgs`` when present.
    """
    out: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for rank, key in _PBDB_CLASS_FIELDS:
        row = _rank_row(
            rank=rank,
            name=pbdb_rec.get(key),
            source="PBDB",
            taxon_key=pbdb_rec.get("oid"),
            authorship=pbdb_rec.get("att"),
        )
        if row and row["name"] not in seen_names:
            out.append(row)
            seen_names.add(row["name"])

    for sg in pbdb_rec.get("sgs") or []:
        if not isinstance(sg, dict):
            continue
        row = _rank_row(
            rank="SUBGENUS",
            name=sg.get("nam"),
            source="PBDB",
            taxon_key=sg.get("oid") or pbdb_rec.get("oid"),
        )
        if row and row["name"] not in seen_names:
            out.append(row)
            seen_names.add(row["name"])

    leaf_name = pbdb_rec.get("acn") or pbdb_rec.get("nam")
    leaf_rank = _pbdb_leaf_rank(pbdb_rec)
    if leaf_name and leaf_rank:
        # Skip if this name is already in the chain at any rank (e.g. genus leaf
        # already listed via gnl) — avoids labeling Coleonyx as SPECIES.
        if leaf_name not in seen_names:
            row = _rank_row(
                rank=leaf_rank,
                name=leaf_name,
                source="PBDB",
                taxon_key=pbdb_rec.get("acc") or pbdb_rec.get("oid"),
                authorship=pbdb_rec.get("att"),
                status="accepted" if pbdb_rec.get("acn") else None,
            )
            if row:
                out.append(row)
                seen_names.add(leaf_name)
        else:
            # Same name already present (genus query): ensure rank matches rnk.
            for row in out:
                if row["name"] == leaf_name and leaf_rank:
                    row["rank"] = leaf_rank
                    break
    return out


def _reconcile_gbif_ranks_with_pbdb(
    hierarchy: list[dict[str, Any]],
    pbdb_hierarchy: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Prefer PBDB Linnaean slots when GBIF mislabels the same taxon name.

    GBIF Backbone often ranks Squamata as CLASS with no ORDER; PBDB places it
    under ORDER with CLASS=Reptilia. Realign matching names and fill empty
    major ranks from PBDB without overwriting a different family/genus.
    """
    if not hierarchy or not pbdb_hierarchy:
        return hierarchy

    pbdb_by_name = {r["name"]: r for r in pbdb_hierarchy if r.get("name")}
    for row in hierarchy:
        pb = pbdb_by_name.get(row.get("name") or "")
        if pb and pb.get("rank") and pb["rank"] != row.get("rank"):
            row["rank"] = pb["rank"]

    have_ranks = {r.get("rank") for r in hierarchy}
    have_names = {r.get("name") for r in hierarchy}
    major = {"KINGDOM", "PHYLUM", "CLASS", "ORDER", "FAMILY", "GENUS", "SPECIES"}
    for pr in pbdb_hierarchy:
        rank, name = pr.get("rank"), pr.get("name")
        if not rank or not name or rank not in major:
            continue
        if rank in have_ranks or name in have_names:
            continue
        filled = _rank_row(
            rank=rank,
            name=name,
            source="PBDB",
            taxon_key=pr.get("taxon_key"),
            authorship=pr.get("authorship"),
            status=pr.get("status"),
        )
        if filled:
            hierarchy.append(filled)
            have_ranks.add(rank)
            have_names.add(name)

    hierarchy.sort(key=lambda r: _rank_key(r.get("rank")))
    return hierarchy


async def fetch_and_parse(params: QueryParams) -> AdapterResult:
    if not params.taxon:
        return AdapterResult(
            provider="TAXONOMY",
            status="skipped",
            error="taxon required",
            data={"hierarchy": [], "sources": {}},
        )

    client = get_client()
    headers = {"Accept": "application/json", "User-Agent": "UPAE/0.1 (https://github.com/hcneeley/upae)"}
    gbif_match: dict[str, Any] = {}
    gbif_parents: list[dict[str, Any]] = []
    gbif_species: dict[str, Any] = {}
    pbdb_rec: dict[str, Any] = {}
    errors: list[str] = []

    # --- GBIF ---
    try:
        match_resp = await client.get(
            GBIF_MATCH,
            params={"name": params.taxon, "verbose": "true"},
            headers=headers,
        )
        match_resp.raise_for_status()
        gbif_match = match_resp.json() if isinstance(match_resp.json(), dict) else {}
        usage_key = gbif_match.get("usageKey") or gbif_match.get("speciesKey")
        if usage_key:
            parents_resp = await client.get(
                f"{GBIF_SPECIES}/{usage_key}/parents",
                headers=headers,
            )
            if parents_resp.status_code < 400:
                raw = parents_resp.json()
                gbif_parents = raw if isinstance(raw, list) else []
            sp_resp = await client.get(f"{GBIF_SPECIES}/{usage_key}", headers=headers)
            if sp_resp.status_code < 400:
                body = sp_resp.json()
                gbif_species = body if isinstance(body, dict) else {}
    except httpx.HTTPError as exc:
        errors.append(f"GBIF: {exc}")

    # --- PBDB ---
    try:
        pbdb_resp = await client.get(
            PBDB_TAXA,
            params={
                "name": params.taxon,
                "show": "attr,class,parent,immparent,nav",
            },
            headers=headers,
        )
        pbdb_resp.raise_for_status()
        records = (pbdb_resp.json() or {}).get("records") or []
        if records:
            pbdb_rec = records[0]
    except httpx.HTTPError as exc:
        errors.append(f"PBDB: {exc}")

    hierarchy: list[dict[str, Any]] = []

    # GBIF parents (root → near tip)
    for p in gbif_parents:
        row = _rank_row(
            rank=p.get("rank"),
            name=p.get("canonicalName") or p.get("scientificName"),
            source="GBIF",
            taxon_key=p.get("key") or p.get("nubKey"),
            authorship=None,
            status=p.get("taxonomicStatus"),
        )
        if row:
            hierarchy.append(row)

    # GBIF leaf (matched usage)
    leaf_name = (
        gbif_species.get("canonicalName")
        or gbif_match.get("canonicalName")
        or gbif_species.get("scientificName")
        or gbif_match.get("scientificName")
    )
    leaf_rank = gbif_species.get("rank") or gbif_match.get("rank")
    if leaf_name:
        # Avoid duplicating last parent if identical
        last = hierarchy[-1] if hierarchy else None
        if not last or last.get("name") != leaf_name or last.get("rank") != (leaf_rank or "").upper():
            row = _rank_row(
                rank=leaf_rank,
                name=leaf_name,
                source="GBIF",
                taxon_key=gbif_match.get("usageKey") or gbif_species.get("key"),
                authorship=None,
                status=gbif_match.get("status") or gbif_species.get("taxonomicStatus"),
            )
            if row:
                hierarchy.append(row)

    # Fill any major ranks from match object if parents were empty
    if not gbif_parents and gbif_match:
        for rank, key in (
            ("KINGDOM", "kingdom"),
            ("PHYLUM", "phylum"),
            ("CLASS", "class"),
            ("ORDER", "order"),
            ("FAMILY", "family"),
            ("GENUS", "genus"),
            ("SPECIES", "species"),
        ):
            row = _rank_row(
                rank=rank,
                name=gbif_match.get(key),
                source="GBIF",
                taxon_key=gbif_match.get(f"{key}Key"),
            )
            if row and all(r.get("name") != row["name"] or r.get("rank") != rank for r in hierarchy):
                hierarchy.append(row)
        hierarchy.sort(key=lambda r: _rank_key(r.get("rank")))

    # PBDB parallel classification (paleo view)
    pbdb_hierarchy: list[dict[str, Any]] = (
        _build_pbdb_hierarchy(pbdb_rec) if pbdb_rec else []
    )

    # Align GBIF rank labels with PBDB when the same name is slotted differently
    # (e.g. Squamata as CLASS in GBIF vs ORDER in PBDB) and fill missing majors.
    if hierarchy and pbdb_hierarchy:
        hierarchy = _reconcile_gbif_ranks_with_pbdb(hierarchy, pbdb_hierarchy)

    # When GBIF missing, fall back to PBDB order
    if not hierarchy and pbdb_hierarchy:
        hierarchy = list(pbdb_hierarchy)

    status = "ok" if hierarchy or gbif_match or pbdb_rec else "error"
    if status == "error" and errors:
        err = "; ".join(errors)
    elif status == "error":
        err = "no taxonomy found"
    else:
        err = "; ".join(errors) if errors else None

    usage_key = gbif_match.get("usageKey")
    return AdapterResult(
        provider="TAXONOMY",
        status=status,
        error=err,
        data={
            "query": params.taxon,
            "accepted_name": (
                gbif_match.get("canonicalName")
                or pbdb_rec.get("acn")
                or pbdb_rec.get("nam")
            ),
            "scientific_name": gbif_match.get("scientificName") or pbdb_rec.get("nam"),
            "rank": (gbif_match.get("rank") or leaf_rank),
            "taxonomic_status": gbif_match.get("status") or gbif_species.get("taxonomicStatus"),
            "confidence": gbif_match.get("confidence"),
            "match_type": gbif_match.get("matchType"),
            "hierarchy": hierarchy,
            "pbdb_hierarchy": pbdb_hierarchy,
            "gbif_usage_key": usage_key,
            "gbif_url": (
                f"https://www.gbif.org/species/{usage_key}" if usage_key else None
            ),
            "pbdb_url": (
                f"https://paleobiodb.org/classic/basicTaxonInfo?taxon_no="
                + quote(str(pbdb_rec.get("oid") or "").replace("txn:", ""))
                if pbdb_rec.get("oid")
                else None
            ),
            "pbdb": {
                "name": pbdb_rec.get("nam"),
                "accepted_name": pbdb_rec.get("acn"),
                "attribution": pbdb_rec.get("att"),
                "taxon_id": pbdb_rec.get("oid"),
            }
            if pbdb_rec
            else None,
            "records": hierarchy,
        },
    )
