# tests/test_grid_engine.py

import numpy as np
from numpy.testing import assert_allclose, assert_array_equal
from transformez.grid.engine import GridEngine


def test_smart_blend_basic():
    """Ensure smart_blend smoothly transitions between two grids."""
    # Create a 5x5 background grid of zeros
    bg_grid = np.zeros((5, 5))

    # Create an input grid of tens, with the right side as NaNs
    in_grid = np.full((5, 5), 10.0)
    in_grid[:, 3:] = np.nan

    # Blend with a very short pixel radius
    blended = GridEngine.smart_blend(in_grid, bg_grid, blend_pixels=2)

    # The left side should remain exactly 10
    assert_array_equal(blended[:, 0], np.full(5, 10.0))
    # The far right side (NaNs) should have blended down toward the background (0)
    assert blended[0, 4] < 10.0
    assert not np.isnan(blended).any()


def test_fill_nans_infinite_extrapolation():
    """Ensure fill_nans extends coastal values infinitely when decay is 0."""
    data = np.full((5, 5), np.nan)
    data[:, 0] = 5.0  # Simulate a "coastline" of 5.0 on the left edge

    # Fill with 0 decay (infinite extrapolation)
    filled = GridEngine.fill_nans(data, decay_pixels=0)

    # The entire grid should now be filled with 5.0
    assert_allclose(filled, np.full((5, 5), 5.0))
    assert not np.isnan(filled).any()


def test_fill_nans_inland_decay():
    """Ensure fill_nans decays values to zero inland using the Hermite curve."""
    data = np.full((1, 10), np.nan)
    data[0, 0] = 10.0  # Coastline at index 0

    # Apply a 5-pixel decay with 0 buffer
    filled = GridEngine.fill_nans(data, decay_pixels=5, buffer_pixels=0)

    # Coastline should remain 10.0
    assert filled[0, 0] == 10.0
    # At or beyond the decay distance (5 pixels), it should be exactly 0.0
    assert filled[0, 5] == 0.0
    assert filled[0, 9] == 0.0
    # Intermediate values should be strictly decreasing
    assert filled[0, 0] > filled[0, 2] > filled[0, 4] > 0.0


def test_fill_nans_ocean_mask():
    """Ensure fill_nans uses the ocean mask to target valid extrapolation sources."""
    data = np.full((5, 5), np.nan)
    data[:, 0] = 3.0  # Coastline on the LEFT edge

    # Ocean mask: LEFT side is ocean (True) where our source data lives.
    # RIGHT side is land (False).
    ocean_mask = np.full((5, 5), False)
    ocean_mask[:, :2] = True

    filled = GridEngine.fill_nans(data, decay_pixels=0, ocean_mask=ocean_mask)

    # Use assert_allclose to handle microscopic floating-point drift from Gaussian blurs
    assert_allclose(filled[0, 2], 3.0)
    assert_allclose(filled[0, 4], 3.0)
