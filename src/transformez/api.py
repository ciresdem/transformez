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

import os
import logging
import numpy as np
from typing import List, Union, Optional, Tuple, Any
import datetime

from .transform import VerticalTransform
from .definitions import Datums
from .grid_engine import GridWriter, GridEngine
from .srs import SRSParser
from .utils import RasterQuery

from fetchez.spatial import parse_region, Region
from fetchez import utils

from transformez import __version__

logger = logging.getLogger(__name__)


def _parse_datum(datum_arg: str) -> Tuple[Optional[int], Optional[str]]:
    """Helper to parse compound datum strings (e.g. '5703:g2012b').

    Args:
        datum_arg: Datum string, possibly with geoid suffix.

    Returns:
        Tuple of (EPSG code, optional geoid name).
    """

    if not datum_arg:
        return None, None

    s = str(datum_arg)
    if ":" in s:
        parts = s.split(":")
        geoid_part = parts[1]
        geoid = geoid_part.split("=")[1] if "geoid=" in geoid_part else geoid_part

        return Datums.get_vdatum_by_name(parts[0]), geoid

    return Datums.get_vdatum_by_name(s), None


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
    out_fn: Optional[str] = None,
    cache_dir: Optional[str] = None,
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
        decay_pixels: Pixels for inland extrapolation decay.
        out_fn: If provided, saves the grid to this file (.tif or .gtx).
        cache_dir: Path to store downloaded grids.
        use_stations: Force RBF interpolation using live tide stations.
        verbose: Enable debug logging.

    Returns:
        2D vertical shift grid, or None if failed.
    """

    if isinstance(region, Region):
        region_obj = region
    else:
        regions = parse_region(region)
        if not regions:
            raise ValueError(f"Could not parse region: {region}")
        region_obj = regions[0]

    try:
        inc_val = utils.str2inc(str(increment))
        nx = int(region_obj.width / inc_val)
        ny = int(region_obj.height / inc_val)
    except Exception as e:
        logger.error(f"Invalid increment '{increment}': {e}")
        raise

    epsg_in, geoid_in = _parse_datum(datum_in)
    epsg_out, geoid_out = _parse_datum(datum_out)

    if epsg_in is None or epsg_out is None:
        raise ValueError(f"Invalid datum specified: {datum_in} -> {datum_out}")

    vt = VerticalTransform(
        region=region_obj,
        nx=nx,
        ny=ny,
        epsg_in=epsg_in,
        epsg_out=epsg_out,
        geoid_in=geoid_in,
        geoid_out=geoid_out,
        epoch_in=epoch_in,
        epoch_out=epoch_out,
        decay_pixels=decay_pixels,
        cache_dir=cache_dir,
        use_stations=use_stations,
        verbose=verbose,
    )

    shift_array, _ = vt._vertical_transform()

    if shift_array is None:
        logger.error("Transformation failed to generate a grid.")
        return None

    if out_fn:
        provenance = {
            "TIFFTAG_SOFTWARE": f"Transformez v{__version__}",
            "TIFFTAG_DATETIME": datetime.datetime.now().strftime("%Y:%m:%d %H:%M:%S"),
            "TRANSFORMEZ_DATUM_IN": str(datum_in),
            "TRANSFORMEZ_DATUM_OUT": str(datum_out),
            "TRANSFORMEZ_DECAY_PIXELS": str(decay_pixels),
        }

        GridWriter.write(out_fn, shift_array, region_obj, tags=provenance)
        logger.info(f"Saved shift grid to {out_fn}")

    return shift_array


def transform_raster(
    input_raster: str,
    datum_in: str,
    datum_out: str,
    decay_pixels: int = 100,
    output_raster: Optional[str] = None,
    cache_dir: Optional[str] = None,
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
        output_raster: Path to save the transformed DEM. Auto-named if None.
        decay_pixels: Pixels for inland extrapolation decay.
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
    from rasterio.warp import transform_bounds
    from rasterio.transform import from_bounds
    from fetchez.spatial import Region

    if not os.path.exists(input_raster):
        raise ValueError(f"Input raster not found: {input_raster}")

    with rasterio.open(input_raster) as src:
        native_crs = src.crs
        native_bounds = src.bounds
        native_transform = src.transform
        nx, ny = src.width, src.height

    is_projected = native_crs.is_projected if native_crs else False
    if is_projected:
        logger.info(
            f"Projected CRS detected ({native_crs}). Extracting WGS84 envelope..."
        )
        w, s, e, n = transform_bounds(native_crs, "EPSG:4326", *native_bounds)

        buffer = 0.05
        region_obj = Region(w - buffer, e + buffer, s - buffer, n + buffer)
        logger.info(f"Using WGS84 region: {region_obj}")

        inc_deg = 3.0 / 3600.0
        vt_nx = int((region_obj.xmax - region_obj.xmin) / inc_deg)
        vt_ny = int((region_obj.ymax - region_obj.ymin) / inc_deg)
    else:
        region_obj = Region(
            native_bounds.left,
            native_bounds.right,
            native_bounds.bottom,
            native_bounds.top,
        )
        vt_nx, vt_ny = nx, ny

    epsg_in, geoid_in = _parse_datum(datum_in)
    epsg_out, geoid_out = _parse_datum(datum_out)

    if z_unit_in == "auto":
        z_unit_in = Datums.get_unit(epsg_in)

    if z_unit_out == "auto":
        z_unit_out = Datums.get_unit(epsg_out)

    if z_unit_in != "m" or z_unit_out != "m":
        logger.info(f"Auto-detected Unit Conversion: {z_unit_in} -> {z_unit_out}")

    if epsg_in is None or epsg_out is None:
        logger.error(f"Invalid datum specified: {datum_in} -> {datum_out}")
        return None

    if not output_raster:
        base, ext = os.path.splitext(input_raster)
        output_raster = f"{base}_trans_{datum_out.replace(':', '_')}{ext}"

    vt = VerticalTransform(
        region=region_obj,
        nx=nx,
        ny=ny,
        epsg_in=epsg_in,
        epsg_out=epsg_out,
        geoid_in=geoid_in,
        geoid_out=geoid_out,
        decay_pixels=decay_pixels,
        cache_dir=cache_dir,
        use_stations=use_stations,
        verbose=verbose,
    )

    shift_array, _ = vt._vertical_transform()

    if shift_array is None:
        logger.error("Failed to generate shift array for the raster bounds.")
        return None

    provenance = {
        "TIFFTAG_SOFTWARE": f"Transformez v{__version__}",
        "TIFFTAG_DATETIME": datetime.datetime.now().strftime("%Y:%m:%d %H:%M:%S"),
        "TRANSFORMEZ_DATUM_IN": str(datum_in),
        "TRANSFORMEZ_DATUM_OUT": str(datum_out),
        "TRANSFORMEZ_DECAY_PIXELS": str(decay_pixels),
    }

    if is_projected:
        logger.debug("Streaming raster via windowed I/O...")
        wgs_transform = from_bounds(
            region_obj.xmin,
            region_obj.ymin,
            region_obj.xmax,
            region_obj.ymax,
            vt_nx,
            vt_ny,
        )

        success = GridEngine.apply_vertical_shift(
            src_dem=input_raster,
            shift_array=shift_array,
            dst_dem=output_raster,
            z_unit_in=z_unit_in,
            z_unit_out=z_unit_out,
            shift_transform=wgs_transform,
            shift_crs="EPSG:4326",
            tags=provenance,
        )
    else:
        # If it's already in Geographic (EPSG:4326), just pass it standardly
        success = GridEngine.apply_vertical_shift(
            src_dem=input_raster,
            shift_array=shift_array,
            dst_dem=output_raster,
            z_unit_in=z_unit_in,
            z_unit_out=z_unit_out,
            tags=provenance,
        )

    if save_shift and not is_projected:
        shift_fn = f"{os.path.splitext(output_raster)[0]}_shiftgrid.tif"
        logger.info(f"Saving aligned shift grid to {shift_fn}...")
        with rasterio.open(
            shift_fn,
            "w",
            driver="GTiff",
            height=ny,
            width=nx,
            count=1,
            dtype=shift_array.dtype,
            crs=native_crs,
            transform=native_transform,
            nodata=-9999.0,
        ) as dst:
            if provenance:
                dst.update_tags(**provenance)

            dst.write(shift_array, 1)
    elif save_shift and is_projected:
        logger.warning(
            "Skipping --save-shift: Cannot export a dense native shift grid for memory-safe projected runs."
        )

    return output_raster if success else None


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
        cache_dir: str = ".",
    ):
        parser = SRSParser(src_srs, dst_srs, region=region, cache_dir=cache_dir)
        self.horz_transformer, self.grid_path = parser.get_components()

        self.raster_query = RasterQuery(self.grid_path) if self.grid_path else None

        self.factor_in = Datums.get_unit_factor(z_unit_in)
        self.factor_out = Datums.get_unit_factor(z_unit_out)

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
            q_x = [x] if is_scalar else x
            q_y = [y] if is_scalar else y

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
        out_x, out_y = self.horz_transformer.transform(x, y)

        return out_x, out_y, z_out


def prefetch_region(
    region: Union[List[float], str, Region],
    datum_in: Optional[str] = None,
    datum_out: Optional[str] = None,
    fetch_all: bool = False,
    cache_dir: Optional[str] = None,
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
            logger.info(" -> [1/5] Fetching Dist2Coast land mask...")
            vt._fetch_ocean_mask()

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
            epsg_in, geoid_in = _parse_datum(datum_in) if datum_in else (4979, None)
            epsg_out, geoid_out = _parse_datum(datum_out) if datum_out else (6319, None)

            logger.info(
                f"Mode: TARGETED PREFETCH for chain ({datum_in or 'WGS84'} ➔ {datum_out or 'NAD83'})..."
            )

            vt = VerticalTransform(
                region=region_obj,
                nx=vt_nx,
                ny=vt_ny,
                epsg_in=epsg_in or 4979,
                epsg_out=epsg_out or 6319,
                geoid_in=geoid_in,
                geoid_out=geoid_out,
                cache_dir=cache_dir,
                verbose=verbose,
            )

            vt._vertical_transform()

        logger.info("Successfully populated offline cache!")
        return True

    except Exception as e:
        logger.error(f"Prefetch failed: {e}")
        return False
