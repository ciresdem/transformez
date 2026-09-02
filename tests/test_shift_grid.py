# tests/test_shift_grid.py

from pathlib import Path

import numpy as np
import pytest
import rasterio

from pyproj import CRS
from rasterio.transform import from_bounds
from rasterio.warp import transform_bounds

from fetchez.spatial import Region

from transformez.generation import ShiftGrid
from transformez.reference.parser import parse_reference
from transformez.utils import RasterQuery


def _region(
    xmin=-124.08,
    xmax=-124.04,
    ymin=44.60,
    ymax=44.64,
    srs=4326,
):
    region = Region(xmin, xmax, ymin, ymax)
    region.srs = srs
    return region


def _shift_grid(
    value=-0.25,
    shape=(48, 64),
    region=None,
    cache_dir=None,
):
    region = region or _region()
    height, width = shape

    array = np.full(shape, value, dtype=np.float32)

    transform = from_bounds(
        region.xmin,
        region.ymin,
        region.xmax,
        region.ymax,
        width,
        height,
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
        provenance={"TEST": "true"},
        generation_key="generation-key",
        cache_dir=Path(cache_dir) if cache_dir else None,
    )


def test_projected_shift_grid_is_queryable_in_projected_coordinates(tmp_path):
    grid = _shift_grid(-0.25)

    projected = grid.reproject("EPSG:32610")

    assert projected.crs == CRS.from_epsg(32610)
    assert np.isfinite(projected.array).any()
    assert np.nanmax(np.abs(projected.array + 0.25)) < 1e-5

    path = projected.write(tmp_path / "projected.tif")

    with rasterio.open(path) as src:
        assert src.crs.to_epsg() == 32610

        left, bottom, right, top = transform_bounds(
            src.crs,
            "EPSG:4326",
            *src.bounds,
        )

        assert left < -124.04
        assert right > -124.08
        assert bottom < 44.64
        assert top > 44.60

        x = np.array([(src.bounds.left + src.bounds.right) / 2.0])
        y = np.array([(src.bounds.bottom + src.bounds.top) / 2.0])

    queried = RasterQuery(str(path)).query(x, y)

    assert queried[0] == pytest.approx(-0.25, abs=1e-5)


def test_reproject_to_non_wgs84_geographic_crs():
    grid = _shift_grid(-0.2)

    projected = grid.reproject("EPSG:4269")

    assert projected.crs == CRS.from_epsg(4269)
    assert np.isfinite(projected.array).any()
    assert np.nanmax(np.abs(projected.array + 0.2)) < 1e-5


def test_reproject_with_exact_region_and_shape():
    grid = _shift_grid(-0.125)

    dst_region = Region(
        400000.0,
        401000.0,
        4930000.0,
        4931000.0,
    )
    dst_region.srs = 32610

    projected = grid.reproject(
        "EPSG:32610",
        dst_region=dst_region,
        dst_shape=(100, 200),
    )

    expected_transform = from_bounds(
        dst_region.xmin,
        dst_region.ymin,
        dst_region.xmax,
        dst_region.ymax,
        200,
        100,
    )

    assert projected.shape == (100, 200)
    assert projected.crs == CRS.from_epsg(32610)
    assert projected.transform == expected_transform


def test_reprojection_preserves_generation_key_changes_storage_key():
    grid = _shift_grid(-0.25)

    projected = grid.reproject("EPSG:32610")

    assert projected.generation_key == grid.generation_key
    assert projected.storage_key() != grid.storage_key()


def test_write_preserves_crs_transform_tags_and_values(tmp_path):
    grid = _shift_grid(-0.5)

    path = grid.write(tmp_path / "shift.tif")

    with rasterio.open(path) as src:
        assert src.crs.to_epsg() == 4326
        assert src.transform == grid.transform
        assert src.tags()["TEST"] == "true"

        np.testing.assert_array_equal(
            src.read(1),
            grid.array,
        )


def test_default_write_uses_storage_path(tmp_path):
    grid = _shift_grid(
        -0.25,
        cache_dir=tmp_path,
    )

    path = grid.write()

    assert path.exists()
    assert path.parent == tmp_path / "grids"


def test_uncertainty_is_reprojected_with_shift():
    grid = _shift_grid(-0.25)

    uncertainty = np.full(
        grid.shape,
        0.05,
        dtype=np.float32,
    )

    grid = ShiftGrid(
        array=grid.array,
        uncertainty=uncertainty,
        region=grid.region,
        crs=grid.crs,
        transform=grid.transform,
        source_reference=grid.source_reference,
        target_reference=grid.target_reference,
        epoch_in=grid.epoch_in,
        epoch_out=grid.epoch_out,
        provenance=grid.provenance,
        generation_key=grid.generation_key,
        cache_dir=grid.cache_dir,
    )

    projected = grid.reproject("EPSG:32610")

    assert projected.uncertainty is not None
    assert projected.uncertainty.shape == projected.array.shape
    assert np.nanmax(np.abs(projected.uncertainty - 0.05)) < 1e-5


def test_same_crs_reprojection_preserves_region():
    grid = _shift_grid(-0.25)

    same = grid.reproject("EPSG:4326")

    assert same.region is not None
    assert same.region.to_bbox() == grid.region.to_bbox()
    np.testing.assert_array_equal(same.array, grid.array)
