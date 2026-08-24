# test/test_transform.py

import numpy as np
from unittest.mock import patch
from numpy.testing import assert_allclose
from fetchez.spatial import Region

from transformez.transform import VerticalTransform


# 1. We patch the specific internal methods of VerticalTransform
@patch.object(VerticalTransform, "_get_grid")
@patch.object(VerticalTransform, "_fetch_ocean_mask")
@patch.object(VerticalTransform, "_get_htdp_shift")
def test_full_transformation_routing(mock_htdp, mock_ocean_mask, mock_get_grid):
    """Test full routing (MLLW -> NAVD88) and math stacking without any downloads."""

    # 2. Set up the artificial grid values returned by _get_grid
    def mock_grid_responses(provider, name, *args, **kwargs):
        # We use a tiny 3x3 array for instant memory testing
        shape = (3, 3)
        if name == "mllw":
            return np.full(shape, 1.0)  # MLLW to LMSL = 1.0m
        elif name == "tss":
            return np.full(shape, 0.5)  # LMSL to Ortho = 0.5m
        elif name in ["g2018", "g2012b"]:
            return np.full(shape, 13.0)  # Geoid Offset = 13.0m

        return np.zeros(shape)

    # Map the side effect to our _get_grid mock
    mock_get_grid.side_effect = mock_grid_responses

    # Set up the ocean mask (False means all land, so no FES global blending needed)
    mock_ocean_mask.return_value = np.full((3, 3), False)

    # HTDP shouldn't be called for NAD83 -> NAD83, but mock it just in case
    mock_htdp.return_value = np.zeros((3, 3))

    # 3. Initialize the Transform engine for MLLW -> NAVD88 (5703)
    dummy_region = Region(-80.0, -79.0, 25.0, 26.0)

    vt = VerticalTransform(
        region=dummy_region,
        nx=3,
        ny=3,
        epsg_in=1089,  # MLLW
        epsg_out=5703,  # NAVD88
        epoch_in="2010.0",
        epoch_out="2010.0",
    )

    # 4. Run the transformation!
    shift_array, _ = vt._vertical_transform()

    # 5. Verify the Math
    # Step 1 (Input to Hub):
    #   MLLW(1.0) - TSS(0.5) = 0.5m hydro shift.
    #   + Geoid(13.0) = 13.5m total offset above NAD83 ellipsoid.
    # Step 2 (Hub to Output):
    #   We are going to NAVD88, so we SUBTRACT the geoid (-13.0m).
    # Final Result: 13.5 - 13.0 = 0.5m!

    assert shift_array is not None
    assert_allclose(shift_array, 0.5)

    # 6. Verify the Routing Logic was hit correctly
    # Assert _get_grid was called exactly for the components we expect
    called_names = [call.args[1] for call in mock_get_grid.call_args_list]
    assert "mllw" in called_names
    assert "tss" in called_names
    assert "g2018" in called_names
