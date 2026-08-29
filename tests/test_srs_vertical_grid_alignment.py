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


def test_unlabeled_processing_region_defaults_to_source_crs():
    parser = SRSParser.__new__(SRSParser)
    parser.tc = {"src_crs": CRS.from_epsg(32610)}
    parser.decay_distance_m = 5000.0
    parser.buffer_distance_m = 250.0
    parser.max_vdatum_extension_m = None
    region = _Region()
    assert parser._vertical_grid_region_crs(region) == CRS.from_epsg(32610)


def test_labeled_processing_region_uses_region_crs():
    parser = SRSParser.__new__(SRSParser)
    parser.tc = {"src_crs": CRS.from_epsg(32610)}
    parser.decay_distance_m = 5000.0
    parser.buffer_distance_m = 250.0
    parser.max_vdatum_extension_m = None
    region = _Region()
    region.srs = CRS.from_epsg(4269)
    assert parser._vertical_grid_region_crs(region) == CRS.from_epsg(4269)


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


def test_grid_writer_preserves_explicit_transform_crs_and_existing_tags_api(tmp_path):
    arr = np.full((3, 4), -0.5, dtype=np.float32)
    transform = from_bounds(400000, 4930000, 401000, 4931000, 4, 3)
    path = tmp_path / "native-grid.tif"
    GridWriter.write(
        str(path),
        arr,
        object(),
        CRS.from_epsg(32610),
        {"datum_in": "5866", "datum_out": "5703"},
        transform,
        np.nan,
    )
    with rasterio.open(path) as src:
        assert src.crs.to_epsg() == 32610
        assert src.transform == transform
        assert src.tags()["datum_in"] == "5866"
        assert src.tags()["datum_out"] == "5703"
        np.testing.assert_array_equal(src.read(1), arr)


def test_set_vertical_transform_preserves_generated_grid_provenance(monkeypatch):
    class _ProcessingRegion(_Region):
        srs = None

        def copy(self):
            clone = _ProcessingRegion(self.xmin, self.xmax, self.ymin, self.ymax)
            clone.srs = self.srs
            return clone

        def buffer(self, pct=0):
            return None

        @property
        def width(self):
            return self.xmax - self.xmin

        @property
        def height(self):
            return self.ymax - self.ymin

        def format(self, style):
            assert style == "fn"
            return "n44x64_w124x08"

    parser = SRSParser.__new__(SRSParser)
    parser.region = _ProcessingRegion()
    parser.cache_dir = None
    parser.tc = {
        "want_vertical": True,
        "src_vert_epsg": 5866,
        "dst_vert_epsg": 5703,
        "src_geoid": None,
        "dst_geoid": None,
        "src_crs": CRS.from_epsg(4326),
    }
    parser.decay_distance_m = 5000.0
    parser.buffer_distance_m = 250.0
    parser.max_vdatum_extension_m = None

    class _VerticalTransform:
        def __init__(self, *args, **kwargs):
            pass

        def _vertical_transform(self):
            return _constant_shift(), None

    captured = {}

    def _capture_write(*args, **kwargs):
        captured.update(kwargs)
        return str(args[0])

    monkeypatch.setattr("transformez.transform.VerticalTransform", _VerticalTransform)
    monkeypatch.setattr("transformez.srs.os.path.exists", lambda path: False)
    monkeypatch.setattr("transformez.srs.GridWriter.write", _capture_write)

    parser.set_vertical_transform()

    tags = captured["tags"]
    assert tags["TRANSFORMEZ_DATUM_IN"] == "5866"
    assert tags["TRANSFORMEZ_DATUM_OUT"] == "5703"
    assert tags["TRANSFORMEZ_GEOID_IN"] == "None"
    assert tags["TRANSFORMEZ_GEOID_OUT"] == "None"
    assert tags["TRANSFORMEZ_NATIVE_CRS"] == "WGS 84"
    assert tags["TIFFTAG_SOFTWARE"].startswith("Transformez v")
    assert "TIFFTAG_DATETIME" in tags
