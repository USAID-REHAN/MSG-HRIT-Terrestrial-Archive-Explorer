"""Browse timeslots / products / reference / dashboard / image serving."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.api.connectivity import check_archive_connectivity
from app.api.schemas import (
    ComparePanel,
    CompareResponse,
    ConnectivityStatus,
    DashboardStats,
    DiskUsageBreakdown,
    JobOut,
    MapEnsureResult,
    MapViewConfig,
    ProductOut,
    ProductRefOut,
    TimeslotOut,
)
from app.config import get_settings
from app.db.models import Job, Product, ProductReference, Timeslot
from app.db.session import get_db
from app.disk_usage import peek_disk_usage, request_disk_usage_refresh
from app.downloader.worker import free_disk_gb
from app.processing.map_layers import (
    map_bounds_wgs84,
    map_leaflet_bounds,
    map_path_for_image,
)
from app.processing.map_overlay_manager import MapOverlayRequest, map_overlay_manager
from app.processing.pipeline import EXPECTED_PRODUCTS, MIN_GENERATED_FOR_SUCCESS
from app.processing.reader import CHANNEL_NAMES, COMPOSITE_NAMES
from app.sampling.selector import ROLES, sample_match_info

router = APIRouter(tags=["browse"])


def _annotate_timeslot(ts: Timeslot, item: TimeslotOut) -> TimeslotOut:
    info = sample_match_info(ts.sample_role, ts.time)
    item.sample_target_time = info["sample_target_time"]
    item.sample_match = info["sample_match"]
    item.sample_offset_minutes = info["sample_offset_minutes"]
    item.sample_note = info["sample_note"]
    return item


def _product_urls(p: Product) -> ProductOut:
    data = ProductOut.model_validate(p)
    if p.local_image_path:
        data.image_url = f"/api/images/{p.id}"
        map_file = map_path_for_image(p.local_image_path)
        if map_file.exists():
            data.map_image_url = f"/api/map-images/{p.id}"
            data.has_map_overlay = True
        else:
            data.has_map_overlay = False
    if p.local_thumbnail_path:
        data.thumbnail_url = f"/api/thumbnails/{p.id}"
    return data


@router.get("/dashboard", response_model=DashboardStats)
def dashboard(db: Session = Depends(get_db)):
    settings = get_settings()

    discovered_total = db.execute(select(func.count()).select_from(Timeslot)).scalar_one()
    selected_total = db.execute(
        select(func.count())
        .select_from(Timeslot)
        .where(Timeslot.sample_role.is_not(None))
    ).scalar_one()
    downloaded_total = db.execute(
        select(func.count())
        .select_from(Timeslot)
        .where(
            Timeslot.sample_role.is_not(None),
            Timeslot.download_status == "downloaded",
        )
    ).scalar_one()
    failed_downloads = db.execute(
        select(func.count())
        .select_from(Timeslot)
        .where(
            Timeslot.sample_role.is_not(None),
            Timeslot.download_status == "failed",
        )
    ).scalar_one()

    discovered_bytes = int(
        db.execute(
            select(func.coalesce(func.sum(Timeslot.server_reported_size_bytes), 0))
        ).scalar_one()
        or 0
    )
    selected_bytes = int(
        db.execute(
            select(func.coalesce(func.sum(Timeslot.server_reported_size_bytes), 0)).where(
                Timeslot.sample_role.is_not(None)
            )
        ).scalar_one()
        or 0
    )

    # Prefer CASE for portability (SQLite/Postgres)
    product_stats = db.execute(
        select(
            Product.timeslot_id,
            func.count().label("n"),
            func.sum(
                case(
                    (Product.availability_status == "unavailable_error", 1),
                    else_=0,
                )
            ).label("err"),
        )
        .where(
            Product.timeslot_id.in_(
                select(Timeslot.id).where(
                    Timeslot.sample_role.is_not(None),
                    Timeslot.download_status == "downloaded",
                )
            )
        )
        .group_by(Product.timeslot_id)
    ).all()
    processed = sum(
        1
        for _tid, n, err in product_stats
        if int(n or 0) >= EXPECTED_PRODUCTS and int(err or 0) == 0
    )

    active = (
        db.execute(
            select(Job)
            .where(Job.status.in_(["queued", "running", "paused"]))
            .order_by(Job.id.desc())
            .limit(10)
        )
        .scalars()
        .all()
    )

    # Never walk the filesystem here — that saturates disk I/O and stalls the UI.
    # Raw size comes from DB; full breakdown is filled by GET /api/disk-usage later.
    disk = peek_disk_usage()
    free_gb = round(free_disk_gb(settings.data_root), 2)
    raw_from_db = int(
        db.execute(
            select(func.coalesce(func.sum(Timeslot.server_reported_size_bytes), 0)).where(
                Timeslot.sample_role.is_not(None),
                Timeslot.download_status == "downloaded",
            )
        ).scalar_one()
        or 0
    )

    if disk is not None:
        breakdown = DiskUsageBreakdown(
            raw_bytes=disk.raw_bytes,
            processed_bytes=disk.processed_bytes,
            thumbnails_bytes=disk.thumbnails_bytes,
            catalog_bytes=disk.catalog_bytes,
            total_bytes=disk.total_bytes,
            free_gb=disk.free_gb if disk.free_gb else free_gb,
        )
        raw_bytes = disk.raw_bytes
        used_gb = round(disk.total_bytes / (1024**3), 2)
        free_gb = breakdown.free_gb
    else:
        breakdown = None
        raw_bytes = raw_from_db
        used_gb = round(raw_from_db / (1024**3), 2)

    return DashboardStats(
        discovered_total=discovered_total,
        selected_total=selected_total,
        downloaded_total=downloaded_total,
        failed_downloads=failed_downloads,
        processed_timeslots=processed,
        discovered_bytes=discovered_bytes,
        selected_bytes=selected_bytes,
        downloaded_bytes_on_disk=raw_bytes,
        disk_free_gb=free_gb,
        disk_used_data_gb=used_gb,
        disk_breakdown=breakdown,
        date_min=db.execute(select(func.min(Timeslot.date))).scalar_one(),
        date_max=db.execute(select(func.max(Timeslot.date))).scalar_one(),
        active_jobs=[JobOut.model_validate(j) for j in active],
        config_snapshot={
            "archive_url": settings.archive_url,
            "sample_daytime_target": settings.sample_daytime_target,
            "sample_nighttime_target": settings.sample_nighttime_target,
            "sample_twilight_target": settings.sample_twilight_target,
            "sample_tolerance_minutes": settings.sample_tolerance_minutes,
            "sample_nearest_fallback": settings.sample_nearest_fallback,
            "sample_files_per_date": settings.sample_files_per_date,
            "download_everything_per_date": settings.download_everything_per_date,
            "max_concurrent_downloads": settings.max_concurrent_downloads,
            "min_request_delay_seconds": settings.min_request_delay_seconds,
            "min_free_disk_gb": settings.min_free_disk_gb,
        },
        archive_reachable=None,
        archive_latency_ms=None,
        archive_check_error=None,
    )


@router.get("/disk-usage", response_model=DiskUsageBreakdown)
def disk_usage(refresh: bool = Query(True)):
    """
    Optional heavy endpoint — walks data/ in a background thread.
    Dashboard must not call this on the critical first-paint path.
    """
    settings = get_settings()
    if refresh:
        snap = request_disk_usage_refresh(settings)
    else:
        snap = peek_disk_usage()
    if snap is None:
        # Kick refresh and return a cheap DB-free placeholder
        request_disk_usage_refresh(settings)
        free = round(free_disk_gb(settings.data_root), 2)
        return DiskUsageBreakdown(
            raw_bytes=0,
            processed_bytes=0,
            thumbnails_bytes=0,
            catalog_bytes=0,
            total_bytes=0,
            free_gb=free,
        )
    return DiskUsageBreakdown(
        raw_bytes=snap.raw_bytes,
        processed_bytes=snap.processed_bytes,
        thumbnails_bytes=snap.thumbnails_bytes,
        catalog_bytes=snap.catalog_bytes,
        total_bytes=snap.total_bytes,
        free_gb=snap.free_gb,
    )


@router.get("/connectivity", response_model=ConnectivityStatus)
def connectivity():
    """Archive server reachability badge — HEAD/GET of the listing root only."""
    return check_archive_connectivity(timeout_seconds=1.2)


@router.get("/compare", response_model=CompareResponse)
def compare_roles(
    date: str = Query(..., description="YYYY-MM-DD"),
    product: str = Query("natural_color", description="Channel or composite name"),
    db: Session = Depends(get_db),
):
    """
    Same date, same product, daytime / twilight / nighttime side by side.
    Additive browse helper — does not alter timeslot or product records.
    """
    available = list(CHANNEL_NAMES) + list(COMPOSITE_NAMES)
    if product not in available:
        raise HTTPException(
            400,
            f"Unknown product '{product}'. Expected one of the 12 channels or composites.",
        )

    role_order = list(ROLES)  # daytime, twilight, nighttime (selector order)
    # Prefer explicit day→twilight→night presentation for the compare UI
    preferred = ["daytime", "twilight", "nighttime"]
    roles = [r for r in preferred if r in role_order] or preferred

    sampled = list(
        db.execute(
            select(Timeslot).where(
                Timeslot.date == date,
                Timeslot.sample_role.is_not(None),
            )
        )
        .scalars()
        .all()
    )
    by_role = {t.sample_role: t for t in sampled if t.sample_role}

    refs = {
        r.product_name: r
        for r in db.execute(select(ProductReference)).scalars().all()
    }

    panels: list[ComparePanel] = []
    for role in roles:
        ts = by_role.get(role)
        if ts is None:
            panels.append(
                ComparePanel(
                    role=role,
                    missing_reason=f"No {role} sample selected for {date}",
                )
            )
            continue

        ts_out = _annotate_timeslot(ts, TimeslotOut.model_validate(ts))
        prod = db.execute(
            select(Product).where(
                Product.timeslot_id == ts.id,
                Product.product_name == product,
            )
        ).scalar_one_or_none()

        if prod is None:
            panels.append(
                ComparePanel(
                    role=role,
                    timeslot=ts_out,
                    missing_reason=(
                        "Product not processed yet — download and process this "
                        "timeslot first"
                        if ts.download_status != "downloaded"
                        else "Product row missing — re-run processing"
                    ),
                )
            )
            continue

        po = _product_urls(prod)
        ref = refs.get(prod.product_name)
        if ref:
            po.reference = ProductRefOut.model_validate(ref)
        panels.append(ComparePanel(role=role, timeslot=ts_out, product=po))

    return CompareResponse(
        date=date,
        product_name=product,
        panels=panels,
        available_products=available,
    )


@router.get("/timeslots", response_model=list[TimeslotOut])
def list_timeslots(
    date: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    sample_role: str | None = None,
    download_status: str | None = None,
    sampled_only: bool = False,
    limit: int = Query(200, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    q = select(Timeslot)
    if date:
        q = q.where(Timeslot.date == date)
    if date_from:
        q = q.where(Timeslot.date >= date_from)
    if date_to:
        q = q.where(Timeslot.date <= date_to)
    if sample_role:
        q = q.where(Timeslot.sample_role == sample_role)
    if download_status:
        q = q.where(Timeslot.download_status == download_status)
    if sampled_only:
        q = q.where(Timeslot.sample_role.is_not(None))
    q = q.order_by(Timeslot.date, Timeslot.time).offset(offset).limit(limit)
    rows = list(db.execute(q).scalars().all())

    out: list[TimeslotOut] = []
    for ts in rows:
        n = db.execute(
            select(func.count()).select_from(Product).where(Product.timeslot_id == ts.id)
        ).scalar_one()
        gen = db.execute(
            select(func.count())
            .select_from(Product)
            .where(
                Product.timeslot_id == ts.id,
                Product.availability_status == "generated",
            )
        ).scalar_one()
        err = db.execute(
            select(func.count())
            .select_from(Product)
            .where(
                Product.timeslot_id == ts.id,
                Product.availability_status == "unavailable_error",
            )
        ).scalar_one()
        item = TimeslotOut.model_validate(ts)
        item.products_complete = (
            n >= EXPECTED_PRODUCTS
            and err == 0
            and gen >= MIN_GENERATED_FOR_SUCCESS
        )
        item.products_generated = gen
        out.append(_annotate_timeslot(ts, item))
    return out


@router.get("/timeslots/{timeslot_id}")
def get_timeslot(timeslot_id: int, db: Session = Depends(get_db)):
    ts = db.get(Timeslot, timeslot_id)
    if ts is None:
        raise HTTPException(404, "Timeslot not found")

    products = list(
        db.execute(select(Product).where(Product.timeslot_id == timeslot_id))
        .scalars()
        .all()
    )
    refs = {
        r.product_name: r
        for r in db.execute(select(ProductReference)).scalars().all()
    }

    product_out = []
    for p in products:
        po = _product_urls(p)
        ref = refs.get(p.product_name)
        if ref:
            po.reference = ProductRefOut.model_validate(ref)
        product_out.append(po)

    # Sibling sample roles on same date for prev/next navigation
    siblings = list(
        db.execute(
            select(Timeslot)
            .where(Timeslot.date == ts.date, Timeslot.sample_role.is_not(None))
            .order_by(Timeslot.time)
        )
        .scalars()
        .all()
    )
    role_order = {r: i for i, r in enumerate(ROLES)}
    siblings_sorted = sorted(
        siblings, key=lambda s: role_order.get(s.sample_role or "", 99)
    )

    ts_out = TimeslotOut.model_validate(ts)
    n = len(products)
    gen = sum(1 for p in products if p.availability_status == "generated")
    err = sum(1 for p in products if p.availability_status == "unavailable_error")
    ts_out.products_complete = (
        n >= EXPECTED_PRODUCTS and err == 0 and gen >= MIN_GENERATED_FOR_SUCCESS
    )
    ts_out.products_generated = gen
    _annotate_timeslot(ts, ts_out)

    return {
        "timeslot": ts_out,
        "products": product_out,
        "siblings": [
            _annotate_timeslot(s, TimeslotOut.model_validate(s)) for s in siblings_sorted
        ],
    }


@router.get("/reference", response_model=list[ProductRefOut])
def list_reference(db: Session = Depends(get_db)):
    rows = list(db.execute(select(ProductReference)).scalars().all())
    kind_rank = {"channel": 0, "composite": 1}
    channel_order = {n: i for i, n in enumerate(CHANNEL_NAMES)}
    composite_order = {n: i for i, n in enumerate(COMPOSITE_NAMES)}

    def sort_key(r: ProductReference):
        if r.product_kind == "channel":
            return (0, channel_order.get(r.product_name, 99))
        return (1, composite_order.get(r.product_name, 999))

    rows.sort(key=sort_key)
    return rows


@router.get("/images/{product_id}")
def serve_image(product_id: int, db: Session = Depends(get_db)):
    p = db.get(Product, product_id)
    if p is None or not p.local_image_path:
        raise HTTPException(404, "Image not found")
    path = Path(p.local_image_path)
    if not path.exists():
        raise HTTPException(404, "Image file missing on disk")
    return FileResponse(path, media_type="image/png")


@router.get("/thumbnails/{product_id}")
def serve_thumbnail(product_id: int, db: Session = Depends(get_db)):
    p = db.get(Product, product_id)
    if p is None or not p.local_thumbnail_path:
        raise HTTPException(404, "Thumbnail not found")
    path = Path(p.local_thumbnail_path)
    if not path.exists():
        raise HTTPException(404, "Thumbnail file missing on disk")
    return FileResponse(path, media_type="image/png")


@router.get("/map-view", response_model=MapViewConfig)
def map_view_config():
    """Pakistan-focused Web Mercator configuration for the Dynamic Image viewer."""
    b = map_bounds_wgs84()
    return MapViewConfig(
        crs=b["crs"],
        projection=b["projection"],
        west=b["west"],
        south=b["south"],
        east=b["east"],
        north=b["north"],
        center_lat=b["center_lat"],
        center_lon=b["center_lon"],
        default_zoom=int(b["default_zoom"]),
        leaflet_bounds=map_leaflet_bounds(),
    )


@router.get("/map-images/{product_id}")
def serve_map_image(product_id: int, db: Session = Depends(get_db)):
    p = db.get(Product, product_id)
    if p is None or not p.local_image_path:
        raise HTTPException(404, "Map overlay not found")
    path = map_path_for_image(p.local_image_path)
    if not path.exists():
        raise HTTPException(
            404,
            "Map overlay not generated yet — call POST /api/map-images/{id}/ensure",
        )
    return FileResponse(path, media_type="image/png")


def _map_overlay_request(product_id: int, db: Session) -> tuple[Product, MapOverlayRequest]:
    p = db.get(Product, product_id)
    if p is None or p.availability_status != "generated" or not p.local_image_path:
        raise HTTPException(404, "Product not available for map overlay")

    ts = db.get(Timeslot, p.timeslot_id)
    if ts is None or not ts.local_raw_path:
        raise HTTPException(404, "Timeslot raw file not available")

    return p, MapOverlayRequest(
        product_id=product_id,
        product_name=p.product_name,
        product_kind=p.product_kind,
        local_image_path=p.local_image_path,
        native_path=Path(ts.local_raw_path),
        date=ts.date,
        time=ts.time,
    )


def _map_ensure_result(product_id: int, state) -> MapEnsureResult:
    ready = state.status == "ready" and bool(state.map_image_url)
    return MapEnsureResult(
        ok=ready,
        product_id=product_id,
        status=state.status,
        map_image_url=state.map_image_url,
        error=state.error,
    )


@router.post("/map-images/{product_id}/ensure", response_model=MapEnsureResult)
def ensure_map_image(product_id: int, db: Session = Depends(get_db)):
    """
    Queue (or return) a Pakistan-Mercator RGBA overlay.

    Non-blocking: satpy resample runs in a single background worker. Poll
    GET /api/map-images/{id}/status until status is ready or error.
    """
    _, request = _map_overlay_request(product_id, db)
    state = map_overlay_manager.start(request)
    return _map_ensure_result(product_id, state)


@router.get("/map-images/{product_id}/status", response_model=MapEnsureResult)
def map_image_status(product_id: int, db: Session = Depends(get_db)):
    """Poll Mercator overlay readiness without starting a new job."""
    _, request = _map_overlay_request(product_id, db)
    state = map_overlay_manager.status(request)
    return _map_ensure_result(product_id, state)
