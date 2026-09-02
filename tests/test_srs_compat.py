# tests/test_srs_compat.py

from pathlib import Path
from unittest.mock import MagicMock

from transformez.api import TransformationComponents


def test_srs_parser_delegates_to_build_components(monkeypatch):
    horizontal = MagicMock()
    vertical = MagicMock()
    vertical.write.return_value = Path("/tmp/shift.tif")

    components = TransformationComponents(
        horizontal=horizontal,
        vertical=vertical,
    )

    build_mock = MagicMock(return_value=components)

    monkeypatch.setattr(
        "transformez.api.build_components",
        build_mock,
    )

    from transformez.srs import SRSParser

    _parser = SRSParser(
        "EPSG:4326+3855",
        "EPSG:4326+5703",
        region=[-80, -79, 25, 26],
        cache_dir="/tmp",
    )

    build_mock.assert_called_once_with(
        "EPSG:4326+3855",
        "EPSG:4326+5703",
        region=[-80, -79, 25, 26],
        cache_dir="/tmp",
    )


def test_srs_parser_returns_legacy_components_tuple(monkeypatch):
    horizontal = MagicMock()

    vertical = MagicMock()
    vertical.write.return_value = Path("/tmp/shift.tif")

    monkeypatch.setattr(
        "transformez.srs.build_components",
        lambda *args, **kwargs: TransformationComponents(
            horizontal=horizontal,
            vertical=vertical,
        ),
    )

    from transformez.srs import SRSParser

    parser = SRSParser(
        "EPSG:4326+3855",
        "EPSG:4326+5703",
        region=[-80, -79, 25, 26],
    )

    returned_horizontal, grid_path = parser.get_components()

    assert returned_horizontal is horizontal
    assert Path(grid_path) == Path("/tmp/shift.tif")
    vertical.write.assert_called_once()


def test_srs_parser_horizontal_only_returns_none_grid(monkeypatch):
    horizontal = MagicMock()

    monkeypatch.setattr(
        "transformez.srs.build_components",
        lambda *args, **kwargs: TransformationComponents(
            horizontal=horizontal,
            vertical=None,
        ),
    )

    from transformez.srs import SRSParser

    parser = SRSParser(
        "EPSG:4326",
        "EPSG:3857",
        region=[-80, -79, 25, 26],
    )

    returned_horizontal, grid_path = parser.get_components()

    assert returned_horizontal is horizontal
    assert grid_path is None
