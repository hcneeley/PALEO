# Unified Paleontology API Engine (UPAE)

Async federated gateway that synthesizes paleontology, geology, and related upstream APIs into a single REST payload.

**MVP** under [`hcneeley/upae`](https://github.com/hcneeley/upae): live adapters for PBDB (incl. paleocoordinates), Macrostrat, Neotoma, iDigBio, MorphoSource, GBIF, NOAA NCEI Paleo Search, Crossref, OpenAlex, Mindat, and GNparser (key required); in-memory 24h cache (no Redis/PostGIS yet).

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
| **PBDB** | Fossil occurrences → GeoJSON features (incl. `paleolat` / `paleolng`) |
| **Macrostrat** | Stratigraphic units at lat/lng |
| **Neotoma** | Quaternary paleoecology occurrences |
| **iDigBio** | Museum specimen vouchers |
| **MorphoSource** | 3D / CT media (`/api/media`) → `media_3d` |
| **GBIF** | Extant occurrence search → GeoJSON features |
| **NCEI Paleo Search** | NOAA paleoclimate / paleoenvironmental studies → `paleoclimate_proxy` |
| **Crossref** | Bibliographic works → `literature` |
| **OpenAlex** | Relevance-ranked works → `literature` (merged with Crossref, DOI-deduped) |
| **GNparser** | Global Names Parser — canonical taxon parse → `name_parse` |
| **Mindat** | Minerals / geomaterials + localities → `minerals` (needs API key) |

### GNparser (Global Names Parser)

Uses [`https://parser.globalnames.org/api/v1/`](https://parser.globalnames.org/doc/api) to parse `taxon` into canonical form, rank, genus/species, and authorship. Part of the [Global Names](https://globalnames.org/) stack (see also [ZooBank via GNA apps](https://globalnames.org/apps/zoobank/)). Results appear under `name_parse`.

### Mindat

Links minerals to taxonomic queries **by place**, not by name:

- With `lat`/`lng`: [`geomin-point`](https://api.mindat.org/v1/schema/redoc/) / `geoloc-point` within `radius_km` → minerals & localities near the search area (`minerals.link_mode: spatial`).
- Taxon only (no coordinates): after PBDB/GBIF/Neotoma return, uses the occurrence centroid for the same spatial join when possible.
- Mineral-name queries (no useful coords): falls back to `geomaterials-search`.

Requires `MINDAT_API_KEY`. Without a key, the adapter reports `skipped`.

### OpenAlex

Uses [`GET https://api.openalex.org/works`](https://docs.openalex.org/api-entities/works/search-works) with `search=<taxon>` and `filter=type:article|review`. Set `OPENALEX_MAILTO` (falls back to `CROSSREF_MAILTO`) and optionally `OPENALEX_API_KEY` for a higher request budget. Results merge into `literature` ahead of Crossref, deduped by DOI; includes `cited_by_count` and `provider`.

### Crossref

Uses [`GET https://api.crossref.org/works`](https://www.crossref.org/documentation/retrieve-metadata/rest-api/) with `query=<taxon>` and `filter=type:journal-article`. Set `CROSSREF_MAILTO` for the [polite pool](https://www.crossref.org/documentation/retrieve-metadata/rest-api/). Results map DOI, title, authors, year, container title, and URL into `literature`.

### PBDB paleocoordinates

Occurrence requests use `show=coords,attr,class,paleoloc`. Compact fields `pla` / `pln` are exposed as `properties.paleolat` / `properties.paleolng` on PBDB features (plate-reconstructed paleolocation when PBDB provides it).

### NCEI Paleo Search (NOAA)

Uses [`study/search.json`](https://www.ncei.noaa.gov/access/paleo-search/api) with `dataPublisher=NOAA`, optional lat/lng bbox from `radius_km`, `searchText` from taxon, and age bounds as years BP. Docs: [API](https://www.ncei.noaa.gov/access/paleo-search/api). Studies appear under `paleoclimate_proxy.studies` (NOAA caps full study pages at 10).

### GBIF

Uses the Occurrence Search API (`GET https://api.gbif.org/v1/occurrence/search`) per [GBIF OpenAPI docs](https://techdocs.gbif.org/en/openapi/). Filters with `scientificName`, optional `geoDistance` (lat,lng,radius_km), and `hasCoordinate=true`. Results land in `occurrences.features` with `database_source: GBIF`.

### MorphoSource

Queries [`/api/media`](https://www.morphosource.org/api/media) with `q=<taxon>&search_field=all_fields`. Records map MorphoSource media fields (id, title, media type, modality, device facility, physical object id/title/organization/type/taxonomy, descriptions, element/part, DOI, ARK, dates) into `media_3d.records`.


## Web UI

Try the search interface at [hcneeley.github.io/upae](https://hcneeley.github.io/upae/) — enter a taxon or mineral, optional location and age bounds, and browse synthesized geology, occurrences, specimens, minerals, and literature from the live API.

## Tests

```bash
pytest -q
```

## Roadmap (post-MVP)

- Redis cache + PostGIS spatial helpers
- Taxonomic synonym resolution / deeper DOI linkage across adapters
- Docker Compose

## Upstream docs

- [PBDB data service](https://paleobiodb.org/data1.2/)
- [Macrostrat API](https://macrostrat.org/api)
- [Neotoma APIv2](https://api.neotomadb.org/)
- [iDigBio search](https://github.com/iDigBio/idigbio-search-api/wiki)
- [MorphoSource API](https://github.com/MorphoSource/morphosource-api)
- [GBIF OpenAPI](https://techdocs.gbif.org/en/openapi/)
- [NCEI Paleo Search API](https://www.ncei.noaa.gov/access/paleo-search/api)
- [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)
- [OpenAlex works search](https://docs.openalex.org/api-entities/works/search-works)
- [GNparser API](https://parser.globalnames.org/doc/api) · [Global Names / ZooBank apps](https://globalnames.org/apps/zoobank/)
- [OpenMindat API](https://api.mindat.org/v1/schema/redoc/) · [Get a Mindat API key](https://www.mindat.org/a/how_to_get_my_mindat_api_key)
- Related composite: [elc-api](https://github.com/hcneeley/elc-api)
