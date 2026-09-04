import pytest

from transformez.reference.bindings import (
    CUSTOM_REGISTRY,
    CUSTOM_VERTICAL_REFERENCES,
    OPERATION_BINDINGS,
    HTDP_FRAME_BINDINGS,
)
from transformez.reference.types import VerticalKind, AxisDirection


def test_registry_resolution_success():
    """Ensure the registry correctly resolves known namespaces, case-insensitively."""

    # Standard resolution
    ref = CUSTOM_REGISTRY.resolve("vdatum:mllw")
    assert ref.id == "vdatum:mllw"
    assert ref.kind == VerticalKind.TIDAL_HEIGHT
    assert ref.axis_direction == AxisDirection.UP

    # Case-insensitivity check
    ref_upper = CUSTOM_REGISTRY.resolve("VDATUM:MLLW")
    assert ref_upper is ref  # Should return the exact same object


def test_registry_resolution_failure():
    """Ensure unknown namespaces fail fast with a ValueError."""

    with pytest.raises(ValueError, match="Unknown custom reference namespace"):
        CUSTOM_REGISTRY.resolve("vdatum:not-a-real-datum")


def test_registry_binding_consistency():
    """
    Structural Test: Ensure every custom vertical reference has a
    corresponding operation binding so the engine knows how to execute it.
    """

    for ref_id in CUSTOM_VERTICAL_REFERENCES.keys():
        assert ref_id in OPERATION_BINDINGS, (
            f"Missing execution plan! '{ref_id}' is defined in metadata "
            f"but has no corresponding entry in OPERATION_BINDINGS."
        )


def test_htdp_frame_bindings():
    """Ensure tectonic bridges are correctly defined with their epochs."""

    nad83_2011 = HTDP_FRAME_BINDINGS.get("EPSG:6319")

    assert nad83_2011 is not None
    assert nad83_2011.htdp_id == 1
    assert nad83_2011.reference_epoch == 1997.0


def test_binding_ids():
    for key, binding in OPERATION_BINDINGS.items():
        assert key == binding.reference_id


def test_binding_duo():
    for key, _binding in CUSTOM_VERTICAL_REFERENCES.items():
        assert OPERATION_BINDINGS.get(key) is not None


@pytest.mark.parametrize(
    ("datum", "proxy"),
    [
        ("vdatum:msl", "global:mss"),
        ("vdatum:mllw", "global:lat"),
        ("vdatum:mlw", "global:lat"),
        ("vdatum:mhhw", "global:hat"),
        ("vdatum:mhw", "global:hat"),
    ],
)
def test_vdatum_global_proxy_bindings(datum, proxy):
    assert OPERATION_BINDINGS[datum].global_proxy == proxy
