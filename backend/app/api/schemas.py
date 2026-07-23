"""Shared Pydantic schemas and helpers for the REST API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class HealthResponse(BaseModel):
    status: str
    service: str
    db_ok: bool
    data_root: str
    archive_url: str


class JobOut(ORMModel):
    id: int
    job_type: str
    scope: str
    status: str
    progress_current: int
    progress_total: int
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    log_summary: str


class TimeslotOut(ORMModel):
    id: int
    year: str
    date: str
    time: str
    server_relative_path: str
    server_reported_size_bytes: Optional[int]
    sample_role: Optional[str]
    download_status: str
    local_raw_path: Optional[str]
    discovered_at: datetime
    downloaded_at: Optional[datetime]
    last_error: Optional[str]
    products_complete: Optional[bool] = None
    products_generated: Optional[int] = None
    # Sample vs standard day/twilight/night targets (for Browse UI)
    sample_target_time: Optional[str] = None
    sample_match: Optional[str] = None  # within_tolerance | nearest_fallback
    sample_offset_minutes: Optional[int] = None
    sample_note: Optional[str] = None


class ProductRefOut(ORMModel):
    product_name: str
    product_kind: str
    wavelength_or_spectral_band: str
    approximate_resolution: str
    plain_language_description: str
    agriculture_application: str
    aviation_application: str
    natural_resource_application: str
    disaster_response_application: str


class ProductOut(ORMModel):
    id: int
    timeslot_id: int
    product_name: str
    product_kind: str
    availability_status: str
    local_image_path: Optional[str]
    local_thumbnail_path: Optional[str]
    generated_at: Optional[datetime]
    error_message: Optional[str]
    image_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    map_image_url: Optional[str] = None
    has_map_overlay: bool = False
    reference: Optional[ProductRefOut] = None


class MapViewConfig(BaseModel):
    """Pakistan-focused Web Mercator ROI for the Dynamic Image viewer."""

    crs: str
    projection: str
    west: float
    south: float
    east: float
    north: float
    center_lat: float
    center_lon: float
    default_zoom: int
    leaflet_bounds: list[list[float]]


class MapEnsureResult(BaseModel):
    ok: bool
    product_id: int
    status: str = "ready"  # ready | generating | error | busy | unavailable
    map_image_url: Optional[str] = None
    error: Optional[str] = None


class GlobeProductOut(BaseModel):
    product_id: int
    timeslot_id: int
    product_name: str
    product_kind: str
    availability_status: str
    generation_status: str
    image_url: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    reference: Optional[ProductRefOut] = None


class GlobeCatalogOut(BaseModel):
    timeslot_id: int
    products: list[GlobeProductOut]


class DateSummary(BaseModel):
    date: str
    year: str
    discovered_count: int
    sampled_count: int
    sample_roles_filled: list[str]
    sample_label: str
    total_bytes: int
    nearest_fallback_count: int = 0


class DiskUsageBreakdown(BaseModel):
    """Bytes used under data/ — raw vs processed vs thumbnails (plus catalog)."""

    raw_bytes: int
    processed_bytes: int
    thumbnails_bytes: int
    catalog_bytes: int
    total_bytes: int
    free_gb: float


class DashboardStats(BaseModel):
    discovered_total: int
    selected_total: int
    downloaded_total: int
    failed_downloads: int
    processed_timeslots: int
    discovered_bytes: int
    selected_bytes: int
    downloaded_bytes_on_disk: int
    disk_free_gb: float
    disk_used_data_gb: float
    disk_breakdown: Optional[DiskUsageBreakdown] = None
    date_min: Optional[str]
    date_max: Optional[str]
    active_jobs: list[JobOut]
    config_snapshot: dict[str, Any]
    archive_reachable: Optional[bool] = None
    archive_latency_ms: Optional[float] = None
    archive_check_error: Optional[str] = None


class ConnectivityStatus(BaseModel):
    reachable: bool
    archive_url: str
    latency_ms: Optional[float] = None
    checked_at: str
    error: Optional[str] = None
    http_status: Optional[int] = None


class ComparePanel(BaseModel):
    role: str
    timeslot: Optional[TimeslotOut] = None
    product: Optional[ProductOut] = None
    missing_reason: Optional[str] = None


class CompareResponse(BaseModel):
    date: str
    product_name: str
    panels: list[ComparePanel]
    available_products: list[str]


class ActionResult(BaseModel):
    ok: bool
    job_id: Optional[int] = None
    job_type: Optional[str] = None
    error: Optional[str] = None
