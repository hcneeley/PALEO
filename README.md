# Unified Paleontology API Engine (UPAE)

Async federated gateway that synthesizes paleontology, geology, and related upstream APIs into a single REST payload.

**MVP** under [`hcneeley/upae`](https://github.com/hcneeley/upae): live adapters for PBDB, Macrostrat, Neotoma, and iDigBio; stubs for MorphoSource, GBIF, PaleoDAP, and CrossRef; in-memory 24h cache (no Redis/PostGIS yet).

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
```

Open http://127.0.0.1:8080/api/v1/

## Synthesize

```bash
curl "http://127.0.0.1:8080/api/v1/synthesize?taxon=Hadrosaurus&lat=34.55&lng=-78.45&radius_km=50"
```

| Param | Description |
|-------|-------------|
| `taxon` | Clade / genus / species (optional if lat+lng given) |
| `lat`, `lng` | Decimal degrees (optional if taxon given) |
| `radius_km` | Spatial buffer (default 10) |
| `age_min`, `age_max` | Numerical age bounds in Ma |

Response sections: `geology`, `occurrences` (GeoJSON FeatureCollection), `specimens`, `media_3d`, `literature`, `paleoclimate_proxy`, plus `diagnostics` per adapter. Header `X-Cache: HIT|MISS`.

## Live adapters (MVP)

| Source | Role |
|--------|------|
| **PBDB** | Fossil occurrences → GeoJSON features |
| **Macrostrat** | Stratigraphic units at lat/lng |
| **Neotoma** | Quaternary paleoecology occurrences |
| **iDigBio** | Museum specimen vouchers |

## Stubs (MVP)

MorphoSource, GBIF, PaleoDAP / paleoclimate, CrossRef return empty collections with `status: stub` in diagnostics.

## Tests

```bash
pytest -q
```

## Roadmap (post-MVP)

- Redis cache + PostGIS spatial helpers
- Wire MorphoSource, GBIF, PaleoDAP, CrossRef
- Taxonomic synonym resolution + bibliographic DOI linkage
- Docker Compose + Render deploy

## Upstream docs

- [PBDB data service](https://paleobiodb.org/data1.2/)
- [Macrostrat API](https://macrostrat.org/api)
- [Neotoma APIv2](https://api.neotomadb.org/)
- [iDigBio search](https://github.com/iDigBio/idigbio-search-api/wiki)
- Related composite: [elc-api](https://github.com/hcneeley/elc-api)
