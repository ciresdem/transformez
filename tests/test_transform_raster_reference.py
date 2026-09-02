# tests/test_transform_raster.py

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import rasterio

from pyproj import CRS
from rasterio.transform import from_bounds

from fetchez.spatial import Region

from transformez.api import transform_raster
from transformez.generation import ShiftGrid
from transformez.reference.parser import parse_reference


def _write_dem(
    path: Path,
    *,
    crs="EPSG:32610",
    width=20,
    height=10,
):
    transform = from_bounds(
        400000.0,
        4930000.0,
        401000.0,
        4931000.0,
        width,
        height,
    )

    data = np.full(
        (height, width),
        10.0,
        dtype=np.float32,
    )

    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=1,
        dtype="float32",
        crs=crs,
        transform=transform,
        nodata=-9999.0,
    ) as dst:
        dst.write(data, 1)

    return data, transform


def _mock_generated_grid():
    region = Region(-124.1, -124.0, 44.5, 44.6)
    region.srs = 4326

    array = np.full((10, 10), -0.25, dtype=np.float32)

    return ShiftGrid(
        array=array,
        uncertainty=None,
        region=region,
        crs=CRS.from_epsg(4326),
        transform=from_bounds(
            region.xmin,
            region.ymin,
            region.xmax,
            region.ymax,
            10,
            10,
        ),
        source_reference=parse_reference("EPSG:4326+3855"),
        target_reference=parse_reference("EPSG:4326+5703"),
        epoch_in="2010.0",
        epoch_out="2010.0",
        provenance={"TEST": "true"},
        generation_key="test",
        trace=["+ [Synthetic reference execution]"],
    )


def test_transform_raster_aligns_shift_to_projected_dem(
    monkeypatch,
    tmp_path,
):
    src_path = tmp_path / "src.tif"
    dst_path = tmp_path / "dst.tif"

    _write_dem(src_path)

    generated = _mock_generated_grid()

    aligned = MagicMock(spec=ShiftGrid)
    aligned.source_reference = generated.source_reference
    aligned.target_reference = generated.target_reference

    generated_reproject = MagicMock(return_value=aligned)

    # Patch the method at the class level.
    monkeypatch.setattr(
        ShiftGrid,
        "reproject",
        generated_reproject,
    )

    monkeypatch.setattr(
        "transformez.api.build_shift_grid",
        MagicMock(return_value=generated),
    )

    apply_mock = MagicMock(return_value=True)
    monkeypatch.setattr(
        "transformez.api.GridEngine.apply_vertical_shift",
        apply_mock,
    )

    result = transform_raster(
        input_raster=str(src_path),
        datum_in="EPSG:4326+3855",
        datum_out="EPSG:4326+5703",
        output_raster=str(dst_path),
        z_unit_in="m",
        z_unit_out="m",
    )

    assert result == str(dst_path)

    generated_reproject.assert_called_once()

    args, kwargs = generated_reproject.call_args

    assert CRS.from_user_input(args[0]) == CRS.from_epsg(32610)
    assert kwargs["dst_shape"] == (10, 20)

    apply_mock.assert_called_once()


def test_transform_raster_auto_units_use_shift_grid_references(
    monkeypatch,
    tmp_path,
):
    src_path = tmp_path / "src.tif"
    dst_path = tmp_path / "dst.tif"

    _write_dem(
        src_path,
        crs="EPSG:4326",
    )

    generated = _mock_generated_grid()

    # Use the same grid as the aligned return for this orchestration test.
    monkeypatch.setattr(
        ShiftGrid,
        "reproject",
        lambda self, *args, **kwargs: self,
    )

    monkeypatch.setattr(
        "transformez.api.build_shift_grid",
        lambda *args, **kwargs: generated,
    )

    captured = {}

    def _capture_apply(**kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr(
        "transformez.api.GridEngine.apply_vertical_shift",
        _capture_apply,
    )

    transform_raster(
        input_raster=str(src_path),
        datum_in="EPSG:4326+3855",
        datum_out="EPSG:4326+5703",
        output_raster=str(dst_path),
        z_unit_in="auto",
        z_unit_out="auto",
    )

    assert captured["z_unit_in"] == generated.source_reference.vertical.unit_name
    assert captured["z_unit_out"] == generated.target_reference.vertical.unit_name


def test_transform_raster_save_shift_writes_alongside_output(
    monkeypatch,
    tmp_path,
):
    src_path = tmp_path / "src.tif"
    dst_path = tmp_path / "result.tif"

    _write_dem(
        src_path,
        crs="EPSG:4326",
    )

    generated = _mock_generated_grid()

    monkeypatch.setattr(
        ShiftGrid,
        "reproject",
        lambda self, *args, **kwargs: self,
    )

    monkeypatch.setattr(
        "transformez.api.build_shift_grid",
        lambda *args, **kwargs: generated,
    )

    monkeypatch.setattr(
        "transformez.api.GridEngine.apply_vertical_shift",
        lambda **kwargs: True,
    )

    written = {}

    def _write(self, filename=None, **kwargs):
        written["filename"] = filename
        return Path(filename)

    monkeypatch.setattr(
        ShiftGrid,
        "write",
        _write,
    )

    transform_raster(
        input_raster=str(src_path),
        datum_in="EPSG:4326+3855",
        datum_out="EPSG:4326+5703",
        output_raster=str(dst_path),
        z_unit_in="m",
        z_unit_out="m",
        save_shift=True,
    )

    assert Path(written["filename"]) == (tmp_path / "result_shiftgrid.tif")
