"""
All tunables for the MSG HRIT Terrestrial Archive Explorer.

Values come from environment variables (see project-root .env.example)
with sane defaults matching BUILDPLAN Section 5 / Section 12.
Never hardcode these in business logic — import Settings instead.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root: backend/app/config.py → ../../
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Server (BUILDPLAN §2 / §12) ---
    archive_base_url: str = Field(
        default="http://YOUR_ARCHIVE_HOST:PORT/",
        description="Root URL of the archive server (set via ARCHIVE_BASE_URL in .env)",
    )
    archive_route: str = Field(
        default="HRIT_Native/",
        description="Archive path under the server root (must end with /)",
    )

    # --- Local data ---
    data_root: Path = Field(
        default=PROJECT_ROOT / "data",
        description="Local root for raw/, processed/, thumbnails/, catalog.sqlite3",
    )

    # --- Sample selection (BUILDPLAN §5) — times match server HH-MM folders ---
    sample_daytime_target: str = Field(default="09-00")
    sample_nighttime_target: str = Field(default="20-00")
    sample_twilight_target: str = Field(default="14-00")
    sample_tolerance_minutes: int = Field(default=30)
    sample_nearest_fallback: bool = Field(
        default=True,
        description=(
            "If a day/twilight/night target has no timeslot within tolerance, "
            "still pick the nearest remaining file on that date so sparse days "
            "are not left empty."
        ),
    )
    sample_files_per_date: int = Field(
        default=3,
        description="Named constant for files sampled per date (default: daytime+night+twilight)",
    )
    download_everything_per_date: bool = Field(
        default=False,
        description="Off-by-default toggle to download every timeslot for a date",
    )

    # --- Download safety (BUILDPLAN §12 / §13) ---
    max_concurrent_downloads: int = Field(default=4, ge=1, le=16)
    min_request_delay_seconds: float = Field(default=0.25, ge=0.0)
    download_chunk_mb: int = Field(default=4, ge=1, le=32)
    min_free_disk_gb: float = Field(default=10.0)

    # --- Throughput ---
    discovery_workers: int = Field(default=8, ge=1, le=32)
    processing_workers: int = Field(default=2, ge=1, le=4)
    processing_threads_per_worker: int = Field(default=3, ge=1, le=16)
    composite_batch_size: int = Field(default=8, ge=1, le=32)
    png_compress_level: int = Field(default=1, ge=0, le=9)
    job_progress_min_interval_seconds: float = Field(default=2.0, ge=0.0)

    # --- Ports ---
    backend_port: int = Field(default=8000)
    frontend_port: int = Field(default=3000)

    # --- CORS ---
    frontend_origin: str = Field(default="http://127.0.0.1:3000")

    @property
    def raw_dir(self) -> Path:
        return self.data_root / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.data_root / "processed"

    @property
    def thumbnails_dir(self) -> Path:
        return self.data_root / "thumbnails"

    @property
    def db_path(self) -> Path:
        return self.data_root / "catalog.sqlite3"

    @property
    def archive_url(self) -> str:
        base = self.archive_base_url.rstrip("/") + "/"
        route = self.archive_route.strip("/")
        return f"{base}{route}/"

    def ensure_data_dirs(self) -> None:
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        self.thumbnails_dir.mkdir(parents=True, exist_ok=True)
        self.data_root.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    # Resolve relative DATA_ROOT against project root (not the process CWD)
    if not settings.data_root.is_absolute():
        settings.data_root = (PROJECT_ROOT / settings.data_root).resolve()
    else:
        settings.data_root = settings.data_root.resolve()
    return settings
