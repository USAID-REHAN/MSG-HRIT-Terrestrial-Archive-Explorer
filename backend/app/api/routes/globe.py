"""Product-level globe catalog, lazy generation, status, and PNG serving."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import GlobeCatalogOut, GlobeProductOut, ProductRefOut
from app.config import get_settings
from app.db.models import Product, ProductReference, Timeslot
from app.db.session import get_db
from app.processing.globe_layers import ELIGIBLE_GLOBE_PRODUCTS
from app.processing.globe_manager import (
    GlobeGenerationRequest,
    GlobeState,
    globe_generation_manager,
    validate_globe_artifact,
)

router = APIRouter(tags=["globe"])


def _resolve_product(
    product_id: int, db: Session
) -> tuple[Product, Timeslot, ProductReference | None]:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(404, "Product not found")
    timeslot = db.get(Timeslot, product.timeslot_id)
    if timeslot is None:
        raise HTTPException(404, "Product timeslot not found")
    reference = db.get(ProductReference, product.product_name)
    return product, timeslot, reference


def _request(product: Product, timeslot: Timeslot) -> GlobeGenerationRequest:
    return GlobeGenerationRequest(
        product_id=product.id,
        product_name=product.product_name,
        availability_status=product.availability_status,
        product_error=product.error_message,
        native_path=Path(timeslot.local_raw_path) if timeslot.local_raw_path else None,
        year=timeslot.year,
        date=timeslot.date,
        time=timeslot.time,
    )


def _response(
    product: Product,
    state: GlobeState,
    reference: ProductReference | None,
) -> GlobeProductOut:
    return GlobeProductOut(
        product_id=product.id,
        timeslot_id=product.timeslot_id,
        product_name=product.product_name,
        product_kind=product.product_kind,
        availability_status=product.availability_status,
        generation_status=state.status,
        image_url=(
            f"/api/globe-products/{product.id}/image"
            if state.status == "ready"
            else None
        ),
        metadata=state.metadata,
        error=state.error,
        reference=(
            ProductRefOut.model_validate(reference) if reference is not None else None
        ),
    )


@router.get(
    "/timeslots/{timeslot_id}/globe-products", response_model=GlobeCatalogOut
)
def globe_product_catalog(
    timeslot_id: int, db: Session = Depends(get_db)
) -> GlobeCatalogOut:
    timeslot = db.get(Timeslot, timeslot_id)
    if timeslot is None:
        raise HTTPException(404, "Timeslot not found")
    products = list(
        db.execute(
            select(Product)
            .where(
                Product.timeslot_id == timeslot_id,
                Product.product_name.in_(ELIGIBLE_GLOBE_PRODUCTS),
            )
            .order_by(Product.id)
        )
        .scalars()
        .all()
    )
    references = {
        reference.product_name: reference
        for reference in db.execute(
            select(ProductReference).where(
                ProductReference.product_name.in_(ELIGIBLE_GLOBE_PRODUCTS)
            )
        )
        .scalars()
        .all()
    }
    settings = get_settings()
    return GlobeCatalogOut(
        timeslot_id=timeslot_id,
        products=[
            _response(
                product,
                globe_generation_manager.status(
                    _request(product, timeslot), settings
                ),
                references.get(product.product_name),
            )
            for product in products
        ],
    )


@router.post(
    "/globe-products/{product_id}/generate",
    response_model=GlobeProductOut,
    status_code=202,
)
def generate_globe_product(
    product_id: int, db: Session = Depends(get_db)
) -> GlobeProductOut:
    product, timeslot, reference = _resolve_product(product_id, db)
    if product.product_name not in ELIGIBLE_GLOBE_PRODUCTS:
        raise HTTPException(400, "Product is not eligible for globe output")
    state = globe_generation_manager.start(
        _request(product, timeslot), get_settings()
    )
    if state.status == "busy":
        raise HTTPException(503, state.error)
    return _response(product, state, reference)


@router.get(
    "/globe-products/{product_id}/status", response_model=GlobeProductOut
)
def globe_product_status(
    product_id: int, db: Session = Depends(get_db)
) -> GlobeProductOut:
    product, timeslot, reference = _resolve_product(product_id, db)
    if product.product_name not in ELIGIBLE_GLOBE_PRODUCTS:
        raise HTTPException(400, "Product is not eligible for globe output")
    state = globe_generation_manager.status(
        _request(product, timeslot), get_settings()
    )
    return _response(product, state, reference)


@router.get("/globe-products/{product_id}/image")
def serve_globe_product(
    product_id: int, db: Session = Depends(get_db)
) -> FileResponse:
    product, timeslot, _ = _resolve_product(product_id, db)
    if product.product_name not in ELIGIBLE_GLOBE_PRODUCTS:
        raise HTTPException(404, "Globe product not found")
    request = _request(product, timeslot)
    state = globe_generation_manager.status(request, get_settings())
    if state.status != "ready":
        status_code = 409 if state.status in {"generating", "unavailable_night", "error"} else 404
        raise HTTPException(status_code, state.error or "Globe PNG is not ready")
    try:
        png, _ = validate_globe_artifact(get_settings(), request)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(404, str(exc)) from exc
    return FileResponse(png, media_type="image/png", filename=f"{product.product_name}.png")
