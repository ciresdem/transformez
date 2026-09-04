#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.generation
~~~~~~~~~~~~~

This is the inroad into transform.py. Generate a shift grid and
return a ShiftGrid object to do with what you will.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
import hashlib
from pathlib import Path
from typing import List, Union, Mapping
from dataclasses import dataclass

import numpy as np
import datetime

from pyproj import CRS

from rasterio.transform import from_bounds, Affine

from .reference.types import ParsedReference, ReferenceInput
from .reference.parser import parse_reference

from fetchez.spatial import parse_region, Region
from fetchez.utils import str_or, str2inc

from transformez import __version__


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ShiftGrid:
    array: np.ndarray
    region: Region
    crs: CRS
    transform: Affine

    source_reference: ParsedReference
    target_reference: ParsedReference

    epoch_in: str
    epoch_out: str

    provenance: Mapping[str, str]

    generation_key: str

    trace: List[str]

    uncertainty: np.ndarray | None = None

    cache_dir: Path | None = None

    @property
    def shape(self) -> tuple[int, ...]:
        return self.array.shape

    @property
    def height(self) -> int:
        return self.array.shape[0]

    @property
    def width(self) -> int:
        return self.array.shape[1]

    @property
    def bounds(self):
        return self.region.to_bbox()

    def storage_key(self) -> str:
        parts = [
            self.generation_key,
            self.crs.to_wkt(),
            str(self.width),
            str(self.height),
            *(format(float(v), ".17g") for v in self.bounds),
        ]

        payload = "\x1f".join(parts).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:16]

    def storage_path(self) -> Path:
        root = self.cache_dir or Path("transformez_cache")
        path = root / "grids"
        path.mkdir(parents=True, exist_ok=True)

        return path / f"transformez_{self.storage_key()}_{self.region.format('fn')}.tif"

    def reproject(
        self,
        dst_crs,
        dst_region=None,
        dst_shape=None,
    ) -> "ShiftGrid":
        from .grid_engine import GridEngine

        array, transform, region = GridEngine.reproject_grid(
            self.array,
            self.transform,
            self.region,
            self.crs,
            dst_crs,
            dst_region=dst_region,
            dst_shape=dst_shape,
        )

        if self.uncertainty is not None:
            unc_array, unc_transform, unc_region = GridEngine.reproject_grid(
                self.uncertainty,
                self.transform,
                self.region,
                self.crs,
                dst_crs,
                dst_region=dst_region,
                dst_shape=dst_shape,
            )
        else:
            unc_array = None

        dst_crs = CRS.from_user_input(dst_crs)
        provenance = {
            **self.provenance,
            "TRANSFORMEZ_GRID_CRS": dst_crs.to_string(),
            "TRANSFORMEZ_REPROJECTED_FROM": self.crs.to_string(),
        }

        return ShiftGrid(
            array=array,
            uncertainty=unc_array,
            region=region,
            crs=dst_crs,
            transform=transform,
            source_reference=self.source_reference,
            target_reference=self.target_reference,
            epoch_in=self.epoch_in,
            epoch_out=self.epoch_out,
            provenance=provenance,
            generation_key=self.generation_key,
            trace=self.trace,
            cache_dir=self.cache_dir,
        )

    def write(self, filename: str | Path | None = None, **kwargs):
        from .grid_engine import GridWriter

        path = Path(filename) if filename is not None else self.storage_path()
        logger.info(f"Saving shift grid to {path}...")
        GridWriter.write(
            path,
            self.array,
            self.region,
            crs=self.crs,
            transform=self.transform,
            tags=self.provenance,
            **kwargs,
        )
        return path


def _region_crs(
    region: Region,
    default: CRS | None = None,
) -> CRS | None:
    value = getattr(region, "srs", None)

    if isinstance(value, (list, tuple)):
        if len(value) != 1:
            raise ValueError(f"Region must contain exactly one CRS, got {value!r}")
        value = value[0]

    if value is None:
        return default

    parsed = parse_reference(value)
    return parsed.horizontal or default


def _region_to_wgs84(
    region: Region,
    fallback_crs: CRS | None = None,
) -> Region:
    working_region = region.copy()

    region_crs = _region_crs(working_region, fallback_crs)

    if region_crs is None:
        # Important policy decision.
        region_crs = CRS.from_epsg(4326)

    working_region.srs = region_crs.to_epsg() or region_crs.to_wkt()

    if region_crs != CRS.from_epsg(4326):
        working_region.warp("EPSG:4326")

    return working_region


def _generation_key(
    region: Region,
    increment: str | float,
    source: ParsedReference,
    target: ParsedReference,
    epoch_in: str,
    epoch_out: str,
    decay_pixels: int,
    decay_distance_m: float | None,
    buffer_distance_m: float | None,
    max_vdatum_extension_m: float | None,
    extrapolate_inland: bool,
    use_stations: bool,
) -> str:
    parts = [
        "shift-grid-v1",
        source.horizontal.to_wkt() if source.horizontal else "",
        source.vertical.id if source.vertical else "",
        target.horizontal.to_wkt() if target.horizontal else "",
        target.vertical.id if target.vertical else "",
        # format(float(epoch_in), ".10g"),
        # format(float(epoch_out), ".10g"),
        str(epoch_in),
        str(epoch_out),
        str(increment),
        str(decay_pixels),
        str(decay_distance_m),
        str(buffer_distance_m),
        str(max_vdatum_extension_m),
        str(extrapolate_inland),
        str(use_stations),
        format(float(region.xmin), ".17g"),
        format(float(region.xmax), ".17g"),
        format(float(region.ymin), ".17g"),
        format(float(region.ymax), ".17g"),
    ]

    payload = "\x1f".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def build_shift_grid(
    region: Union[List[float], str, Region],
    increment: Union[str, float],
    datum_in: ReferenceInput,
    datum_out: ReferenceInput,
    epoch_in: str = "2010.0",
    epoch_out: str = "2010.0",
    decay_pixels: int = 100,
    decay_distance_m: float | None = None,
    buffer_distance_m: float = 0.0,
    max_vdatum_extension_m: float | None = None,
    extrapolate_inland: bool = False,
    cache_dir: str | Path | None = None,
    use_stations: bool = False,
    verbose: bool = False,
) -> ShiftGrid:
    """Generate a vertical shift grid for a specific region.

    Args:
        region: Bounds as [W, E, S, N], a 'loc:' string, or a Region object.
        increment: Resolution (e.g., '3s' or 0.0008333).
        datum_in: Source datum (e.g., 'mllw', '5703').
        datum_out: Target datum (e.g., '4979', '6319').
        epoch_in: Source epoch (e.g., '2010.0').
        epoch_out: Target epoch (e.g., '2010.0').
        decay_pixels: Legacy pixel-based inland decay distance.
        decay_distance_m: Inland decay distance in meters. When set,
            this takes precedence over ``decay_pixels``.
        buffer_distance_m: Distance inland, in meters, to retain the full coastal
            shift before inland decay begins.
        max_vdatum_extension_m: Optional maximum inland distance where VDatum
            coverage may extend the effective water domain.
        extrapolate_inland: No decay will be performed and the shift values
             will be extrapolated for the entire region.
        cache_dir: Path to store downloaded grids.
        use_stations: Force RBF interpolation using live tide stations.
        verbose: Enable debug logging.

    Returns:
        GeneratedGrid, or None if failed.
    """

    from .reference.executor import ExecutionContext, TransformationExecutor
    from .reference.resolver import resolve_reference
    from .reference.planner import TransformationPlanner

    src_ref = parse_reference(datum_in)
    dst_ref = parse_reference(datum_out)

    if isinstance(region, Region):
        region_obj = region
    else:
        regions = parse_region(region)
        if not regions:
            raise ValueError(f"Could not parse region: {region}")
        region_obj = regions[0]

    if isinstance(region_obj, Region):
        wgs84_region = _region_to_wgs84(region_obj, src_ref.horizontal)

    try:
        inc_val = str2inc(str(increment))
        nx = int(wgs84_region.width / inc_val)
        ny = int(wgs84_region.height / inc_val)
    except Exception as e:
        logger.error(f"Invalid increment '{increment}': {e}")
        raise

    effective_epoch_in = str_or(src_ref.coordinate_epoch, epoch_in)
    effective_epoch_out = str_or(dst_ref.coordinate_epoch, epoch_out)

    if src_ref.vertical is None or dst_ref.vertical is None:
        raise ValueError("A vertical reference is required.")

    if decay_distance_m is not None and decay_distance_m < 0:
        raise ValueError("decay_distance_m must be >= 0")

    if buffer_distance_m is not None and buffer_distance_m < 0:
        raise ValueError("buffer_distance_m must be >= 0")

    if max_vdatum_extension_m is not None and max_vdatum_extension_m < 0:
        raise ValueError("max_vdatum_extension_m must be >= 0")

    # --- Reference Module ---
    resolved_src = resolve_reference(
        src_ref,
        default_epoch=float(effective_epoch_in),
    )

    resolved_dst = resolve_reference(
        dst_ref,
        default_epoch=float(effective_epoch_out),
    )
    plan = TransformationPlanner.build_plan(resolved_src, resolved_dst)

    context = ExecutionContext(
        region=wgs84_region,
        nx=nx,
        ny=ny,
        cache_dir=Path(cache_dir) if cache_dir else Path.cwd() / "transformez_cache",
        decay_pixels=decay_pixels,
        decay_distance_m=decay_distance_m,
        buffer_distance_m=buffer_distance_m,
        max_vdatum_extension_m=max_vdatum_extension_m,
        extrapolate_inland=extrapolate_inland,
        use_stations=use_stations,
        verbose=verbose,
    )

    try:
        executor = TransformationExecutor(context=context)
        result = executor.execute(plan)
        shift_array = result.shift
        trace = result.trace
        uncertainty_array = None

        if verbose:
            logger.info("-" * 60)
            logger.info(f"Transformation Execution Trace: {datum_in} -> {datum_out}")

            if not trace:
                logger.info("  ✓ Identity Transformation (No Shift Applied)")
            else:
                for step_desc in trace:
                    logger.info(f"  {step_desc}")

            if np.any(shift_array) and not np.isnan(shift_array).all():
                mean_shift = np.nanmean(shift_array)
                min_shift = np.nanmin(shift_array)
                max_shift = np.nanmax(shift_array)
                logger.info(
                    f"  => Total Shift Applied (Mean: {mean_shift:.3f}m | "
                    f"Min: {min_shift:.3f}m | Max: {max_shift:.3f}m)"
                )
            else:
                logger.info("  => Total Shift Applied (Zero / Identity)")

            logger.info("-" * 60)

    except Exception as exc:
        raise RuntimeError("Transformation failed to generate a shift grid.") from exc

    provenance = {
        "TIFFTAG_SOFTWARE": f"Transformez v{__version__}",
        "TIFFTAG_DATETIME": datetime.datetime.now().strftime("%Y:%m:%d %H:%M:%S"),
        "TRANSFORMEZ_DATUM_IN": str(datum_in),
        "TRANSFORMEZ_DATUM_OUT": str(datum_out),
        "TRANSFORMEZ_DECAY_MODE": (
            "physical" if decay_distance_m is not None else "pixels"
        ),
        "TRANSFORMEZ_DECAY_PIXELS": str(decay_pixels),
        "TRANSFORMEZ_DECAY_DISTANCE_M": str(decay_distance_m),
        "TRANSFORMEZ_BUFFER_DISTANCE_M": str(buffer_distance_m),
        "TRANSFORMEZ_MAX_VDATUM_EXTENSION_M": str(max_vdatum_extension_m),
        "TRANSFORMEZ_REFERENCE_IN": (src_ref.vertical.id if src_ref.vertical else ""),
        "TRANSFORMEZ_REFERENCE_OUT": (dst_ref.vertical.id if dst_ref.vertical else ""),
        "TRANSFORMEZ_EPOCH_IN": effective_epoch_in,
        "TRANSFORMEZ_EPOCH_OUT": effective_epoch_out,
        "TRANSFORMEZ_GRID_CRS": "EPSG:4326",
        "TRANSFORMEZ_INCREMENT": str(increment),
        "TRANSFORMEZ_EXTRAPOLATE_INLAND": str(extrapolate_inland),
        "TRANSFORMEZ_USE_STATIONS": str(use_stations),
    }

    wgs_transform = from_bounds(
        wgs84_region.xmin,
        wgs84_region.ymin,
        wgs84_region.xmax,
        wgs84_region.ymax,
        nx,
        ny,
    )

    generation_key = _generation_key(
        wgs84_region,
        increment,
        src_ref,
        dst_ref,
        effective_epoch_in,
        effective_epoch_out,
        decay_pixels,
        decay_distance_m,
        buffer_distance_m,
        max_vdatum_extension_m,
        extrapolate_inland,
        use_stations,
    )

    return ShiftGrid(
        array=shift_array,
        region=wgs84_region,
        crs=CRS.from_epsg(4326),
        transform=wgs_transform,
        source_reference=src_ref,
        target_reference=dst_ref,
        epoch_in=effective_epoch_in,
        epoch_out=effective_epoch_out,
        provenance=provenance,
        generation_key=generation_key,
        trace=trace,
        uncertainty=uncertainty_array,
        cache_dir=context.cache_dir,
    )
