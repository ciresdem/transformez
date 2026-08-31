# tests/test_api.py

import pytest
import numpy as np
from unittest.mock import MagicMock
from pyproj import Transformer

from transformez.api import (
    PointTransformer,
    TransformationComponents,
)


def test_z_unit_scaling_and_math(monkeypatch):
    mock_transformer = MagicMock()
    mock_transformer.transform.side_effect = lambda x, y: (x, y)

    mock_vertical = MagicMock()
    mock_vertical.write.return_value = "fake_grid.tif"

    monkeypatch.setattr(
        "transformez.api.build_components",
        lambda *args, **kwargs: TransformationComponents(
            horizontal=mock_transformer,
            vertical=mock_vertical,
        ),
    )

    monkeypatch.setattr(
        "transformez.api.RasterQuery.__init__",
        lambda self, path: None,
    )

    monkeypatch.setattr(
        "transformez.api.RasterQuery.query",
        lambda self, x, y: np.array([-0.25]),
    )

    pt = PointTransformer(
        "EPSG:4326",
        "EPSG:4326",
        region=None,
        z_unit_in="ft",
        z_unit_out="m",
    )

    _, _, z = pt.transform(-124.0, 44.0, 10.0)

    assert z == pytest.approx(2.798, abs=0.001)


def test_scalar_vs_vector_return_types(monkeypatch):
    mock_transformer = MagicMock()
    mock_transformer.transform.side_effect = lambda x, y: (x, y)

    mock_vertical = MagicMock()
    mock_vertical.write.return_value = "fake_grid.tif"

    monkeypatch.setattr(
        "transformez.api.build_components",
        lambda *args, **kwargs: TransformationComponents(
            horizontal=mock_transformer,
            vertical=mock_vertical,
        ),
    )

    monkeypatch.setattr(
        "transformez.api.RasterQuery.__init__",
        lambda self, path: None,
    )

    pt = PointTransformer(
        "EPSG:4326",
        "EPSG:4326",
        region=None,
    )

    monkeypatch.setattr(
        "transformez.api.RasterQuery.query",
        lambda self, x, y: np.array([1.0]),
    )

    _, _, z_scalar = pt.transform(0.0, 0.0, 5.0)

    assert isinstance(z_scalar, float)

    monkeypatch.setattr(
        "transformez.api.RasterQuery.query",
        lambda self, x, y: np.array([1.0, 1.0]),
    )

    _, _, z_vector = pt.transform(
        np.array([0.0, 0.0]),
        np.array([0.0, 0.0]),
        np.array([5.0, 5.0]),
    )

    assert isinstance(z_vector, np.ndarray)
    assert len(z_vector) == 2


def test_horizontal_only_bypass(monkeypatch):
    transformer = Transformer.from_crs(
        "EPSG:4326",
        "EPSG:32610",
        always_xy=True,
    )

    monkeypatch.setattr(
        "transformez.api.build_components",
        lambda *args, **kwargs: TransformationComponents(
            horizontal=transformer,
            vertical=None,
        ),
    )

    pt = PointTransformer(
        "EPSG:4326",
        "EPSG:32610",
        region=None,
    )

    assert pt.raster_query is None

    x, y, z = pt.transform(
        -124.0,
        44.0,
        10.0,
    )

    assert x > 0
    assert z == 10.0
