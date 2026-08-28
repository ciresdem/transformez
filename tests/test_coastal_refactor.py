# tests/test_coastal_refactor.py

import numpy as np
import rasterio
from rasterio.transform import from_bounds

from fetchez.spatial import Region
from transformez.grid_engine import GridEngine


def _signed_coast(ny: int = 10, nx: int = 10) -> np.ndarray:
    """Return a simple signed-distance field with water in columns 5 and higher."""
    x = np.arange(nx, dtype=np.float32)
    return np.tile((x - 4.5) * 100.0, (ny, 1))


def _signed_coast_with_zero_band(ny: int = 7, nx: int = 7) -> np.ndarray:
    """Return land, a zero-valued coastline column, then definite water."""
    values = np.array(
        [-300.0, -200.0, -100.0, 0.0, 100.0, 200.0, 300.0],
        dtype=np.float32,
    )
    return np.tile(values[:nx], (ny, 1))


def test_loader_can_preserve_zero_when_zero_is_declared_nodata(tmp_path):
    """Dist2Coast zero cells must survive even though its NetCDF marks zero nodata."""
    data = np.array(
        [
            [-1.0, 0.0, 1.0],
            [-1.0, 0.0, 1.0],
            [-1.0, 0.0, 1.0],
        ],
        dtype=np.float32,
    )
    path = tmp_path / "dist2coast_like.tif"
    transform = from_bounds(0.0, 0.0, 0.003, 0.003, 3, 3)

    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=3,
        width=3,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform,
        nodata=0.0,
    ) as dst:
        dst.write(data, 1)

    region = Region(0.0, 0.003, 0.0, 0.003)

    normal = GridEngine.load_and_interpolate(
        [str(path)], region, nx=3, ny=3, preserve_zero=False
    )
    preserved = GridEngine.load_and_interpolate(
        [str(path)], region, nx=3, ny=3, preserve_zero=True
    )

    assert np.isnan(normal[:, 1]).all()
    np.testing.assert_allclose(preserved[:, 1], 0.0, atol=1e-6)


def test_zero_coast_band_gets_positive_physical_inland_distance():
    """A Dist2Coast zero cell is coastline geometry, not a 0 m inland plateau."""
    d2c_m = _signed_coast_with_zero_band()

    width_deg = d2c_m.shape[1] * 100.0 / 111_320.0
    height_deg = d2c_m.shape[0] * 100.0 / 110_574.0
    region = Region(0.0, width_deg, 0.0, height_deg)

    context = GridEngine.build_coastal_context(
        signed_distance_m=d2c_m,
        target_region=region,
    )

    coast_col = 3
    assert not context.water_mask[0, coast_col]
    assert np.isfinite(context.inland_distance_m[:, coast_col]).all()
    assert (context.inland_distance_m[:, coast_col] > 0.0).all()


def test_vdatum_extension_moves_effective_decay_edge():
    """VDatum coverage may move the effective shoreline landward."""
    d2c_m = _signed_coast()
    region = Region(0.0, 0.01, 0.0, 0.01)

    vdatum_valid = d2c_m > 0.0
    vdatum_valid[4:6, 2:5] = True

    context = GridEngine.build_coastal_context(
        signed_distance_m=d2c_m,
        target_region=region,
        vdatum_valid=vdatum_valid,
    )

    assert context.water_mask[4, 2]
    assert context.water_mask[4, 3]
    assert context.water_mask[4, 4]
    assert context.inland_distance_m[4, 2] == 0.0
    assert context.inland_distance_m[4, 1] > 0.0
    assert context.inland_distance_m[4, 0] > context.inland_distance_m[4, 1]

    np.testing.assert_allclose(
        context.inland_distance_m[0, :5],
        np.maximum(-d2c_m[0, :5], 0.0),
        atol=1e-5,
    )


def test_global_proxy_never_expands_water_domain():
    """Global proxy coverage cannot redefine the coastal water domain."""
    d2c_m = _signed_coast()
    region = Region(0.0, 0.01, 0.0, 0.01)

    vdatum = np.full((10, 10), np.nan, dtype=np.float32)
    vdatum[:, 5:] = 1.0
    vdatum[4:6, 2:5] = 1.0

    context = GridEngine.build_coastal_context(
        signed_distance_m=d2c_m,
        target_region=region,
        vdatum_valid=np.isfinite(vdatum),
    )

    proxy = np.full((10, 10), 2.0, dtype=np.float32)

    result = GridEngine.coastal_aware_composite(
        vdatum_grid=vdatum,
        global_grid=proxy,
        nx=10,
        ny=10,
        coastal_context=context,
        decay_distance_m=300.0,
        buffer_distance_m=0.0,
        blend_pixels=2,
    )

    np.testing.assert_allclose(result[4, 2:5], 1.0)
    assert result[0, 0] != 2.0
    assert result[4, 0] != 2.0
    assert abs(result[4, 1]) > abs(result[4, 0])


def test_vdatum_extension_can_be_guarded_by_native_distance():
    """The optional guard rejects implausibly far-inland VDatum extensions."""
    d2c_m = _signed_coast()
    region = Region(0.0, 0.01, 0.0, 0.01)

    vdatum_valid = d2c_m > 0.0
    vdatum_valid[:, 0] = True

    context = GridEngine.build_coastal_context(
        signed_distance_m=d2c_m,
        target_region=region,
        vdatum_valid=vdatum_valid,
        max_vdatum_extension_m=250.0,
    )

    assert not context.water_mask[0, 0]
