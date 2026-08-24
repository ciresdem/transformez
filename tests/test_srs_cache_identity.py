from pyproj import CRS

from transformez.srs import SRSParser


class _Region:
    def __init__(self, xmin, xmax, ymin, ymax, *, srs=None, label="n44x64_w124x10"):
        self.xmin = xmin
        self.xmax = xmax
        self.ymin = ymin
        self.ymax = ymax
        self.srs = srs
        self._label = label

    def format(self, style):
        assert style == "fn"
        return self._label


def _parser(src_crs, *, src_geoid=None, dst_geoid=None):
    parser = SRSParser.__new__(SRSParser)
    parser.tc = {
        "src_crs": CRS.from_user_input(src_crs),
        "src_geoid": src_geoid,
        "dst_geoid": dst_geoid,
    }
    return parser


def test_vertical_grid_name_distinguishes_source_horizontal_crs():
    # Keep every other cache input identical; only the source horizontal CRS changes.
    region = _Region(-124.10, -123.99, 44.58, 44.64)
    geographic = _parser("EPSG:4326")._vertical_grid_name(region, 5866, 5703)
    projected = _parser("EPSG:32610")._vertical_grid_name(region, 5866, 5703)
    assert geographic != projected


def test_vertical_grid_name_distinguishes_full_region_with_same_coarse_label():
    # The human-readable label is deliberately identical. Full bounds must still
    # produce different cache artifacts.
    parser = _parser("EPSG:4326")
    region_a = _Region(-124.10, -124.00, 44.50, 44.64)
    region_b = _Region(-124.10, -123.90, 44.40, 44.64)
    assert region_a.format("fn") == region_b.format("fn")
    name_a = parser._vertical_grid_name(region_a, 5866, 5703)
    name_b = parser._vertical_grid_name(region_b, 5866, 5703)
    assert name_a != name_b


def test_vertical_grid_name_distinguishes_effective_region_crs():
    # Region.srs is consumed by Region.warp when present, so materially different
    # region CRSs must not share a generated-grid identity.
    parser = _parser("EPSG:32610")
    region_a = _Region(400000, 410000, 4930000, 4940000, srs="EPSG:32610")
    region_b = _Region(400000, 410000, 4930000, 4940000, srs="EPSG:26910")
    assert parser._vertical_grid_name(
        region_a, 5866, 5703
    ) != parser._vertical_grid_name(region_b, 5866, 5703)


def test_vertical_grid_name_canonicalizes_equivalent_region_crs_labels():
    # Equivalent CRS labels should resolve to one cache identity rather than
    # producing duplicate grids for presentation-only differences.
    parser = _parser("EPSG:4326")
    region_a = _Region(-124.10, -124.00, 44.50, 44.64, srs="EPSG:4326")
    region_b = _Region(-124.10, -124.00, 44.50, 44.64, srs="WGS 84")
    assert parser._vertical_grid_name(
        region_a, 5866, 5703
    ) == parser._vertical_grid_name(region_b, 5866, 5703)


def test_vertical_grid_name_treats_missing_region_crs_as_wgs84():
    # Fetchez/Globato processing regions are geographic and often unlabeled.
    # Missing Region.srs therefore means WGS84 for generated-grid identity.
    parser = _parser("EPSG:32610")
    region_a = _Region(-124.10, -124.00, 44.50, 44.64, srs=None)
    region_b = _Region(-124.10, -124.00, 44.50, 44.64, srs=(CRS.from_epsg(4326),))
    assert parser._vertical_grid_name(
        region_a, 5866, 5703
    ) == parser._vertical_grid_name(region_b, 5866, 5703)


def test_vertical_grid_name_distinguishes_geoid_inputs():
    # VerticalTransform consumes the geoid names even when the vertical EPSG
    # pair is unchanged, so they are part of the generated-grid identity.
    region = _Region(-124.10, -124.00, 44.50, 44.64, srs="EPSG:4326")
    geoid_a = _parser("EPSG:4326", src_geoid="g2012b")._vertical_grid_name(
        region, 5866, 5703
    )
    geoid_b = _parser("EPSG:4326", src_geoid="g2018")._vertical_grid_name(
        region, 5866, 5703
    )
    assert geoid_a != geoid_b
