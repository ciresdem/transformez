import pytest
from pyproj import CRS
from pyproj.crs import CompoundCRS

from transformez.reference.parser import (
    parse_reference,
    InvalidReferenceError,
    UnsupportedReferenceError,
)
from transformez.reference.types import ParsedReference


def test_parse_polymorphic_inputs():
    """Ensure the parser gracefully handles ints, strings, CRS objects, and ParsedReferences."""

    # 1. Integer
    ref_int = parse_reference(4326)
    assert ref_int.horizontal_specified is True
    assert ref_int.horizontal.to_epsg() == 4326

    # 2. String
    ref_str = parse_reference("EPSG:4326")
    assert ref_str.horizontal.to_epsg() == 4326

    # 3. CRS Object
    ref_crs = parse_reference(CRS.from_epsg(4326))
    assert ref_crs.horizontal.to_epsg() == 4326

    # 4. ParsedReference Pass-through
    ref_pass = parse_reference(ref_str)
    assert ref_pass is ref_str  # Must be the exact same object in memory


def test_decompose_standard_crs():
    """Ensure compound CRSs are successfully split into horizontal and vertical components."""

    # WGS84 + NAVD88
    ref = parse_reference("EPSG:4326+5703")
    assert isinstance(ref, ParsedReference)
    assert ref.horizontal_specified is True
    assert ref.vertical_specified is True
    assert ref.horizontal.to_epsg() == 4326

    # Pure 2D Horizontal
    ref_2d = parse_reference("EPSG:4326")
    assert ref_2d.horizontal_specified is True
    assert ref_2d.vertical_specified is False


def test_custom_namespaces_and_legacy_aliases(caplog):
    """Ensure custom prefixes bypass PROJ and legacy aliases issue warnings."""

    # 1. Custom Namespace
    ref_custom = parse_reference("vdatum:mllw")
    assert ref_custom.horizontal_specified is False
    assert ref_custom.vertical_specified is True
    assert ref_custom.source_text == "vdatum:mllw"

    # 2. Legacy Alias
    ref_legacy = parse_reference("mllw")
    assert (
        ref_legacy.source_text == "vdatum:mllw"
    )  # It should internally map to the new namespace

    # Ensure the deprecation warning was actually fired
    assert "Legacy alias 'mllw' is deprecated" in caplog.text


def test_invalid_references():
    """Ensure bad inputs fail fast rather than returning silent garbage."""

    # Empty strings
    with pytest.raises(InvalidReferenceError, match="cannot be empty"):
        parse_reference("   ")

    # Unrecognized integers (Assuming 999999 is not a valid EPSG)
    with pytest.raises(InvalidReferenceError, match="Unsupported coordinate reference"):
        parse_reference("999999")

    # Garbage strings
    with pytest.raises(InvalidReferenceError):
        parse_reference("not_a_datum:12345")


def test_unsupported_compounds():
    """Ensure compounds with multiple horizontal or vertical components raise an error."""

    crs_horz = CRS.from_epsg(4326)
    crs_vert1 = CRS.from_epsg(5703)
    crs_vert2 = CRS.from_epsg(3855)

    # Build an illegal CRS using pyproj's native CompoundCRS builder
    illegal_crs = CompoundCRS(
        name="Too Many Verticals", components=[crs_horz, crs_vert1, crs_vert2]
    )

    with pytest.raises(UnsupportedReferenceError, match="Multiple vertical"):
        parse_reference(illegal_crs)
