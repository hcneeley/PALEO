# Unified Paleontology API Engine (UPAE)

Async federated gateway that synthesizes paleontology, geology, and related upstream APIs into a single REST payload.

**MVP** under [`hcneeley/upae`](https://github.com/hcneeley/upae): live adapters for PBDB, Macrostrat, Neotoma, iDigBio, MorphoSource, GBIF, and NOAA NCEI Paleo Search; stub for CrossRef; in-memory 24h cache (no Redis/PostGIS yet).

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
| **MorphoSource** | 3D / CT media (`/api/media`) → `media_3d` |
| **GBIF** | Extant occurrence search → GeoJSON features |
| **NCEI Paleo Search** | NOAA paleoclimate / paleoenvironmental studies → `paleoclimate_proxy` |

### NCEI Paleo Search (NOAA)

Uses [`study/search.json`](https://www.ncei.noaa.gov/access/paleo-search/api) with `dataPublisher=NOAA`, optional lat/lng bbox from `radius_km`, `searchText` from taxon, and age bounds as years BP. Docs: [API](https://www.ncei.noaa.gov/access/paleo-search/api). Studies appear under `paleoclimate_proxy.studies` (NOAA caps full study pages at 10).

### GBIF

Uses the Occurrence Search API (`GET https://api.gbif.org/v1/occurrence/search`) per [GBIF OpenAPI docs](https://techdocs.gbif.org/en/openapi/). Filters with `scientificName`, optional `geoDistance` (lat,lng,radius_km), and `hasCoordinate=true`. Results land in `occurrences.features` with `database_source: GBIF`.

### MorphoSource

Queries [`/api/media`](https://www.morphosource.org/api/media) with `q=<taxon>&search_field=all_fields`. Records map MorphoSource media fields (id, title, media type, modality, device facility, physical object id/title/organization/type/taxonomy, descriptions, element/part, DOI, ARK, dates) into `media_3d.records`.

## Stubs (MVP)

CrossRef returns an empty literature list with `status: stub` in diagnostics.

## Tests

```bash
pytest -q
```

## Deploy on Render

Repo is Render-ready (`render.yaml` + `Procfile`). This does **not** create a Render service by itself — connect the GitHub repo in the Render dashboard when you want it live.

1. Push `main` to [hcneeley/upae](https://github.com/hcneeley/upae) (already the default).
2. In Render: **New → Blueprint** and select this repo, **or** **New → Web Service** → connect `hcneeley/upae`.
3. Confirm:
   - **Build:** `pip install -r requirements.txt`
   - **Start:** `gunicorn app.main:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
   - **Health check:** `/api/v1/`
4. Optional env vars (also listed in `render.yaml` / `.env.example`): `ADAPTER_TIMEOUT_SEC`, `CACHE_TTL_SEC`, `OCCURRENCE_LIMIT`.

Free tier: the service may sleep when idle; the first request after a pause can take ~30–60 seconds. Synthesize fans out to several upstream APIs, so cold starts plus a full query can feel slow.

Once deployed, try:

```text
https://<your-service>.onrender.com/api/v1/synthesize?taxon=Coleonyx+variegatus&lat=30.2672&lng=-97.7431&radius_km=500
```

## Roadmap (post-MVP)

- Redis cache + PostGIS spatial helpers
- Wire CrossRef bibliographic linkage
- Taxonomic synonym resolution + bibliographic DOI linkage
- Docker Compose

## Upstream docs

- [PBDB data service](https://paleobiodb.org/data1.2/)
- [Macrostrat API](https://macrostrat.org/api)
- [Neotoma APIv2](https://api.neotomadb.org/)
- [iDigBio search](https://github.com/iDigBio/idigbio-search-api/wiki)
- [MorphoSource API](https://github.com/MorphoSource/morphosource-api)
- [GBIF OpenAPI](https://techdocs.gbif.org/en/openapi/)
- [NCEI Paleo Search API](https://www.ncei.noaa.gov/access/paleo-search/api)
- Related composite: [elc-api](https://github.com/hcneeley/elc-api)
