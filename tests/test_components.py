# tests/test_components.py

from unittest.mock import MagicMock

import numpy as np
import pytest

from pyproj import CRS, Transformer
from rasterio.transform import from_bounds

from fetchez.spatial import Region

from transformez.api import (
    build_components,
    TransformationComponents,
)
from transformez.grid.shift import ShiftGrid
from transformez.reference.parser import parse_reference


def _region():
    region = Region(-124.08, -124.04, 44.60, 44.64)
    region.srs = 4326
    return region


def _synthetic_shift_grid():
    region = _region()

    array = np.full((10, 10), -0.25, dtype=np.float32)

    transform = from_bounds(
        region.xmin,
        region.ymin,
        region.xmax,
        region.ymax,
        10,
        10,
    )

    return ShiftGrid(
        array=array,
        uncertainty=None,
        region=region,
        crs=CRS.from_epsg(4326),
        transform=transform,
        source_reference=parse_reference("EPSG:4326+3855"),
        target_reference=parse_reference("EPSG:4326+5703"),
        epoch_in="2010.0",
        epoch_out="2010.0",
        provenance={},
        generation_key="test",
    )


def test_build_components_horizontal_only():
    components = build_components(
        "EPSG:4326",
        "EPSG:3857",
        region=_region(),
    )

    assert isinstance(components, TransformationComponents)
    assert isinstance(components.horizontal, Transformer)
    assert components.vertical is None

    x, y = components.horizontal.transform(-124.0, 44.0)

    assert x != pytest.approx(-124.0)
    assert y != pytest.approx(44.0)


def test_build_components_vertical_is_aligned_to_source_crs(monkeypatch):
    generated = MagicMock()
    aligned = MagicMock()
    generated.reproject.return_value = aligned

    monkeypatch.setattr(
        "transformez.api.build_shift_grid",
        MagicMock(return_value=generated),
    )

    region = Region(
        400000.0,
        410000.0,
        4930000.0,
        4940000.0,
    )
    region.srs = 32610

    components = build_components(
        "EPSG:32610+3855",
        "EPSG:4326+5703",
        region=region,
    )

    assert components.vertical is aligned

    generated.reproject.assert_called_once()

    args, kwargs = generated.reproject.call_args
    assert CRS.from_user_input(args[0]) == CRS.from_epsg(32610)
    assert kwargs["dst_region"] is region


def test_build_components_requires_both_vertical_references():
    with pytest.raises(
        ValueError,
        match="Both source and target vertical references are required",
    ):
        build_components(
            "EPSG:4326+3855",
            "EPSG:4326",
            region=_region(),
        )
