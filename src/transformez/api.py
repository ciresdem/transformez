#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.api
~~~~~~~~~~~~~~~
High-level Python Interface for Transformez.

Usage::

    import transformez

    # Generate a shift grid (returns a numpy array)
    shift_array = transformez.generate_grid(
        region=[-90, -89, 29, 30],
        increment="3s",
        datum_in="mllw",
        datum_out="5703",
    )

    # Transform an existing DEM directly
    out_file = transformez.transform_raster(
        input_raster="my_dem_mllw.tif",
        datum_in="mllw",
        datum_out="5703:g2012b",
        output_raster="my_dem_navd88.tif",
    )
"""

import logging
from pathlib import Path
import numpy as np
from typing import List, Union, Optional, Tuple, Any
from dataclasses import dataclass

from pyproj import Transformer

from .transform import VerticalTransform
from .grid_engine import GridEngine
from .utils import RasterQuery, UNITS
from .reference.parser import parse_reference
from .reference.adapter import adapt_reference
from .generation import build_shift_grid, ShiftGrid

from fetchez.spatial import parse_region, Region

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TransformationComponents:
    horizontal: Transformer | None
    vertical: ShiftGrid | None


def plot_grid(
    grid_array: np.ndarray, region: Region, title: str = "Vertical Shift Preview"
) -> None:
    """Plot the transformation grid using Matplotlib.

    Requires the 'preview' extra to be installed.

    Args:
        grid_array: 2D array of vertical shift values.
        region: Geographic region object or bounds list/string.
        title: Plot title.
    """

    try:
        import matplotlib.pyplot as plt
    except ImportError:
        logger.warning("Matplotlib is not installed. Cannot generate preview.")
        return None

    if isinstance(region, Region):
        region_obj = region
    else:
        regions = parse_region(region)
        if not regions:
            logger.error(f"Could not parse region: {region}")
            return None
        region_obj = regions[0]

    masked_data = np.ma.masked_where(
        (np.isnan(grid_array)) | (grid_array == -9999) | (grid_array == 0), grid_array
    )

    if masked_data.count() == 0:
        logger.warning("Preview skipped: Grid contains no valid data.")
        return None

    plt.figure(figsize=(10, 6))
    plot_region = [region_obj.xmin, region_obj.xmax, region_obj.ymin, region_obj.ymax]

    # im = plt.imshow(masked_data, extent=plot_region, cmap="RdBu_r", origin="upper")
    im = plt.imshow(masked_data, extent=plot_region, cmap="viridis", origin="upper")
    cbar = plt.colorbar(im)
    cbar.set_label("Vertical Shift (meters)")
    plt.title(title)
    plt.xlabel("Longitude")
    plt.ylabel("Latitude")
    plt.grid(True, linestyle=":", alpha=0.6)

    stats = (
        f"Min: {masked_data.min():.3f} m\n"
        f"Max: {masked_data.max():.3f} m\n"
        f"Mean: {masked_data.mean():.3f} m"
    )
    plt.annotate(
        stats,
        xy=(0.02, 0.02),
        xycoords="axes fraction",
        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="gray", alpha=0.8),
    )
    logger.info("Displaying preview... Close the plot window to continue.")
    plt.show()


def generate_grid(
    region: Union[List[float], str, Region],
    increment: Union[str, float],
    datum_in: str,
    datum_out: str,
    epoch_in: str = "2010.0",
    epoch_out: str = "2010.0",
    decay_pixels: int = 100,
    decay_distance_m: Optional[float] = None,
    buffer_distance_m: Optional[float] = None,
    max_vdatum_extension_m: Optional[float] = None,
    extrapolate_inland: bool = False,
    out_fn: Optional[str | Path] = None,
    cache_dir: Optional[str | Path] = None,
    use_stations: bool = False,
    verbose: bool = False,
) -> Optional[np.ndarray]:
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
        out_fn: If provided, saves the grid to this file (.tif or .gtx).
        cache_dir: Path to store downloaded grids.
        use_stations: Force RBF interpolation using live tide stations.
        verbose: Enable debug logging.

    Returns:
        2D vertical shift grid, or None if failed.
    """

    cache_dir = (
        Path(cache_dir) if cache_dir is not None else Path.cwd() / "transformez_cache"
    )
    shift_grid = build_shift_grid(
        region,
        increment,
        datum_in,
        datum_out,
        epoch_in,
        epoch_out,
        decay_pixels,
        decay_distance_m,
        buffer_distance_m,
        max_vdatum_extension_m,
        extrapolate_inland,
        cache_dir,
        use_stations,
        verbose,
    )

    if out_fn:
        shift_grid.write(out_fn)
        logger.info(f"Saved shift grid to {out_fn}")

    return shift_grid.array


def build_components(
    src_srs: str,
    dst_srs: str,
    region: Region | str | list[float] | None = None,
    increment: str | float = "3s",
    cache_dir: str | Path | None = None,
    **vertical_options: Any,
) -> TransformationComponents:
    source = parse_reference(src_srs)
    target = parse_reference(dst_srs)

    cache_dir = Path(cache_dir) if cache_dir else None

    if isinstance(region, Region):
        region_obj = region
    else:
        regions = parse_region(region)
        if not regions:
            raise ValueError(f"Could not parse region: {region}")
        region_obj = regions[0]

    horizontal = None
    if source.horizontal and target.horizontal:
        if source.horizontal != target.horizontal:
            horizontal = Transformer.from_crs(
                source.horizontal,
                target.horizontal,
                always_xy=True,
            )

    vertical = None
    if source.vertical or target.vertical:
        if source.vertical is None or target.vertical is None:
            raise ValueError("Both source and target vertical references are required.")

        vertical = build_shift_grid(
            region=region_obj,
            increment=increment,
            datum_in=src_srs,
            datum_out=dst_srs,
            cache_dir=cache_dir,
            **vertical_options,
        )

        if source.horizontal is not None:
            vertical = vertical.reproject(
                source.horizontal,
                dst_region=region_obj,
            )

    return TransformationComponents(
        horizontal=horizontal,
        vertical=vertical,
    )


def transform_raster(
    input_raster: str | Path,
    datum_in: str,
    datum_out: str,
    epoch_in: str = "2010.0",
    epoch_out: str = "2010.0",
    decay_pixels: int = 100,
    decay_distance_m: Optional[float] = None,
    buffer_distance_m: Optional[float] = None,
    max_vdatum_extension_m: Optional[float] = None,
    extrapolate_inland: bool = False,
    output_raster: Optional[str | Path] = None,
    cache_dir: Optional[str | Path] = None,
    z_unit_in: str = "auto",
    z_unit_out: str = "auto",
    use_stations: bool = False,
    save_shift: bool = False,
    verbose: bool = False,
) -> Optional[str]:
    """Apply a vertical datum transformation directly to an existing raster file.

    Args:
        input_raster: Path to the input DEM.
        datum_in: Source datum of the DEM.
        datum_out: Target datum for the output DEM.
        epoch_in: Source epoch (e.g., '2010.0').
        epoch_out: Target epoch (e.g., '2010.0').
        output_raster: Path to save the transformed DEM. Auto-named if None.
        decay_pixels: Legacy pixel-based inland decay distance.
        decay_distance_m: Physical inland decay distance in meters. When set,
            this takes precedence over ``decay_pixels``.
        buffer_distance_m: Distance inland, in meters, to retain the full coastal
            shift before physical decay begins.
        max_vdatum_extension_m: Optional maximum inland distance where VDatum
            coverage may extend the effective water domain.
        extrapolate_inland: No decay will be performed and the shift values
             will be extrapolated for the entire region.
        cache_dir: Path to store downloaded grids.
        z_unit_in: Input DEM z units ('auto', 'm', 'ft', 'us-ft').
        z_unit_out: Output DEM z units ('auto', 'm', 'ft', 'us-ft').
        use_stations: Force RBF interpolation using live tide stations.
        save_shift: Save the generated shift raster to disk.
        verbose: Enable debug logging.

    Returns:
        Path to the transformed output raster, or None if failed.
    """

    import rasterio

    cache_dir = (
        Path(cache_dir) if cache_dir is not None else Path.cwd() / "transformez_cache"
    )
    input_raster = Path(input_raster)

    if not input_raster.exists():
        raise ValueError(f"Input raster not found: {input_raster}")

    if output_raster is None:
        output_raster = input_raster.with_name(
            f"{input_raster.stem}_trans_{datum_out.replace(':', '_')}"
            f"{input_raster.suffix}"
        )
    else:
        output_raster = Path(output_raster)

    with rasterio.open(input_raster) as src:
        native_crs = src.crs
        native_bounds = src.bounds
        # native_transform = src.transform
        nx, ny = src.width, src.height

    region_obj = Region(
        native_bounds.left,
        native_bounds.right,
        native_bounds.bottom,
        native_bounds.top,
    )
    region_obj.srs = native_crs.to_epsg() or native_crs.to_wkt()

    shift_grid = build_shift_grid(
        region_obj,
        "3s",
        datum_in,
        datum_out,
        epoch_in,
        epoch_out,
        decay_pixels,
        decay_distance_m,
        buffer_distance_m,
        max_vdatum_extension_m,
        extrapolate_inland,
        cache_dir,
        use_stations,
        verbose,
    )

    if (
        shift_grid.source_reference.vertical is not None
        and shift_grid.target_reference.vertical is not None
    ):
        if z_unit_in == "auto":
            z_unit_in = shift_grid.source_reference.vertical.unit_name

        if z_unit_out == "auto":
            z_unit_out = shift_grid.target_reference.vertical.unit_name

    aligned_shift = shift_grid.reproject(
        native_crs,
        dst_region=region_obj,
        dst_shape=(ny, nx),
    )

    success = GridEngine.apply_vertical_shift(
        src_dem=input_raster,
        shift_grid=aligned_shift,
        dst_dem=output_raster,
        z_unit_in=z_unit_in,
        z_unit_out=z_unit_out,
    )

    if save_shift:
        shift_fn = output_raster.with_name(f"{output_raster.stem}_shiftgrid.tif")
        aligned_shift.write(shift_fn)

    return str(output_raster) if success else None


class PointTransformer:
    """Unified API for transforming spatial coordinates (X, Y, Z).

    Handles horizontal reprojection, vertical datum shifts via cached grids,
    and Z-unit scaling (e.g., feet to meters) internally.
    """

    def __init__(
        self,
        src_srs: str,
        dst_srs: str,
        region: Any,
        z_unit_in: str = "m",
        z_unit_out: str = "m",
        cache_dir: Optional[str | Path] = None,
    ):
        cache_dir = (
            Path(cache_dir)
            if cache_dir is not None
            else Path.cwd() / "transformez_cache"
        )
        components = build_components(
            src_srs,
            dst_srs,
            region=region,
            cache_dir=cache_dir,
        )
        self.raster_query: RasterQuery | None

        self.horz_transformer = components.horizontal

        if components.vertical is not None:
            self.grid_path = components.vertical.write()
            self.raster_query = RasterQuery(self.grid_path)
        else:
            self.grid_path = None
            self.raster_query = None

        self.factor_in = UNITS.get_unit_factor_m(z_unit_in)
        self.factor_out = UNITS.get_unit_factor_m(z_unit_out)

    def transform(
        self,
        x: Union[float, np.ndarray],
        y: Union[float, np.ndarray],
        z: Union[float, np.ndarray],
    ) -> Tuple[
        Union[float, np.ndarray], Union[float, np.ndarray], Union[float, np.ndarray]
    ]:
        """Transforms coordinates horizontally and vertically.
        Accepts and returns either single scalar floats or NumPy arrays.

        Args:
            x: float or array of x value(s)
            y: float or array of y value(s)
            z: float or array of z value(s)

        Returns:
            Tuple of transformed x, y and z floats or arrays.
        """

        is_scalar = np.isscalar(x)

        # --- Vertical Transformation ---
        if self.raster_query:
            q_x = np.array([x]) if is_scalar else np.array(x)
            q_y = np.array([y]) if is_scalar else np.array(y)

            shift_meters = self.raster_query.query(q_x, q_y)

            z_meters = (np.array(z) * self.factor_in) + shift_meters
            z_out = z_meters / self.factor_out

            if is_scalar:
                z_out = float(z_out[0])
        else:
            z_out = (np.array(z) * self.factor_in) / self.factor_out
            if is_scalar:
                z_out = float(z_out)

        # --- Horizontal Transformation ---
        if self.horz_transformer is not None:
            out_x, out_y = self.horz_transformer.transform(x, y)
        else:
            out_x, out_y = x, y

        return out_x, out_y, z_out


def prefetch_region(
    region: Union[List[float], str, Region],
    datum_in: Optional[str] = None,
    datum_out: Optional[str] = None,
    fetch_all: bool = False,
    cache_dir: Optional[str | Path] = None,
    verbose: bool = True,
) -> bool:
    """Pre-download transformation grids and reference datasets for offline field use.

    Args:
        region: Bounds as [W, E, S, N], a 'loc:' string, or a Region object.
        datum_in: Source datum string to limit fetching to a specific chain.
        datum_out: Target datum string to limit fetching to a specific chain.
        fetch_all: If True, fetches ALL available geoids, tidal surfaces, coastlines.
        cache_dir: Directory where downloaded assets will be cached.
        verbose: Enable detailed logging.

    Returns:
        True if prefetching succeeded, False otherwise.
    """

    from .definitions import Datums

    cache_dir = (
        Path(cache_dir) if cache_dir is not None else Path.cwd() / "transformez_cache"
    )

    if isinstance(region, Region):
        region_obj = region
    else:
        regions = parse_region(region)
        if not regions:
            raise ValueError(f"Could not parse region: {region}")
        region_obj = regions[0]

    logger.info(f"Initiating offline prefetch for region: {region_obj}")

    # Minimal dimensions (10x10) to avoid allocating memory for large arrays
    vt_nx, vt_ny = 10, 10

    try:
        if fetch_all or (not datum_in and not datum_out):
            logger.info(
                "Mode: FULL PREFETCH. Downloading all geoids, VDatum grids, and coastlines..."
            )

            # Instantiate base engine to leverage internal fetchers
            vt = VerticalTransform(
                region=region_obj,
                nx=vt_nx,
                ny=vt_ny,
                epsg_in=4979,  # Base WGS84
                epsg_out=6319,  # Base NAD83
                cache_dir=cache_dir,
                verbose=verbose,
            )

            # Dist2Coast landmask
            logger.info(" -> [1/5] Fetching Dist2Coast signed-distance grid...")
            vt._fetch_dist2coast_m()

            # All Registered Geoids
            logger.info(" -> [2/5] Fetching Geoid grids...")
            for g_name, g_def in Datums.GEOIDS.items():
                provider = g_def.get("provider", "proj")
                logger.info(f"    - Fetching Geoid: {g_name} ({provider})")
                try:
                    vt.fetch_grid(provider, datatype=g_name, query=g_name)
                except Exception as e:
                    logger.warning(f"    - Skipping '{g_name}': {e}")

            # USA VDatum Tidal Grids
            logger.info(" -> [3/5] Fetching VDatum regional grids...")
            for s_key, s_def in Datums.SURFACES.items():
                s_name = s_def.get("name", s_key)
                if s_def.get("region") == "usa":
                    logger.info(f"    - Fetching VDatum Surface: {s_name}")
                    try:
                        vt.fetch_grid("vdatum", datatype=s_name, query=s_name)
                    except Exception as e:
                        logger.warning(f"    - Skipping VDatum '{s_name}': {e}")

            # Topography of the Sea Surface (TSS)
            logger.info(" -> [4/5] Fetching VDatum TSS grid...")
            try:
                vt.fetch_grid("vdatum", datatype="tss", query="tss")
            except Exception as e:
                logger.warning(f"    - Skipping TSS: {e}")

            # Global Satellite Models (FES / SEANOE)
            logger.info(" -> [5/5] Fetching Global FES / MSS proxy grids...")
            for proxy_name in ["lat", "msl", "mss"]:
                logger.info(f"    - Fetching Global Proxy: {proxy_name}")
                try:
                    vt.fetch_grid(
                        "fes" if proxy_name != "mss" else "dtu",
                        datatype=proxy_name,
                        query=proxy_name,
                    )
                except Exception as e:
                    logger.warning(f"    - Skipping Global '{proxy_name}': {e}")

        else:
            src_ref = adapt_reference(datum_in)
            dst_ref = adapt_reference(datum_out)

            if src_ref.vertical is None or dst_ref.vertical is None:
                raise ValueError("A vertical reference is required.")

            logger.info(
                f"Mode: TARGETED PREFETCH for chain ({datum_in or 'WGS84'} ➔ {datum_out or 'NAD83'})..."
            )

            vt = VerticalTransform(
                region=region_obj,
                nx=vt_nx,
                ny=vt_ny,
                epsg_in=src_ref.vertical.epsg or 4979,
                epsg_out=dst_ref.vertical.epsg or 6319,
                geoid_in=src_ref.vertical.geoid,
                geoid_out=dst_ref.vertical.geoid,
                cache_dir=cache_dir,
                verbose=verbose,
            )

            vt._vertical_transform()

        logger.info("Successfully populated offline cache!")
        return True

    except Exception as e:
        logger.error(f"Prefetch failed: {e}")
        return False
