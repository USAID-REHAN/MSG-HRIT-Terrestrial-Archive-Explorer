"""Focused tests for scientifically georeferenced SEVIRI globe overlays."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr
from PIL import Image
from pyresample.geometry import AreaDefinition, StackedAreaDefinition

from app.processing import globe_layers


def _source_area(lons: np.ndarray | None = None, lats: np.ndarray | None = None):
    if lons is None:
        lons = np.array(
            [
                [np.nan, 42.0, 48.0, np.nan],
                [40.0, 44.0, 46.0, 50.0],
                [np.nan, 42.0, 48.0, np.nan],
            ]
        )
    if lats is None:
        lats = np.array(
            [
                [np.nan, 5.0, 5.0, np.nan],
                [0.0, 0.0, 0.0, 0.0],
                [np.nan, -5.0, -5.0, np.nan],
            ]
        )
    projection = {
        "proj": "geos",
        "lon_0": 45.5,
        "h": 35785831.0,
        "a": 6378169.0,
        "b": 6356583.8,
        "sweep": "y",
        "units": "m",
    }
    return AreaDefinition(
        "test_seviri",
        "Tiny synthetic SEVIRI geometry",
        "geos",
        projection,
        lons.shape[1],
        lons.shape[0],
        (-1_000_000.0, -750_000.0, 1_000_000.0, 750_000.0),
        lons=lons,
        lats=lats,
    )


def test_bounds_and_target_shape_come_from_finite_source_coordinates():
    target, bounds = globe_layers.geographic_area_for_dataset(
        _source_area(), width=100
    )

    assert bounds == {"west": 40.0, "south": -5.0, "east": 50.0, "north": 5.0}
    assert target.area_extent == (40.0, -5.0, 50.0, 5.0)
    assert (target.width, target.height) == (100, 100)
    assert target.crs.to_epsg() == 4326


def test_antimeridian_crossing_geometry_is_rejected():
    lons = np.array([[170.0, 175.0], [-179.0, -175.0]])
    lats = np.array([[5.0, 5.0], [-5.0, -5.0]])
    area = _source_area(lons, lats)

    with pytest.raises(ValueError, match="antimeridian"):
        globe_layers.geographic_bounds_from_area(area)


def test_only_standard_channels_and_five_composites_are_eligible():
    assert globe_layers.ELIGIBLE_GLOBE_PRODUCTS == frozenset(
        globe_layers.CHANNEL_NAMES
    ) | {"natural_color", "airmass", "dust", "ash", "convection"}
    assert "overview" not in globe_layers.ELIGIBLE_GLOBE_PRODUCTS
    assert "night_microphysics" not in globe_layers.ELIGIBLE_GLOBE_PRODUCTS


def test_hrv_stacked_area_is_aggregated_on_its_native_grid():
    projection = {
        "proj": "geos",
        "lon_0": 45.5,
        "h": 35785831.0,
        "a": 6378169.0,
        "b": 6356583.8,
        "sweep": "y",
        "units": "m",
    }
    upper = AreaDefinition(
        "hrv_upper",
        "HRV upper window",
        "geos",
        projection,
        6,
        3,
        (-3_000.0, 0.0, 3_000.0, 3_000.0),
    )
    lower = AreaDefinition(
        "hrv_lower",
        "HRV lower window",
        "geos",
        projection,
        6,
        3,
        (-3_000.0, -3_000.0, 3_000.0, 0.0),
    )
    source = xr.DataArray(
        np.arange(36, dtype=np.float32).reshape(6, 6),
        dims=("y", "x"),
        attrs={"area": StackedAreaDefinition(upper, lower)},
    )

    aggregated = globe_layers._aggregate_hrv_native_grid(source)

    assert aggregated.shape == (2, 2)
    assert isinstance(aggregated.attrs["area"], StackedAreaDefinition)
    assert aggregated.attrs["area"].shape == (2, 2)
    np.testing.assert_allclose(
        aggregated.values,
        np.array([[7.0, 10.0], [25.0, 28.0]], dtype=np.float32),
    )


class _Scene:
    def __init__(self, source_dataset, remapped_dataset):
        self.source_dataset = source_dataset
        self.remapped_dataset = remapped_dataset
        self.resample_calls = []

    def resample(self, area, **kwargs):
        self.resample_calls.append((area, kwargs))
        return {"VIS006": self.remapped_dataset}


class _Enhanced:
    def __init__(self, width: int, height: int):
        self.data = SimpleNamespace(
            attrs={"enhancement_history": [{"name": "test enhancement"}]}
        )
        self._image = Image.new("RGBA", (width, height), (10, 20, 30, 255))
        self._image.putpixel((0, 0), (0, 0, 0, 0))

    def pil_image(self, fill_value=None):
        assert fill_value is None
        return self._image


def test_generate_channel_writes_transparent_png_and_exact_sidecar(
    tmp_path, monkeypatch
):
    area = _source_area()
    source = SimpleNamespace(
        attrs={
            "area": area,
            "start_time": datetime(2020, 6, 1, 9, 0, tzinfo=timezone.utc),
        }
    )
    remapped = SimpleNamespace(attrs={})
    scene = _Scene(source, remapped)
    enhanced_calls = []

    monkeypatch.setattr(globe_layers, "load_scene", lambda *args: scene)
    monkeypatch.setattr(
        globe_layers, "resolve_dataset_name", lambda _scene, _product: "VIS006"
    )
    monkeypatch.setattr(
        globe_layers, "load_channel_dataset", lambda _scene, _name: source
    )

    import satpy.enhancements.enhancer

    def fake_enhance(dataset):
        enhanced_calls.append(dataset)
        return _Enhanced(16, 16)

    monkeypatch.setattr(
        satpy.enhancements.enhancer, "get_enhanced_image", fake_enhance
    )

    png, sidecar = globe_layers.generate_globe_layer(
        native_path=tmp_path / "msg15.nat",
        processed_dir=tmp_path / "processed",
        year="2020",
        date="2020-06-01",
        time="09-00",
        product="VIS006",
        width=16,
    )

    assert png == (
        tmp_path
        / "processed"
        / "2020"
        / "2020-06-01"
        / "09-00"
        / "globe"
        / "VIS006.png"
    )
    assert sidecar == png.with_suffix(".json")
    assert enhanced_calls == [remapped]
    assert len(scene.resample_calls) == 1
    target, kwargs = scene.resample_calls[0]
    assert kwargs == {"datasets": ["VIS006"], "resampler": "bilinear"}
    assert target.area_extent == (40.0, -5.0, 50.0, 5.0)

    with Image.open(png) as output:
        assert output.mode == "RGBA"
        assert output.size == (16, 16)
        assert output.getpixel((0, 0))[3] == 0
    metadata = json.loads(sidecar.read_text(encoding="utf-8"))
    assert metadata["bounds"] == {
        "west": 40.0,
        "south": -5.0,
        "east": 50.0,
        "north": 5.0,
        "semantics": "pixel_edges",
    }
    assert metadata["dimensions"] == {"width": 16, "height": 16}
    assert metadata["source_crs_parameters"]["lon_0"] == 45.5
    assert metadata["source_longitude_of_projection_origin"] == 45.5
    assert metadata["resampler"] == "bilinear"
    assert metadata["enhancement"]["identity"].endswith("get_enhanced_image")
    assert metadata["source_timestamp"] == "2020-06-01T09:00:00Z"
    assert metadata["version"] == globe_layers.GLOBE_LAYER_VERSION
    assert not list(png.parent.glob("*.tmp"))


def test_generate_composite_uses_composite_loader_and_satpy_enhancement(
    tmp_path, monkeypatch
):
    source = SimpleNamespace(attrs={"area": _source_area()})
    remapped = SimpleNamespace(attrs={})
    loader_calls = []

    class CompositeScene:
        def resample(self, area, **kwargs):
            assert kwargs == {"datasets": ["dust"], "resampler": "bilinear"}
            return {"dust": remapped}

    scene = CompositeScene()
    monkeypatch.setattr(globe_layers, "load_scene", lambda *args: scene)

    def fake_load_composite(received_scene, product):
        loader_calls.append((received_scene, product))
        return source

    monkeypatch.setattr(
        globe_layers, "load_composite_dataset", fake_load_composite
    )

    import satpy.enhancements.enhancer

    enhancement_calls = []

    def fake_enhance(dataset):
        enhancement_calls.append(dataset)
        return _Enhanced(12, 12)

    monkeypatch.setattr(
        satpy.enhancements.enhancer, "get_enhanced_image", fake_enhance
    )

    _, sidecar = globe_layers.generate_globe_layer(
        native_path=tmp_path / "msg15.nat",
        processed_dir=tmp_path / "processed",
        year="2020",
        date="2020-06-01",
        time="09-00",
        product="dust",
        width=12,
    )

    assert loader_calls == [(scene, "dust")]
    assert enhancement_calls == [remapped]
    metadata = json.loads(sidecar.read_text(encoding="utf-8"))
    assert metadata["product_kind"] == "composite"
    assert metadata["enhancement"]["dataset"] == "dust"


def test_bilinear_failure_is_propagated_without_algorithm_fallback(
    tmp_path, monkeypatch
):
    source = SimpleNamespace(attrs={"area": _source_area()})

    class FailingScene:
        def __init__(self):
            self.calls = []

        def resample(self, area, **kwargs):
            self.calls.append(kwargs)
            raise RuntimeError("bilinear unavailable")

    scene = FailingScene()
    monkeypatch.setattr(globe_layers, "load_scene", lambda *args: scene)
    monkeypatch.setattr(
        globe_layers, "resolve_dataset_name", lambda _scene, _product: "VIS006"
    )
    monkeypatch.setattr(
        globe_layers, "load_channel_dataset", lambda _scene, _name: source
    )

    with pytest.raises(RuntimeError, match="bilinear unavailable"):
        globe_layers.generate_globe_layer(
            native_path=tmp_path / "msg15.nat",
            processed_dir=tmp_path / "processed",
            year="2020",
            date="2020-06-01",
            time="09-00",
            product="VIS006",
            width=16,
        )

    assert scene.calls == [{"datasets": ["VIS006"], "resampler": "bilinear"}]
    assert not (tmp_path / "processed").exists()
