"""SQLite schema — timeslots, products, product_reference, jobs (BUILDPLAN §9)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Timeslot(Base):
    __tablename__ = "timeslots"
    __table_args__ = (
        UniqueConstraint("year", "date", "time", name="uq_timeslot_ydt"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    year: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    date: Mapped[str] = mapped_column(String(16), nullable=False, index=True)  # YYYY-MM-DD
    time: Mapped[str] = mapped_column(String(8), nullable=False)  # HH-MM
    server_relative_path: Mapped[str] = mapped_column(String(512), nullable=False)
    server_reported_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    sample_role: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, index=True
    )  # daytime | nighttime | twilight | null
    download_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="discovered", index=True
    )  # discovered → queued → downloading → downloaded → failed
    local_raw_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    downloaded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    products: Mapped[list["Product"]] = relationship(back_populates="timeslot")


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("timeslot_id", "product_name", name="uq_product_timeslot_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timeslot_id: Mapped[int] = mapped_column(ForeignKey("timeslots.id"), nullable=False, index=True)
    product_name: Mapped[str] = mapped_column(String(64), nullable=False)
    product_kind: Mapped[str] = mapped_column(String(32), nullable=False)  # channel | composite
    availability_status: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # generated | unavailable_night | unavailable_error
    local_image_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    local_thumbnail_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    timeslot: Mapped["Timeslot"] = relationship(back_populates="products")


class ProductReference(Base):
    __tablename__ = "product_reference"

    product_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    product_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    wavelength_or_spectral_band: Mapped[str] = mapped_column(String(128), nullable=False)
    approximate_resolution: Mapped[str] = mapped_column(String(64), nullable=False)
    plain_language_description: Mapped[str] = mapped_column(Text, nullable=False)
    agriculture_application: Mapped[str] = mapped_column(Text, nullable=False)
    aviation_application: Mapped[str] = mapped_column(Text, nullable=False)
    natural_resource_application: Mapped[str] = mapped_column(Text, nullable=False)
    disaster_response_application: Mapped[str] = mapped_column(Text, nullable=False)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_type: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )  # discovery | sampling | download | processing
    scope: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="queued", index=True
    )  # queued | running | completed | failed | paused
    progress_current: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    log_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
