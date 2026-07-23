from __future__ import annotations

from concurrent.futures import Future
from contextlib import contextmanager
from datetime import datetime

import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Base, Product, Timeslot
from app.processing import composite_loader, pipeline
from app.processing.channels import render_channel_png
from app.processing.composites import render_composite_png


def _timeslot(time: str) -> Timeslot:
    return Timeslot(
        year="2026",
        date="2026-01-01",
        time=time,
        server_relative_path=f"2026/2026-01-01/{time}/msg15.nat",
        download_status="downloaded",
        discovered_at=datetime(2026, 1, 1),
    )


def test_grouped_processing_stats_and_queue_selection():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        complete = _timeslot("09-00")
        pending = _timeslot("10-00")
        failed = _timeslot("11-00")
        db.add_all([complete, pending, failed])
        db.flush()
        db.add_all(
            [
                Product(
                    timeslot_id=complete.id,
                    product_name=f"p{i}",
                    product_kind="channel",
                    availability_status="generated",
                )
                for i in range(pipeline.EXPECTED_PRODUCTS)
            ]
        )
        db.add(
            Product(
                timeslot_id=failed.id,
                product_name="bad",
                product_kind="channel",
                availability_status="unavailable_error",
            )
        )
        db.commit()

        stats = pipeline.processing_stats_by_timeslot(
            db, [complete.id, pending.id, failed.id]
        )
        assert stats[complete.id]["generated"] == pipeline.EXPECTED_PRODUCTS
        assert pending.id not in stats
        assert pipeline.timeslots_needing_processing(db) == [pending.id, failed.id]


def test_parallel_worker_accounts_for_results_and_stops_scheduling(monkeypatch, tmp_path):
    @contextmanager
    def empty_session():
        yield object()

    class ImmediatePool:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def submit(self, _fn, timeslot_id, _settings):
            future = Future()
            future.set_result(
                {
                    "ok": timeslot_id != 2,
                    "timings": {"total_seconds": float(timeslot_id)},
                }
            )
            return future

    stopped = False
    progress_values = []

    def progress(current, total, _message):
        nonlocal stopped
        progress_values.append((current, total))
        if current >= 1:
            stopped = True

    monkeypatch.setattr(pipeline, "session_scope", empty_session)
    monkeypatch.setattr(pipeline, "ProcessPoolExecutor", ImmediatePool)
    settings = Settings(
        data_root=tmp_path,
        processing_workers=2,
        processing_threads_per_worker=1,
    )
    result = pipeline.run_processing_worker(
        settings,
        progress=progress,
        stop_flag=lambda: stopped,
        only_ids=[1, 2, 3],
    )
    assert result["processed_ok"] == 1
    assert result["failed"] == 1
    assert result["stopped"] is True
    assert (2, 3) in progress_values


def test_composite_context_builds_resampled_scene_once(monkeypatch):
    class LocalScene(dict):
        def load(self, names, **_kwargs):
            for name in names:
                self[name] = f"resampled-{name}"

    class Scene(dict):
        def __init__(self):
            super().__init__()
            self.resample_calls = 0

        def load(self, _names, **_kwargs):
            pass

        def resample(self, _area):
            self.resample_calls += 1
            return LocalScene()

    scene = Scene()
    monkeypatch.setattr(composite_loader, "_ensure_ir_area", lambda _scene: object())
    context = composite_loader.CompositeLoadContext(scene)
    assert context.load("a") == "resampled-a"
    assert context.load("b") == "resampled-b"
    assert scene.resample_calls == 1


def test_fast_lossless_renderers_write_valid_images(tmp_path):
    channel = np.arange(64, dtype=np.float32).reshape(8, 8)
    rgb = np.dstack([channel / 63.0] * 3)
    channel_path = tmp_path / "channel.png"
    channel_thumb = tmp_path / "channel-thumb.png"
    composite_path = tmp_path / "composite.png"
    composite_thumb = tmp_path / "composite-thumb.png"

    render_channel_png(
        channel, "IR_108", "test", channel_path, channel_thumb, compress_level=1
    )
    render_composite_png(
        rgb, "natural_color", "test", composite_path, composite_thumb, compress_level=1
    )

    from PIL import Image

    with Image.open(channel_path) as image:
        image.verify()
    with Image.open(composite_path) as image:
        image.verify()
