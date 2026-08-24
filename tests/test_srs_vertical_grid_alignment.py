import numpy as np
from pyproj import CRS
import rasterio
from rasterio.transform import from_bounds
from rasterio.warp import transform_bounds
import pytest

from transformez.grid_engine import GridWriter
from transformez.srs import SRSParser
from transformez.utils import RasterQuery


class _Region:
    def __init__(self, xmin=-124.08, xmax=-124.04, ymin=44.60, ymax=44.64):
        self.xmin = xmin
        self.xmax = xmax
        self.ymin = ymin
        self.ymax = ymax


def _constant_shift(value=-0.25):
    return np.full((48, 64), value, dtype=np.float32)


def test_unlabeled_processing_region_defaults_to_wgs84_not_source_crs():
    region = _Region()
    assert SRSParser._vertical_grid_region_crs(region) == CRS.from_epsg(4326)


def test_projected_source_grid_is_queryable_in_projected_coordinates(tmp_path):
    region = _Region()
    arr, transform, crs = SRSParser._align_vertical_grid_to_source_crs(
        _constant_shift(), region, CRS.from_epsg(32610)
    )
    assert crs == CRS.from_epsg(32610)
    assert np.isfinite(arr).any()
    assert np.nanmax(np.abs(arr + 0.25)) < 1e-5

    grid = tmp_path / "projected.tif"
    GridWriter.write(
        str(grid), arr, object(), crs=crs, transform=transform, nodata=np.nan
    )
    with rasterio.open(grid) as src:
        assert src.crs.to_epsg() == 32610
        left, bottom, right, top = transform_bounds(src.crs, "EPSG:4326", *src.bounds)
        assert left < -124.04 and right > -124.08
        assert bottom < 44.64 and top > 44.60
        x = np.array([(src.bounds.left + src.bounds.right) / 2.0])
        y = np.array([(src.bounds.bottom + src.bounds.top) / 2.0])

    queried = RasterQuery(str(grid)).query(x, y)
    assert queried[0] == pytest.approx(-0.25, abs=1e-5)


def test_wgs84_source_grid_keeps_original_geographic_grid():
    region = _Region()
    source = _constant_shift(-0.125)
    arr, transform, crs = SRSParser._align_vertical_grid_to_source_crs(
        source, region, CRS.from_epsg(4326)
    )
    expected = from_bounds(
        region.xmin,
        region.ymin,
        region.xmax,
        region.ymax,
        source.shape[1],
        source.shape[0],
    )
    np.testing.assert_array_equal(arr, source)
    assert transform == expected
    assert crs == CRS.from_epsg(4326)


def test_non_wgs84_geographic_source_is_aligned_to_its_exact_crs():
    region = _Region()
    arr, transform, crs = SRSParser._align_vertical_grid_to_source_crs(
        _constant_shift(-0.2), region, CRS.from_epsg(4269)
    )
    assert crs == CRS.from_epsg(4269)
    assert np.isfinite(arr).any()
    assert np.nanmax(np.abs(arr + 0.2)) < 1e-5
    assert transform is not None


def test_alignment_fails_closed_if_reprojection_produces_no_coverage(monkeypatch):
    region = _Region()

    def _no_op_reproject(*args, **kwargs):
        return None

    monkeypatch.setattr("transformez.srs.reproject", _no_op_reproject)
    with pytest.raises(RuntimeError, match="no finite source-CRS coverage"):
        SRSParser._align_vertical_grid_to_source_crs(
            _constant_shift(), region, CRS.from_epsg(32610)
        )


def test_grid_writer_preserves_explicit_transform_and_crs(tmp_path):
    arr = np.full((3, 4), -0.5, dtype=np.float32)
    transform = from_bounds(400000, 4930000, 401000, 4931000, 4, 3)
    path = tmp_path / "native-grid.tif"
    GridWriter.write(
        str(path),
        arr,
        object(),
        crs=CRS.from_epsg(32610),
        transform=transform,
        nodata=np.nan,
    )
    with rasterio.open(path) as src:
        assert src.crs.to_epsg() == 32610
        assert src.transform == transform
        np.testing.assert_array_equal(src.read(1), arr)
