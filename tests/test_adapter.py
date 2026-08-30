# tests/test_adapter.py


from transformez.definitions import Datums
from transformez.reference.adapter import adapt_reference


def test_vdatum_mllw_adapter():
    spec = adapt_reference("vdatum:mllw")

    assert spec.vertical is not None
    assert spec.vertical.ref_type == "surface"
    assert spec.vertical.native_epsg == 6319
    assert spec.vertical.provider_datum == "mllw"


def test_global_lat_adapter():
    spec = adapt_reference("global:lat")

    assert spec.vertical is not None
    assert spec.vertical.ref_type == "global_tidal"
    assert spec.vertical.native_epsg == 4979
    assert spec.vertical.provider_datum == "lat"


def test_epsg_navd88_adapter():
    spec = adapt_reference("EPSG:5703")

    assert spec.vertical is not None
    assert spec.vertical.epsg == 5703
    assert spec.vertical.ref_type == "cdn"


def test_horizontal_only_reference():
    spec = adapt_reference("EPSG:4326")

    assert spec.horizontal is not None
    assert spec.vertical is None


def test_compound_mapping():
    spec = adapt_reference(
        {
            "horizontal": "EPSG:4326",
            "vertical": "vdatum:mllw",
        }
    )

    assert spec.horizontal is not None
    assert spec.vertical is not None
    assert spec.vertical.provider_datum == "mllw"


# def test_valid_but_legacy_unsupported_vertical_crs():
#     with pytest.raises(LegacyAdapterError):
#         adapt_reference("EPSG:<some-valid-but-unsupported-vertical-crs>")


def test_mllw_legacy_equivalence():
    old_epsg = Datums.get_vdatum_by_name("mllw")

    new = adapt_reference("vdatum:mllw")

    assert new.vertical.epsg == old_epsg
    assert new.vertical.ref_type == Datums.get_frame_type(old_epsg)


def test_geoid_legacy_equivalence():
    old_geoid = Datums.get_default_geoid(5703)
    spec = adapt_reference(5703)
    new_geoid = spec.vertical.geoid

    assert old_geoid == new_geoid


def test_legacy_geoid_processing():
    spec = adapt_reference("EPSG:4326+5703+geoid:g2012b")

    assert spec.vertical.geoid == "g2012b"
    assert spec.vertical.epsg == 5703
    assert spec.horizontal.to_epsg() == 4326
