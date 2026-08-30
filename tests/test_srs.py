# tests/test_srs.py

from unittest.mock import patch, MagicMock

import numpy as np
from pyproj import Transformer

from transformez.srs import SRSParser
from fetchez.spatial import Region


def test_srs_pure_horizontal():
    """Ensure pure horizontal requests do not trigger vertical logic."""
    parser = SRSParser("EPSG:4326", "EPSG:3857")

    # It should cleanly parse the horizontal CRSs
    assert parser.tc["src_crs"].to_epsg() == 4326
    assert parser.tc["dst_crs"].to_epsg() == 3857

    # It should realize no vertical shift is needed
    assert parser.tc["want_vertical"] is False
    assert parser.tc["src_vert_epsg"] is None


def test_srs_compound_vertical_parsing():
    """Ensure it correctly splits compound vertical strings."""
    # Simulating WGS84 to NAD83 + NAVD88
    parser = SRSParser("EPSG:4979", "EPSG:6319+5703")

    assert parser.tc["dst_crs"].to_epsg() == 6319
    assert parser.tc["dst_vert_epsg"] == 5703
    assert parser.tc["want_vertical"] is True


def test_srs_geoid_extraction_and_fallback():
    """Ensure it extracts explicit geoids and falls back to definitions if omitted.

    With the new parser we no longer accept the syntax such as `:g2012b`. Instead,
    we have to use the mappting with, e.g.:
    {geoid: "g2012b"}
    """
    # 1. Explicit geoid extraction
    parser_explicit = SRSParser("EPSG:4326", "EPSG:4326+geoid:g2012b")
    # parser_explicit = SRSParser("EPSG:4326", {"horizontal": "EPSG:4326", "vertical": "5703", "geoid": "g2012b"})
    assert parser_explicit.tc["dst_geoid"] == "g2012b"

    # 2. Implicit geoid fallback (5703 should default to g2018 per Datums)
    parser_implicit = SRSParser("EPSG:4326", "EPSG:4326+5703")
    assert parser_implicit.tc["dst_geoid"] == "g2018"


@patch("transformez.grid_engine.GridWriter.write")
@patch("transformez.transform.VerticalTransform")
def test_srs_component_generation(mock_vt_class, mock_writer):
    """Ensure get_components returns the correct PyProj transformer and grid path."""

    # Setup the mock VerticalTransform to return a dummy grid
    mock_vt_instance = MagicMock()
    mock_vt_instance._vertical_transform.return_value = (
        np.full((10, 10), -0.25, dtype=np.float32),
        None,
    )  # Dummy return
    mock_vt_class.return_value = mock_vt_instance

    dummy_region = Region(-80.0, -79.0, 25.0, 26.0)

    # Requesting WGS84 -> NAVD88
    parser = SRSParser("EPSG:4326+3855", "EPSG:4326+5703", region=dummy_region)
    horz_transformer, grid_fn = parser.get_components()

    # 1. Verify Horizontal Transformer
    assert isinstance(horz_transformer, Transformer)

    # 2. Verify Vertical Grid Generation Logic
    assert parser.tc["want_vertical"] is True
    # The VT class should have been instantiated
    assert mock_vt_class.called
    # The grid should have been "written" to disk
    assert mock_writer.called

    # 3. Verify the returned grid filename matches the expected output format
    assert grid_fn is not None
    assert "transformez_3855_5703" in grid_fn
    assert grid_fn.endswith(".tif")
