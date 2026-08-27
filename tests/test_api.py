# tests/test_api.py

import pytest
import numpy as np
from unittest.mock import MagicMock
from pyproj import Transformer

from transformez.api import PointTransformer


def test_horizontal_only_bypass(monkeypatch):
    """Test 1: If no vertical datums are passed, ensure Z is untouched."""

    # Use monkeypatch to override get_components so it returns a real PyProj transformer
    # but explicitly returns None for the grid path.
    def mock_get_components(self):
        return Transformer.from_crs("EPSG:4326", "EPSG:32610", always_xy=True), None

    monkeypatch.setattr("transformez.api.SRSParser.get_components", mock_get_components)

    # Initialize the transformer
    pt = PointTransformer("EPSG:4326", "EPSG:32610", region=None)

    # Assert RasterQuery was bypassed completely
    assert pt.raster_query is None

    # Transform a point in Oregon/Washington
    x, y, z = pt.transform(-124.0, 44.0, 10.0)

    # Assert X/Y changed, but Z is completely untouched
    assert x > 0  # UTM easting should be a large positive number
    assert z == 10.0


def test_z_unit_scaling_and_math(monkeypatch):
    """Test 2 & 4: Ensure ft->m conversion and grid shifts stack correctly."""

    # Mock the horizontal transformer
    mock_transformer = MagicMock()
    mock_transformer.transform.side_effect = lambda x, y: (x, y)

    monkeypatch.setattr(
        "transformez.api.SRSParser.get_components",
        lambda self: (mock_transformer, "fake_grid.tif"),
    )

    # Force __init__ to do absolutely nothing (bypassing the file check)
    monkeypatch.setattr("transformez.api.RasterQuery.__init__", lambda self, path: None)

    # Force query to return our math test value
    monkeypatch.setattr(
        "transformez.api.RasterQuery.query", lambda self, x, y: np.array([-0.25])
    )

    pt = PointTransformer(
        "EPSG:4326", "EPSG:4326", region=None, z_unit_in="ft", z_unit_out="m"
    )

    # 10 ft = ~3.048 meters. Add -0.25m shift = 2.798 meters.
    _, _, z = pt.transform(-124.0, 44.0, 10.0)

    assert z == pytest.approx(2.798, abs=0.001)


def test_scalar_vs_vector_return_types(monkeypatch):
    """Test 3: Ensure passing floats returns floats, and arrays return arrays."""

    # 1. Mock the horizontal transformer
    mock_transformer = MagicMock()
    mock_transformer.transform.side_effect = lambda x, y: (x, y)

    monkeypatch.setattr(
        "transformez.api.SRSParser.get_components",
        lambda self: (mock_transformer, "fake_grid.tif"),
    )

    # 2. Neuter the RasterQuery initialization
    monkeypatch.setattr("transformez.api.RasterQuery.__init__", lambda self, path: None)

    pt = PointTransformer("EPSG:4326", "EPSG:4326", region=None)

    # --- Scalar Test ---
    monkeypatch.setattr(
        "transformez.api.RasterQuery.query", lambda self, x, y: np.array([1.0])
    )
    _, _, z_scalar = pt.transform(0.0, 0.0, 5.0)

    assert isinstance(z_scalar, float)

    # --- Vector Test ---
    monkeypatch.setattr(
        "transformez.api.RasterQuery.query", lambda self, x, y: np.array([1.0, 1.0])
    )
    _, _, z_vector = pt.transform(
        np.array([0.0, 0.0]), np.array([0.0, 0.0]), np.array([5.0, 5.0])
    )

    assert isinstance(z_vector, np.ndarray)
    assert len(z_vector) == 2
