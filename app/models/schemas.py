"""Pydantic models for /api/v1/synthesize."""

from __future__ import annotations

from typing import Annotated, Any, Optional

from pydantic import BaseModel, BeforeValidator, Field


def _coerce_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _coerce_int(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


OptFloat = Annotated[Optional[float], BeforeValidator(_coerce_float)]
OptInt = Annotated[Optional[int], BeforeValidator(_coerce_int)]


class Coordinates(BaseModel):
    lat: OptFloat = None
    lng: OptFloat = None


class GtsNormalizedAge(BaseModel):
    epoch: str | None = None
    stage: str | None = None
    age_min_ma: OptFloat = None
    age_max_ma: OptFloat = None


class QueryBlock(BaseModel):
    taxon: str | None = None
    coordinates: Coordinates
    radius_km: float
    gts_normalized_age: GtsNormalizedAge


class MacrostratUnit(BaseModel):
    unit_id: OptInt = None
    unit_name: str | None = None
    lithology: str | None = None
    age_bottom_ma: OptFloat = None
    age_top_ma: OptFloat = None
    environment: str | None = None


class GeologyBlock(BaseModel):
    macrostrat_units: list[MacrostratUnit] = Field(default_factory=list)


class PaleoclimateStudy(BaseModel):
    study_id: str | None = None
    noaa_study_id: str | None = None
    study_name: str | None = None
    doi: str | None = None
    data_type: str | None = None
    investigators: str | None = None
    site_name: str | None = None
    lat: OptFloat = None
    lng: OptFloat = None
    data_publisher: str | None = None
    url: str | None = None


class PaleoclimateProxy(BaseModel):
    target_ma: OptFloat = None
    estimated_mat_celsius: OptFloat = None
    estimated_map_mm: OptFloat = None
    estimated_pco2_ppm: OptFloat = None
    model_source: str | None = None
    status: str | None = None
    study_count: int = 0
    studies: list[PaleoclimateStudy] = Field(default_factory=list)


class GeoJSONGeometry(BaseModel):
    type: str = "Point"
    coordinates: list[float]


class OccurrenceProperties(BaseModel):
    occurrence_id: str | None = None
    database_source: str
    taxon_name: str | None = None
    accepted_name: str | None = None
    dwc_eventDate: str | None = None
    max_ma: OptFloat = None
    min_ma: OptFloat = None
    paleolat: OptFloat = None
    paleolng: OptFloat = None


class OccurrenceFeature(BaseModel):
    type: str = "Feature"
    geometry: GeoJSONGeometry | None = None
    properties: OccurrenceProperties


class OccurrenceBrowseLink(BaseModel):
    """Link to browse the full occurrence set beyond this response's cap."""

    provider: str
    label: str
    url: str


class OccurrenceSourceTotal(BaseModel):
    """Per-provider returned vs upstream-available counts."""

    provider: str
    returned: int = 0
    total: int | None = None
    has_more: bool = False


class OccurrencesBlock(BaseModel):
    type: str = "FeatureCollection"
    # Upstream-available count (sum of source_totals), not len(features) page size.
    total_records: int = 0
    features: list[OccurrenceFeature] = Field(default_factory=list)
    # Same synthesize URL — open for the full JSON FeatureCollection returned here
    view_all_url: str | None = None
    # Upstream portals for occurrences beyond UPAE's per-source limit
    browse_links: list[OccurrenceBrowseLink] = Field(default_factory=list)
    source_totals: list[OccurrenceSourceTotal] = Field(default_factory=list)


class SpecimenRecord(BaseModel):
    provider: str
    institution_code: str | None = None
    catalog_number: str | None = None
    scientific_name: str | None = None
    epandda_matched: bool = False
    uuid: str | None = None
    url: str | None = None


class SpecimensBlock(BaseModel):
    # Upstream-available count when known (iDigBio itemCount); else page length.
    voucher_count: int = 0
    returned: int = 0
    total: int | None = None
    has_more: bool = False
    records: list[SpecimenRecord] = Field(default_factory=list)


class Media3dRecord(BaseModel):
    provider: str
    media_id: str | None = None
    title: str | None = None
    media_type: str | None = None
    modality: str | None = None
    device_facility: str | None = None
    physical_object_id: str | None = None
    physical_object_title: str | None = None
    physical_object_organization: str | None = None
    physical_object_type: str | None = None
    physical_object_taxonomy: str | None = None
    short_description: str | None = None
    description: str | None = None
    element_part: str | None = None
    doi: str | None = None
    ark: str | None = None
    date_upload: str | None = None
    date_modified: str | None = None
    url: str | None = None


class Media3dBlock(BaseModel):
    has_3d_assets: bool = False
    records: list[Media3dRecord] = Field(default_factory=list)
    status: str | None = None


class LiteratureRecord(BaseModel):
    provider: str | None = None
    doi: str | None = None
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: OptInt = None
    container_title: str | None = None
    type: str | None = None
    url: str | None = None
    cited_by_count: OptInt = None


class MineralRecord(BaseModel):
    provider: str = "Mindat"
    mineral_id: str | None = None
    name: str | None = None
    formula: str | None = None
    ima_status: Any = None
    crystal_system: str | None = None
    hardness_min: OptFloat = None
    hardness_max: OptFloat = None
    url: str | None = None
    link_mode: str | None = None  # spatial | name


class MineralLocality(BaseModel):
    provider: str = "Mindat"
    locality_id: str | None = None
    name: str | None = None
    country: str | None = None
    lat: OptFloat = None
    lon: OptFloat = None
    mineral: str | None = None
    url: str | None = None
    link_mode: str | None = None
    distance_km: OptFloat = None


class MineralsBlock(BaseModel):
    mineral_count: int = 0
    locality_count: int = 0
    minerals: list[MineralRecord] = Field(default_factory=list)
    localities: list[MineralLocality] = Field(default_factory=list)
    status: str | None = None
    link_mode: str | None = None  # spatial | name
    linked_taxon: str | None = None
    link_lat: OptFloat = None
    link_lng: OptFloat = None
    link_radius_km: OptFloat = None


class AdapterDiagnostic(BaseModel):
    provider: str
    status: str
    error: str | None = None
    record_count: int = 0
    elapsed_ms: OptFloat = None




class TaxonomyRank(BaseModel):
    rank: str
    name: str
    source: str | None = None
    taxon_key: str | None = None
    authorship: str | None = None
    status: str | None = None


class TaxonomyBlock(BaseModel):
    query: str | None = None
    accepted_name: str | None = None
    scientific_name: str | None = None
    rank: str | None = None
    taxonomic_status: str | None = None
    confidence: OptInt = None
    match_type: str | None = None
    hierarchy: list[TaxonomyRank] = Field(default_factory=list)
    pbdb_hierarchy: list[TaxonomyRank] = Field(default_factory=list)
    gbif_usage_key: OptInt = None
    gbif_url: str | None = None
    pbdb_url: str | None = None
    status: str | None = None


class SynthesizeResponse(BaseModel):
    status: str = "success"
    execution_time_ms: float
    cache_status: str
    query: QueryBlock
    taxonomy: TaxonomyBlock = Field(default_factory=TaxonomyBlock)
    geology: GeologyBlock
    paleoclimate_proxy: PaleoclimateProxy
    occurrences: OccurrencesBlock
    specimens: SpecimensBlock
    media_3d: Media3dBlock
    minerals: MineralsBlock = Field(default_factory=MineralsBlock)
    literature: list[LiteratureRecord] = Field(default_factory=list)
    diagnostics: list[AdapterDiagnostic] = Field(default_factory=list)
    extras: dict[str, Any] = Field(default_factory=dict)
