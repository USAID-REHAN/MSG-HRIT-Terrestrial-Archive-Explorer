"""Focused tests for the additive product-level globe API and manager."""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.routes import globe
from app.config import Settings
from app.db.models import Base, Product, ProductReference, Timeslot
from app.db.session import get_db
from app.processing import globe_manager
from app.processing.globe_layers import GLOBE_LAYER_VERSION, globe_output_paths
from app.processing.globe_manager import (
    GlobeGenerationManager,
    GlobeGenerationRequest,
)


def _metadata(product: str, width: int = 8, height: int = 6) -> dict:
    return {
        "version": GLOBE_LAYER_VERSION,
        "product": product,
        "bounds": {
            "west": 20.0,
            "south": -30.0,
            "east": 70.0,
            "north": 30.0,
            "semantics": "pixel_edges",
        },
        "dimensions": {"width": width, "height": height},
    }


def _write_artifact(settings: Settings, request: GlobeGenerationRequest) -> None:
    png, sidecar = globe_output_paths(
        settings.processed_dir,
        year=request.year,
        date=request.date,
        time=request.time,
        product=request.product_name,
    )
    png.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (8, 6), (1, 2, 3, 255)).save(png, format="PNG")
    sidecar.write_text(json.dumps(_metadata(request.product_name)), encoding="utf-8")


def _request(product_id: int = 1) -> GlobeGenerationRequest:
    return GlobeGenerationRequest(
        product_id=product_id,
        product_name="VIS006",
        availability_status="generated",
        product_error=None,
        native_path=None,
        year="2020",
        date="2020-06-01",
        time="09-00",
    )


def test_manager_deduplicates_background_generation(tmp_path, monkeypatch):
    settings = Settings(data_root=tmp_path)
    request = GlobeGenerationRequest(
        **{**_request().__dict__, "native_path": tmp_path / "source.nat"}
    )
    started = threading.Event()
    release = threading.Event()
    calls: list[int] = []

    def fake_generate(**_kwargs):
        calls.append(request.product_id)
        started.set()
        assert release.wait(timeout=2)
        _write_artifact(settings, request)

    monkeypatch.setattr(globe_manager, "generate_globe_layer", fake_generate)
    manager = GlobeGenerationManager(max_workers=1, max_pending=1)
    try:
        assert manager.start(request, settings).status == "generating"
        assert started.wait(timeout=2)
        assert manager.start(request, settings).status == "generating"
        assert calls == [request.product_id]
        release.set()
        deadline = time.monotonic() + 2
        while manager.status(request, settings).status == "generating":
            assert time.monotonic() < deadline
            time.sleep(0.01)
        state = manager.status(request, settings)
        assert state.status == "ready"
        assert state.metadata == _metadata("VIS006")
    finally:
        release.set()
        manager.shutdown()


def test_catalog_reports_reference_sidecar_and_unavailable_night_and_serves_png(
    tmp_path, monkeypatch
):
    settings = Settings(data_root=tmp_path)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        timeslot = Timeslot(
            year="2020",
            date="2020-06-01",
            time="09-00",
            server_relative_path="2020/2020-06-01/09-00/source.nat",
            download_status="downloaded",
            local_raw_path=str(tmp_path / "source.nat"),
            discovered_at=datetime(2020, 6, 1),
        )
        db.add(timeslot)
        db.flush()
        ready = Product(
            timeslot_id=timeslot.id,
            product_name="VIS006",
            product_kind="channel",
            availability_status="generated",
        )
        night = Product(
            timeslot_id=timeslot.id,
            product_name="VIS008",
            product_kind="channel",
            availability_status="unavailable_night",
            error_message="No reflected sunlight",
        )
        db.add_all([ready, night])
        db.add(
            ProductReference(
                product_name="VIS006",
                product_kind="channel",
                wavelength_or_spectral_band="0.6 µm",
                approximate_resolution="3 km",
                plain_language_description="Visible cloud and land imagery.",
                agriculture_application="Crop monitoring.",
                aviation_application="Cloud monitoring.",
                natural_resource_application="Surface monitoring.",
                disaster_response_application="Smoke monitoring.",
            )
        )
        db.commit()
        timeslot_id = timeslot.id
        ready_id = ready.id

    ready_request = _request(ready_id)
    _write_artifact(settings, ready_request)
    monkeypatch.setattr(globe, "get_settings", lambda: settings)

    def override_db():
        with Session(engine) as db:
            yield db

    app = FastAPI()
    app.include_router(globe.router, prefix="/api")
    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)

    response = client.get(f"/api/timeslots/{timeslot_id}/globe-products")
    assert response.status_code == 200
    products = {item["product_name"]: item for item in response.json()["products"]}
    assert products["VIS006"]["generation_status"] == "ready"
    assert products["VIS006"]["metadata"] == _metadata("VIS006")
    assert products["VIS006"]["reference"]["agriculture_application"] == "Crop monitoring."
    assert products["VIS008"]["generation_status"] == "unavailable_night"
    assert products["VIS008"]["error"] == "No reflected sunlight"

    image = client.get(f"/api/globe-products/{ready_id}/image")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"

    malformed = _metadata("VIS006")
    malformed["dimensions"]["width"] = 99
    _, sidecar = globe_output_paths(
        settings.processed_dir,
        year="2020",
        date="2020-06-01",
        time="09-00",
        product="VIS006",
    )
    sidecar.write_text(json.dumps(malformed), encoding="utf-8")
    status = client.get(f"/api/globe-products/{ready_id}/status")
    assert status.json()["generation_status"] == "error"
    assert "dimensions" in status.json()["error"]
    assert client.get(f"/api/globe-products/{ready_id}/image").status_code == 409
