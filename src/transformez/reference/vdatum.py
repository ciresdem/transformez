#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.reference.vdatum
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Literal

import rasterio


logger = logging.getLogger(__name__)


_UNKNOWN_DATE = datetime.min


VDATUM_TSS_REFERENCES = {
    "NAD83": "epsg:5703",
    "IGS08": "vdatum:xgeoid17b",
    "IGS14": "vdatum:xgeoid20b",
}

_VDATUM_REGIONAL_SURFACES = {
    "dtl",
    "mhhw",
    "mhw",
    "mllw",
    "mlw",
    "msl",
    "mtl",
    "tss",
}


class UnsupportedVDatumRoadmapError(Exception):
    """Raised when a vdatum metadata file doesn't have the correct values"""

    pass


@dataclass(frozen=True)
class VDatumCoverageMetadata:
    id: str
    release_date: str
    horizontal_frame: str


@dataclass(frozen=True)
class VDatumCoverage:
    id: str
    tidal_grid: Path
    tss_grid: Path
    metadata: VDatumCoverageMetadata


def tss_reference_class(metadata: VDatumCoverageMetadata) -> str:
    try:
        return VDATUM_TSS_REFERENCES[metadata.horizontal_frame.upper()]
    except KeyError as err:
        raise UnsupportedVDatumRoadmapError(
            f"Unsupported VDatum horizontal frame: {metadata.horizontal_frame!r}"
        ) from err


def tss_reference(metadata: dict[str, str]) -> str:
    try:
        return VDATUM_TSS_REFERENCES[metadata.get("horz", "").upper()]
    except KeyError as err:
        raise UnsupportedVDatumRoadmapError(
            f"Unsupported VDatum horizontal frame: {metadata.get('horz')}"
        ) from err


def parse_release_date(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        return datetime.strptime(value.strip(), "%m/%d/%Y")
    except ValueError:
        return None


def parse_vdatum_registry(path: Path) -> dict[str, str]:
    metadata: dict[str, str] = {}

    if not path.exists():
        return metadata

    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            metadata[key.strip()] = value.strip()

    return metadata


def surface_family(grid_name: str) -> Literal["tidal", "tss"]:
    return "tss" if grid_name.casefold() == "tss" else "tidal"


def release_date_from_met(
    path: Path,
    surface: str,
) -> datetime | None:
    wanted = f"{surface}.released_date"

    try:
        with path.open() as f:
            for line in f:
                line = line.strip()

                if "=" not in line:
                    continue

                key, value = line.split("=", 1)

                if key.strip().casefold() == wanted.casefold():
                    return parse_release_date(value)

    except OSError:
        pass

    return None


def vdatum_release_date(
    grid_path: Path,
    grid_name: str,
    registry: dict[str, str],
) -> datetime:
    coverage_id = grid_path.parent.name
    surface = surface_family(grid_name)

    # 1. Coverage-local metadata is authoritative.
    for met_path in sorted(grid_path.parent.glob("*.met")):
        date = release_date_from_met(met_path, surface)
        if date is not None:
            return date

    # 2. Fall back to the global VDatum coverage registry.
    value = registry.get(f"{coverage_id}.{surface}.released_date")
    date = parse_release_date(value)

    return date if date is not None else _UNKNOWN_DATE


def vdatum_priority(
    path: Path,
    grid_name: str,
    registry: dict[str, str],
) -> tuple[datetime, float, str]:
    release_date = vdatum_release_date(
        path,
        grid_name,
        registry,
    )

    try:
        with rasterio.open(path) as src:
            bounds = src.bounds
            area = (bounds.right - bounds.left) * (bounds.top - bounds.bottom)
    except Exception:
        area = float("inf")

    return (
        release_date,
        -area,
        path.as_posix(),
    )


def vdatum_grid_datum(path: Path) -> Optional[str]:
    if path.suffix.casefold() != ".gtx":
        return None

    parts = path.stem.casefold().split("_")

    if parts and parts[-1] == "unc":
        return None

    datum = parts[-1] if parts else None

    if datum not in _VDATUM_REGIONAL_SURFACES:
        return None

    return datum
