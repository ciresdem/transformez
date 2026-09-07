# tests/test_decay.py

import numpy as np
import pytest

from fetchez.spatial import Region
from transformez.grid.engine import GridEngine


def _make_signed_coast(ny: int, nx: int, width_m: float = 10_000.0):
    """Create a vertical synthetic shoreline at the center of the grid."""
    x_m = np.linspace(-width_m / 2, width_m / 2, nx, dtype=np.float32)

    # Positive = water, negative = land.
    signed = -x_m

    return np.tile(signed, (ny, 1))


def _physical_decay_profile(nx: int):
    ny = nx
    region = Region(0.0, 0.1, 0.0, 0.1)

    d2c_m = _make_signed_coast(ny, nx)

    context = GridEngine.build_coastal_context(
        signed_distance_m=d2c_m,
        target_region=region,
    )

    # Constant 2 m tidal shift on water; land starts as NaN.
    data = np.full((ny, nx), np.nan, dtype=np.float32)
    data[context.water_mask] = 2.0

    result = GridEngine.fill_nans(
        data,
        coastal_context=context,
        decay_distance_m=5_000.0,
        buffer_distance_m=250.0,
    )

    # Use middle row as a transect through the shoreline.
    return d2c_m[ny // 2], result[ny // 2]


@pytest.mark.parametrize("nx", [50, 100, 400])
def test_physical_decay_reaches_zero_at_requested_distance(nx):
    distance, shift = _physical_decay_profile(nx)

    land_distance = np.maximum(-distance, 0.0)

    near_zero = np.argmin(np.abs(land_distance - 5_250.0))

    assert abs(shift[near_zero]) < 0.05


def test_physical_decay_is_resolution_invariant():
    sample_distances = np.array([250.0, 500.0, 1_000.0, 2_500.0, 4_000.0, 5_250.0])

    profiles = []

    for nx in (100, 200, 400):
        distance, shift = _physical_decay_profile(nx)
        land_distance = np.maximum(-distance, 0.0)

        sampled = []

        for target_m in sample_distances:
            idx = np.argmin(np.abs(land_distance - target_m))
            sampled.append(shift[idx])

        profiles.append(sampled)

    reference = np.asarray(profiles[-1])

    for profile in profiles[:-1]:
        np.testing.assert_allclose(
            profile,
            reference,
            atol=0.03,
        )
