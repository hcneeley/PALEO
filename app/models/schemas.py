"""Pydantic models for /api/v1/synthesize."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Coordinates(BaseModel):
    lat: float | None = None
    lng: float | None = None


class GtsNormalizedAge(BaseModel):
    epoch: str | None = None
    stage: str | None = None
    age_min_ma: float | None = None
    age_max_ma: float | None = None


class QueryBlock(BaseModel):
    taxon: str | None = None
    coordinates: Coordinates
    radius_km: float
    gts_normalized_age: GtsNormalizedAge


class MacrostratUnit(BaseModel):
    unit_id: int | None = None
    unit_name: str | None = None
    lithology: str | None = None
    age_bottom_ma: float | None = None
    age_top_ma: float | None = None
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
    lat: float | None = None
    lng: float | None = None
    data_publisher: str | None = None
    url: str | None = None


class PaleoclimateProxy(BaseModel):
    target_ma: float | None = None
    estimated_mat_celsius: float | None = None
    estimated_map_mm: float | None = None
    estimated_pco2_ppm: float | None = None
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
    max_ma: float | None = None
    min_ma: float | None = None
    paleolat: float | None = None
    paleolng: float | None = None


class OccurrenceFeature(BaseModel):
    type: str = "Feature"
    geometry: GeoJSONGeometry | None = None
    properties: OccurrenceProperties


class OccurrencesBlock(BaseModel):
    type: str = "FeatureCollection"
    total_records: int = 0
    features: list[OccurrenceFeature] = Field(default_factory=list)


class SpecimenRecord(BaseModel):
    provider: str
    institution_code: str | None = None
    catalog_number: str | None = None
    scientific_name: str | None = None
    epandda_matched: bool = False
    uuid: str | None = None
    url: str | None = None


class SpecimensBlock(BaseModel):
    voucher_count: int = 0
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
    year: int | None = None
    container_title: str | None = None
    type: str | None = None
    url: str | None = None
    cited_by_count: int | None = None


class MineralRecord(BaseModel):
    provider: str = "Mindat"
    mineral_id: str | None = None
    name: str | None = None
    formula: str | None = None
    ima_status: Any = None
    crystal_system: str | None = None
    hardness_min: float | None = None
    hardness_max: float | None = None
    url: str | None = None


class MineralLocality(BaseModel):
    provider: str = "Mindat"
    locality_id: str | None = None
    name: str | None = None
    country: str | None = None
    lat: float | None = None
    lon: float | None = None
    mineral: str | None = None
    url: str | None = None


class MineralsBlock(BaseModel):
    mineral_count: int = 0
    locality_count: int = 0
    minerals: list[MineralRecord] = Field(default_factory=list)
    localities: list[MineralLocality] = Field(default_factory=list)
    status: str | None = None


class AdapterDiagnostic(BaseModel):
    provider: str
    status: str
    error: str | None = None
    record_count: int = 0
    elapsed_ms: float | None = None


class SynthesizeResponse(BaseModel):
    status: str = "success"
    execution_time_ms: float
    cache_status: str
    query: QueryBlock
    geology: GeologyBlock
    paleoclimate_proxy: PaleoclimateProxy
    occurrences: OccurrencesBlock
    specimens: SpecimensBlock
    media_3d: Media3dBlock
    minerals: MineralsBlock = Field(default_factory=MineralsBlock)
    literature: list[LiteratureRecord] = Field(default_factory=list)
    diagnostics: list[AdapterDiagnostic] = Field(default_factory=list)
    extras: dict[str, Any] = Field(default_factory=dict)