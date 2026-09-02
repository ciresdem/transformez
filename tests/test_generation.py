# tests/test_generation.py

from unittest.mock import MagicMock

import numpy as np
import pytest
from pyproj import CRS

from fetchez.spatial import Region

from transformez.generation import build_shift_grid, ShiftGrid


def _mock_vertical_transform(monkeypatch, value=-0.25, uncertainty=None):
    """Patch VerticalTransform with a deterministic synthetic result."""

    instance = MagicMock()
    instance._vertical_transform.return_value = (
        np.full((10, 10), value, dtype=np.float32),
        uncertainty,
    )

    cls = MagicMock(return_value=instance)

    monkeypatch.setattr(
        "transformez.transform.VerticalTransform",
        cls,
    )

    return cls, instance


def test_build_shift_grid_returns_wgs84_shift_grid(monkeypatch):
    vt_cls, _ = _mock_vertical_transform(monkeypatch)

    grid = build_shift_grid(
        region=[-80.0, -79.0, 25.0, 26.0],
        increment="0.1",
        datum_in="EPSG:4326+3855",
        datum_out="EPSG:4326+5703",
    )

    assert isinstance(grid, ShiftGrid)
    assert grid.crs == CRS.from_epsg(4326)
    assert grid.array.shape == (10, 10)
    assert grid.source_reference.vertical is not None
    assert grid.target_reference.vertical is not None
    assert grid.source_reference.vertical.id == "epsg:3855"
    assert grid.target_reference.vertical.id == "epsg:5703"

    assert vt_cls.called

    kwargs = vt_cls.call_args.kwargs
    assert kwargs["epsg_in"] == 3855
    assert kwargs["epsg_out"] == 5703


def test_build_shift_grid_preserves_effective_epochs(monkeypatch):
    vt_cls, _ = _mock_vertical_transform(monkeypatch)

    grid = build_shift_grid(
        region=[-80.0, -79.0, 25.0, 26.0],
        increment="0.1",
        datum_in={
            "horizontal": "EPSG:4326",
            "vertical": "EPSG:3855",
            "coordinate_epoch": 2017.5,
        },
        datum_out={
            "horizontal": "EPSG:4326",
            "vertical": "EPSG:5703",
            "coordinate_epoch": 2020.0,
        },
        epoch_in="2010.0",
        epoch_out="2010.0",
    )

    assert grid.epoch_in == "2017.5"
    assert grid.epoch_out == "2020.0"

    kwargs = vt_cls.call_args.kwargs
    assert kwargs["epoch_in"] == "2017.5"
    assert kwargs["epoch_out"] == "2020.0"

    assert grid.provenance["TRANSFORMEZ_EPOCH_IN"] == "2017.5"
    assert grid.provenance["TRANSFORMEZ_EPOCH_OUT"] == "2020.0"


def test_build_shift_grid_keeps_uncertainty(monkeypatch):
    uncertainty = np.full((10, 10), 0.05, dtype=np.float32)

    _mock_vertical_transform(
        monkeypatch,
        value=-0.25,
        uncertainty=uncertainty,
    )

    grid = build_shift_grid(
        region=[-80.0, -79.0, 25.0, 26.0],
        increment="0.1",
        datum_in="EPSG:4326+3855",
        datum_out="EPSG:4326+5703",
    )

    assert grid.uncertainty is not None
    np.testing.assert_array_equal(grid.uncertainty, uncertainty)


def test_identical_generation_requests_have_same_key(monkeypatch):
    _mock_vertical_transform(monkeypatch)

    kwargs = dict(
        region=[-80.0, -79.0, 25.0, 26.0],
        increment="0.1",
        datum_in="EPSG:4326+3855",
        datum_out="EPSG:4326+5703",
        epoch_in="2010.0",
        epoch_out="2020.0",
        decay_distance_m=5000.0,
        buffer_distance_m=250.0,
    )

    a = build_shift_grid(**kwargs)
    b = build_shift_grid(**kwargs)

    assert a.generation_key == b.generation_key


@pytest.mark.parametrize(
    "override",
    [
        {"increment": "0.05"},
        {"epoch_in": "2015.0"},
        {"epoch_out": "2025.0"},
        {"decay_pixels": 200},
        {"decay_distance_m": 10000.0},
        {"buffer_distance_m": 500.0},
        {"max_vdatum_extension_m": 1000.0},
        {"extrapolate_inland": True},
        {"use_stations": True},
    ],
)
def test_generation_key_changes_with_generation_options(
    monkeypatch,
    override,
):
    _mock_vertical_transform(monkeypatch)

    base_kwargs = dict(
        region=[-80.0, -79.0, 25.0, 26.0],
        increment="0.1",
        datum_in="EPSG:4326+3855",
        datum_out="EPSG:4326+5703",
        epoch_in="2010.0",
        epoch_out="2020.0",
        decay_pixels=100,
        decay_distance_m=5000.0,
        buffer_distance_m=250.0,
        max_vdatum_extension_m=None,
        extrapolate_inland=False,
        use_stations=False,
    )

    base = build_shift_grid(**base_kwargs)

    changed_kwargs = {**base_kwargs, **override}
    changed = build_shift_grid(**changed_kwargs)

    assert base.generation_key != changed.generation_key


def test_generation_key_changes_with_region(monkeypatch):
    _mock_vertical_transform(monkeypatch)

    a = build_shift_grid(
        region=[-80.0, -79.0, 25.0, 26.0],
        increment="0.1",
        datum_in="EPSG:4326+3855",
        datum_out="EPSG:4326+5703",
    )

    b = build_shift_grid(
        region=[-80.0, -78.9, 25.0, 26.0],
        increment="0.1",
        datum_in="EPSG:4326+3855",
        datum_out="EPSG:4326+5703",
    )

    assert a.generation_key != b.generation_key


def test_projected_region_is_normalized_to_wgs84(monkeypatch):
    _mock_vertical_transform(monkeypatch)

    region = Region(
        400000.0,
        410000.0,
        4930000.0,
        4940000.0,
    )
    region.srs = 32610

    grid = build_shift_grid(
        region=region,
        increment="0.01",
        datum_in="EPSG:32610+3855",
        datum_out="EPSG:32610+5703",
    )

    assert grid.crs == CRS.from_epsg(4326)
    assert -180.0 <= grid.region.xmin <= 180.0
    assert -90.0 <= grid.region.ymin <= 90.0
