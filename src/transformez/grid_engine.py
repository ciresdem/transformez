#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.grid_engine
~~~~~~~~~~~~~~~~~~~~~~~

Grid compositing utility.
Uses rasterio.warp.reproject (GDAL) with in-memory pre-cleaning to prevent
floating-point nodata leaks and spline ringing at data boundaries.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import logging
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Tuple

import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling
from rasterio.transform import from_bounds
from scipy.ndimage import distance_transform_edt, gaussian_filter
from scipy.interpolate import Rbf

from fetchez.spatial import Region, parse_region

os.environ["HDF5_USE_FILE_LOCKING"] = "FALSE"

logger = logging.getLogger(__name__)


class GridCorruptionError(Exception):
    """Raised when a fetched grid is corrupted and needs re-downloading."""

    pass


def plot_grid(
    grid_array: np.ndarray,
    region: Region | str,
    title: str = "Vertical Shift Preview",
) -> None:
    """Plot the transformation grid using Matplotlib."""

    try:
        import matplotlib.pyplot as plt
    except ImportError:
        logger.warning("Matplotlib is not installed. Cannot generate preview.")
        return

    masked_data = np.ma.masked_where(
        (np.isnan(grid_array)) | (grid_array == -9999) | (grid_array == 0), grid_array
    )

    if masked_data.count() == 0:
        logger.warning("Preview skipped: Grid contains no valid data.")
        return

    if isinstance(region, Region):
        region_obj = region.copy()
    else:
        regions = parse_region(region)
        if not regions:
            raise ValueError(f"Could not parse region: {region}")
        region_obj = regions[0]

    plt.figure(figsize=(10, 6))
    plot_region = [region_obj.xmin, region_obj.xmax, region_obj.ymin, region_obj.ymax]

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


@dataclass(frozen=True)
class CoastalContext:
    """Coastal classification and physical inland-distance field.

    Attributes:
        water_mask: True where tidal/global proxy values are geographically allowed.
            Dist2Coast positive cells define native water and valid VDatum coverage
            may extend this mask landward.
        inland_distance_m: Physical distance inland from the effective water domain.
            Native negative Dist2Coast values are used directly. Dist2Coast zero
            cells are treated as an unresolved coastline band and assigned distance
            from the nearest definite-water cell. Water pixels are always zero.
        sampling_m: Approximate (row, column) pixel spacing in meters used by EDT
            when resolving zero-valued coastline cells or VDatum extensions.
    """

    water_mask: np.ndarray
    inland_distance_m: np.ndarray
    sampling_m: Tuple[float, float]


class GridEngine:
    @staticmethod
    def load_and_interpolate(
        source_files: List[str],
        target_region: Region | str,
        nx: int,
        ny: int,
        decay_pixels: int = 100,
        preserve_zero: bool = False,
    ):
        """Composites grids using GDAL/rasterio Warper.

        Args:
            source_files: List of input grid files (NetCDF, GTX, GeoTIFF).
            target_region: Target geographic region object.
            nx: Number of pixels along x-axis.
            ny: Number of pixels along y-axis.
            decay_pixels: Legacy argument retained for API compatibility. It is not
                used by the reprojection operation.
            preserve_zero: Preserve source cells equal to zero when the source
                metadata also declares zero as nodata. This is required for
                Dist2Coast, where zero identifies coastline-intersecting cells.

        Returns:
            2D array with composited grid data (NaN for no data).
        """

        if isinstance(target_region, str):
            regions = parse_region(target_region)
            if not regions:
                raise ValueError(f"Could not parse region: {target_region}")
            target_region = regions[0]

        if isinstance(target_region, Region):
            xmin, xmax, ymin, ymax = target_region
        else:
            raise ValueError(f"Could not parse region: {target_region}")

        dst_transform = from_bounds(xmin, ymin, xmax, ymax, nx, ny)
        dst_crs = "EPSG:4326"

        mosaic = np.full((ny, nx), np.nan, dtype=np.float32)

        for fn in source_files:
            if not os.path.exists(fn) and not fn.startswith("netcdf:"):
                continue

            try:
                with rasterio.open(fn) as src:
                    src_data = src.read(1).astype(np.float32)
                    src_nodata = src.nodata

                    preserve_zero_nodata = (
                        preserve_zero
                        and src_nodata is not None
                        and np.isclose(src_nodata, 0.0)
                    )
                    if src_nodata is not None and not preserve_zero_nodata:
                        src_data[np.isclose(src_data, src_nodata, atol=1e-4)] = np.nan
                    if fn.endswith(".gtx"):
                        src_data[np.isclose(src_data, -88.8888, atol=1e-2)] = np.nan

                    temp_buffer = np.full((ny, nx), np.nan, dtype=np.float32)

                    with rasterio.Env(CENTER_LONG=0):
                        reproject(
                            source=src_data,
                            destination=temp_buffer,
                            src_transform=src.transform,
                            src_crs=src.crs or "EPSG:4326",
                            src_nodata=np.nan,
                            dst_transform=dst_transform,
                            dst_crs=dst_crs,
                            dst_nodata=np.nan,
                            resampling=Resampling.bilinear,
                        )

                    valid_mask = ~np.isnan(temp_buffer)
                    mosaic[valid_mask] = temp_buffer[valid_mask]

            except Exception as e:
                error_msg = str(e)

                if any(
                    err in error_msg
                    for err in [
                        "-101",
                        "HDF error",
                        "not recognized as a supported file format",
                        "RasterioIOError",
                    ]
                ):
                    logger.error(f" CRITICAL: Corrupted grid chunk detected in {fn}!")

                    real_path = fn.split(":")[1] if fn.startswith("netcdf:") else fn
                    if os.path.exists(real_path):
                        logger.warning(
                            f"Auto-deleting corrupted cache file to force re-fetch: {real_path}"
                        )
                        try:
                            os.remove(real_path)
                        except OSError:
                            pass

                    raise GridCorruptionError(f"Corrupted file deleted: {real_path}")

                logger.exception(f"Failed to reproject {fn}: {e}")
                raise

        return mosaic

    @staticmethod
    def _pixel_sampling_m(
        target_region: Region | str,
        nx: int,
        ny: int,
    ) -> Tuple[float, float]:
        """Approximate north/south and east/west pixel spacing in meters.

        Transformez coastal models are generated in EPSG:4326.  A single EDT can
        only accept one sampling value per axis, so use the region midpoint for
        the longitude scale.  Dist2Coast remains the primary distance source; this
        approximation is only used where VDatum changes the effective shoreline.
        """

        if isinstance(target_region, str):
            regions = parse_region(target_region)
            if not regions:
                raise ValueError(f"Could not parse region: {target_region}")
            target_region = regions[0]

        if not isinstance(target_region, Region):
            raise ValueError(f"Could not parse region: {target_region}")

        mean_lat = 0.5 * (target_region.ymin + target_region.ymax)
        dy_deg = target_region.height / max(ny, 1)
        dx_deg = target_region.width / max(nx, 1)

        # Good local approximations for a geographic working grid.
        dy_m = abs(dy_deg) * 110_574.0
        dx_m = abs(dx_deg) * 111_320.0 * np.cos(np.deg2rad(mean_lat))

        return max(dy_m, 1e-6), max(dx_m, 1e-6)

    @staticmethod
    def build_coastal_context(
        signed_distance_m: np.ndarray,
        target_region: Region | str,
        vdatum_valid: Optional[np.ndarray] = None,
        max_vdatum_extension_m: Optional[float] = None,
    ) -> CoastalContext:
        """Build the effective tidal-water domain and physical inland distances.

        Dist2Coast supplies the native signed distance field: positive values are
        definite water, negative values are definite land, and zero-valued cells
        represent source cells intersected by the coastline. Zero cells are assigned
        a physical distance from the nearest definite-water cell instead of being
        treated as a full-strength 0 m inland plateau.

        Valid VDatum cells may expand the water domain so decay begins at the VDatum
        coverage edge where it extends landward of the native shoreline. Native
        Dist2Coast land distances remain authoritative unless the VDatum-aware EDT
        provides a closer effective-water boundary.
        """

        if signed_distance_m.ndim != 2:
            raise ValueError("signed_distance_m must be a 2-D array")

        ny, nx = signed_distance_m.shape
        sampling_m = GridEngine._pixel_sampling_m(target_region, nx, ny)

        finite_d2c = np.isfinite(signed_distance_m)
        native_water = finite_d2c & (signed_distance_m > 0.0)
        native_land = finite_d2c & (signed_distance_m < 0.0)
        native_coast = finite_d2c & np.isclose(signed_distance_m, 0.0)
        water_mask = native_water.copy()
        accepted_extension = np.zeros_like(water_mask, dtype=bool)
        if vdatum_valid is not None:
            if vdatum_valid.shape != signed_distance_m.shape:
                raise ValueError("vdatum_valid and signed_distance_m shapes differ")

            accepted_extension = vdatum_valid & ~native_water
            if max_vdatum_extension_m is not None:
                accepted_extension &= finite_d2c & (
                    signed_distance_m >= -abs(max_vdatum_extension_m)
                )

            water_mask |= accepted_extension

        # Dist2Coast already gives the best physical distance to its own
        # shoreline.  Convert signed land distances to positive inland meters.
        native_inland_m = np.full(
            signed_distance_m.shape,
            np.inf,
            dtype=np.float32,
        )

        # Known land: trust Dist2Coast's physical distance.
        native_inland_m[native_land] = -signed_distance_m[native_land]

        # Known water is zero distance inland.
        native_inland_m[native_water] = 0.0

        # Dist2Coast uses zero for cells intersected by the coastline. Because Dist2Coast
        # also sets zero as nodata, we must preserve these cells when loading the
        # signed-distance field. They are not true 0 m point distances, so resolve the band
        # from the nearest definite-water cell.
        if native_coast.any() and native_water.any():
            dist_from_water_m = distance_transform_edt(
                ~native_water,
                sampling=sampling_m,
            ).astype(np.float32)
            native_inland_m[native_coast] = dist_from_water_m[native_coast]

            coast_dist = native_inland_m[native_coast]
            logger.debug(
                "Dist2Coast coast band: %d pixels, inland distance %.1f to %.1f m",
                np.count_nonzero(native_coast),
                np.nanmin(coast_dist),
                np.nanmax(coast_dist),
            )

        if accepted_extension.any():
            # Distance to the union of native water + VDatum water.  We retain the
            # direct Dist2Coast value unless VDatum creates a closer boundary.
            effective_edt_m = distance_transform_edt(
                ~water_mask,
                sampling=sampling_m,
            ).astype(np.float32)
            inland_distance_m = np.minimum(native_inland_m, effective_edt_m)
        else:
            inland_distance_m = native_inland_m

        inland_distance_m[water_mask] = 0.0
        inland_distance_m[~np.isfinite(inland_distance_m)] = np.nan

        return CoastalContext(
            water_mask=water_mask,
            inland_distance_m=inland_distance_m,
            sampling_m=sampling_m,
        )

    @staticmethod
    def smart_blend(
        in_grid: np.ndarray,
        background_grid: np.ndarray,
        blend_pixels: int = 50,
    ) -> np.ndarray:
        """Smoothly blend a primary grid into a background grid.

        Args:
            in_grid: Primary grid (may contain NaNs).
            background_grid: Background grid to blend into.
            blend_pixels: Width of the blending zone in pixels.

        Returns:
            Blended grid with smooth transition.
        """
        mask = np.isnan(in_grid)

        if not mask.any():
            return in_grid
        if mask.all():
            return background_grid.copy()

        dist: Any = distance_transform_edt(mask)
        alpha = np.clip(dist / max(blend_pixels, 1), 0.0, 1.0)
        alpha = alpha * alpha * (3.0 - 2.0 * alpha)

        nearest_indices = distance_transform_edt(
            mask, return_distances=False, return_indices=True
        )
        extended_vdatum = in_grid.copy()
        extended_vdatum[mask] = in_grid[tuple(nearest_indices)][mask]

        return (extended_vdatum * (1.0 - alpha)) + (background_grid * alpha)

    @staticmethod
    def coastal_aware_composite(
        vdatum_grid: np.ndarray,
        global_grid: np.ndarray,
        nx: int,
        ny: int,
        ocean_mask: Optional[np.ndarray] = None,
        decay_pixels: int = 100,
        buffer_pixels: int = 10,
        blend_pixels: int = 50,
        coastal_context: Optional[CoastalContext] = None,
        decay_distance_m: Optional[float] = None,
        buffer_distance_m: float = 0.0,
    ) -> np.ndarray:
        """Blend VDatum with a global proxy and decay landward.

        ``coastal_context`` is the preferred path.  It separates two questions:
        where tidal values are allowed (``water_mask``), and how far inland a
        pixel lies (``inland_distance_m``).  Legacy pixel arguments remain for
        backwards compatibility.

        Args:
            vdatum_grid: High-resolution coastal tidal shift grid.
            global_grid: Lower-resolution global background grid.
            nx: Number of pixels along x-axis.
            ny: Number of pixels along y-axis.
            ocean_mask: Boolean mask where True = ocean.
            decay_pixels: Pixels for inland extrapolation decay.
            buffer_pixels: Buffer zone before inland decay begins.
            blend_pixels: Width of offshore blending zone.
            coastal_context: Context of the coastal domain. (Preferred)
        Returns:
            Composite grid with appropriate treatment for land/ocean/inland.
        """

        final_grid = vdatum_grid.copy()
        proxy_grid = global_grid.copy()

        water_mask = (
            coastal_context.water_mask if coastal_context is not None else ocean_mask
        )

        # Global proxies such as FES are consumers of the water mask, never
        # contributors to it.
        if water_mask is not None:
            proxy_grid[~water_mask] = np.nan

        is_vdatum = np.isfinite(vdatum_grid)
        if water_mask is not None:
            is_water = water_mask
        else:
            is_water = np.isfinite(proxy_grid)

        is_proxy = np.isfinite(proxy_grid)
        is_inland = ~is_vdatum & ~is_water
        is_offshore = ~is_vdatum & is_water & is_proxy

        if is_offshore.any():
            blended_ocean = GridEngine.smart_blend(
                vdatum_grid, proxy_grid, blend_pixels=blend_pixels
            )
            final_grid[is_offshore] = blended_ocean[is_offshore]

        if is_inland.any():
            decayed_inland = GridEngine.fill_nans(
                final_grid,
                decay_pixels=decay_pixels,
                buffer_pixels=buffer_pixels,
                ocean_mask=ocean_mask,
                coastal_context=coastal_context,
                decay_distance_m=decay_distance_m,
                buffer_distance_m=buffer_distance_m,
            )
            final_grid[is_inland] = decayed_inland[is_inland]

        return final_grid

    @staticmethod
    def fill_nans(
        data: np.ndarray,
        decay_pixels: int = 100,
        buffer_pixels: int = 10,
        ocean_mask: Optional[np.ndarray] = None,
        coastal_context: Optional[CoastalContext] = None,
        decay_distance_m: Optional[float] = None,
        buffer_distance_m: float = 0.0,
        extrapolate_inland: bool = False,
    ) -> np.ndarray:
        """Extrapolate coastal values landward and decay them toward zero.

        When ``coastal_context`` and ``decay_distance_m`` are supplied, decay is
        controlled in physical meters.

        Args:
            data: Input grid with NaN gaps to fill.
            decay_pixels: Distance over which values decay to zero (0 for infinite).
            buffer_pixels: Zone near coast where raw data is preserved.
            ocean_mask: Boolean mask where True = ocean (excluded from inland decay).
            coastal_context: The context of the coastal domain.
            buffer_distance_m: The buffer distance in meters to apply the tidal
                transformation from the coastal zone.

        Returns:
            Filled grid with extrapolated inland values.
        """

        out_data = data.copy()
        water_mask = (
            coastal_context.water_mask if coastal_context is not None else ocean_mask
        )

        if water_mask is not None:
            out_data[~water_mask] = np.nan

        mask = np.isnan(out_data)
        if not mask.any() or mask.all():
            return out_data

        sampling = (
            coastal_context.sampling_m
            if coastal_context is not None and decay_distance_m is not None
            else None
        )
        nearest_result = distance_transform_edt(
            mask,
            sampling=sampling,
            return_distances=True,
            return_indices=True,
        )
        nearest_dist, indices = nearest_result
        raw_extrapolation = out_data[tuple(indices)]

        if coastal_context is not None and decay_distance_m is not None:
            mean_pixel_m = 0.5 * sum(coastal_context.sampling_m)
            decay_pixels_equiv = max(decay_distance_m / max(mean_pixel_m, 1e-6), 1.0)
            blur_sigma = min(50.0, max(1.0, decay_pixels_equiv / 5.0))
        else:
            # Legacy behavior, but remove the old sigma=10 floor which dominated
            # very small decay distances.
            blur_sigma = min(50.0, max(1.0, decay_pixels / 5.0))

        blurred_extrapolation = gaussian_filter(raw_extrapolation, sigma=blur_sigma)

        if coastal_context is not None and decay_distance_m is not None:
            inland_distance_m = coastal_context.inland_distance_m
            blur_blend = np.clip(
                inland_distance_m / max(decay_distance_m, 1e-6), 0.0, 1.0
            )
        else:
            blur_blend = np.clip(nearest_dist / max(decay_pixels, 1), 0.0, 1.0)

        coast_values = (raw_extrapolation * (1.0 - blur_blend)) + (
            blurred_extrapolation * blur_blend
        )

        if extrapolate_inland:
            out_data[mask] = coast_values[mask]
        elif coastal_context is not None and decay_distance_m is not None:
            effective_dist_m = np.clip(
                coastal_context.inland_distance_m - buffer_distance_m,
                0.0,
                None,
            )
            linear_decay = np.clip(
                (decay_distance_m - effective_dist_m) / max(decay_distance_m, 1e-6),
                0.0,
                1.0,
            )
            decay_factor = linear_decay * linear_decay * (3.0 - 2.0 * linear_decay)
            out_data[mask] = coast_values[mask] * decay_factor[mask]

        elif decay_pixels and decay_pixels > 0:
            effective_dist = np.clip(nearest_dist - buffer_pixels, 0.0, None)
            linear_decay = np.clip(
                (decay_pixels - effective_dist) / decay_pixels, 0.0, 1.0
            )
            decay_factor = linear_decay * linear_decay * (3.0 - 2.0 * linear_decay)
            out_data[mask] = coast_values[mask] * decay_factor[mask]

        else:
            out_data[mask] = coast_values[mask]

        return out_data

    @staticmethod
    def apply_vertical_shift(
        src_dem: str,
        shift_array: np.ndarray,
        dst_dem: str,
        z_unit_in: str = "m",
        z_unit_out: str = "m",
        shift_transform: Optional[Any] = None,
        shift_crs: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> bool:
        """Apply a vertical shift array to a source DEM using memory-safe windowed I/O.

        Args:
            src_dem: Path to input DEM.
            shift_array: 2D shift grid (same projection as src_dem unless shift_transform given).
            dst_dem: Path to output transformed DEM.
            z_unit_in: Input DEM Z units ('m', 'ft', etc.).
            z_unit_out: Output DEM Z units.
            shift_transform: Transform matrix for shift_array (if different from src_dem).
            shift_crs: CRS of shift_array (if different from src_dem).
            tags: Metadata tags to apply to the transformed dem.

        Returns:
            True if successful, False otherwise.
        """

        from .definitions import Datums

        factor_in = Datums.get_unit_factor(z_unit_in)
        factor_out = Datums.get_unit_factor(z_unit_out)

        try:
            with rasterio.open(src_dem) as src:
                profile = src.profile.copy()
                profile.update(dtype="float32")

                if not profile.get("tiled"):
                    profile.update(tiled=True, blockxsize=256, blockysize=256)

                nodata = src.nodata if src.nodata is not None else -9999.0
                profile.update(nodata=nodata)

                with rasterio.open(dst_dem, "w", **profile) as dst:
                    if tags:
                        dst.update_tags(**tags)

                    for ji, window in dst.block_windows(1):
                        data_chunk = src.read(1, window=window).astype(np.float32)
                        if np.isnan(nodata):
                            if np.all(np.isnan(data_chunk)):
                                dst.write(data_chunk, 1, window=window)
                                continue
                        else:
                            if np.all((data_chunk == nodata) | np.isnan(data_chunk)):
                                dst.write(data_chunk, 1, window=window)
                                continue

                        if shift_transform and shift_crs:
                            window_transform = src.window_transform(window)
                            local_shift = np.zeros(data_chunk.shape, dtype=np.float32)

                            reproject(
                                source=shift_array,
                                destination=local_shift,
                                src_transform=shift_transform,
                                src_crs=shift_crs,
                                dst_transform=window_transform,
                                dst_crs=src.crs,
                                resampling=Resampling.bilinear,
                            )
                        else:
                            row_start = int(window.row_off)
                            row_end = int(window.row_off + window.height)
                            col_start = int(window.col_off)
                            col_end = int(window.col_off + window.width)

                            local_shift = shift_array[
                                row_start:row_end, col_start:col_end
                            ]

                        if src.nodata is None or np.isnan(src.nodata):
                            valid_mask = (~np.isnan(data_chunk)) & (
                                ~np.isnan(local_shift)
                            )
                        else:
                            valid_mask = (
                                (data_chunk != nodata)
                                & (~np.isnan(data_chunk))
                                & (~np.isnan(local_shift))
                            )
                        # valid_mask = (data_chunk != nodata) & (~np.isnan(local_shift))

                        data_meters = data_chunk[valid_mask] * factor_in
                        data_shifted_meters = data_meters + local_shift[valid_mask]

                        data_chunk[valid_mask] = data_shifted_meters / factor_out
                        data_chunk[~valid_mask] = nodata

                        dst.write(data_chunk, 1, window=window)

            logger.info(f"Successfully wrote transformed DEM to: {dst_dem}")
            return True

        except Exception as e:
            logger.error(f"Failed to apply shift to DEM: {e}")
            return False


class GridWriter:
    @staticmethod
    def write(
        filename: str,
        data: np.ndarray,
        region: Region | str,
        crs: Any = "EPSG:4326",
        tags: Optional[Dict[str, str]] = None,
        transform: Optional[Any] = None,
        nodata: Optional[float] = None,
    ) -> str:
        """Write a grid to a GeoTIFF.

        Args:
            filename: Output grid filename.
            data: Two-dimensional array to write.
            region: Region used to derive georeferencing when ``transform`` is omitted.
            crs: Coordinate reference system for the output grid.
            tags: Optional metadata tags to write.
            transform: Optional explicit raster transform.
            nodata: Optional nodata value.

        Returns:
            Path to the written GeoTIFF.
        """
        dirname = os.path.dirname(filename)
        if dirname and not os.path.exists(dirname):
            os.makedirs(dirname)

        if not filename.endswith(".tif"):
            filename = os.path.splitext(filename)[0] + ".tif"
        rows, cols = data.shape
        if transform is None:
            if isinstance(region, str):
                regions = parse_region(region)
                if not regions:
                    raise ValueError(f"Could not parse region: {region}")
                region = regions[0]
            if isinstance(region, Region):
                xmin, xmax, ymin, ymax = region
            else:
                raise ValueError(f"Could not parse region: {region}")
            res_x = (xmax - xmin) / cols
            res_y = (ymax - ymin) / rows
            transform = rasterio.transform.from_origin(xmin, ymax, res_x, res_y)

        raster_crs = crs.to_wkt() if hasattr(crs, "to_wkt") else crs
        with rasterio.open(
            filename,
            "w",
            driver="GTiff",
            height=rows,
            width=cols,
            count=1,
            dtype="float32",
            crs=raster_crs,
            transform=transform,
            nodata=nodata,
            compress="deflate",
            tiled=True,
        ) as dst:
            dst.write(data.astype("float32"), 1)
            if tags:
                dst.update_tags(**tags)
        return filename


def calculate_psmsl_msl(csv_path: str) -> float:
    """Reads a PSMSL time-series CSV generated by fetchez, filters out
    missing data flags (-99999), and calculates the all-time Mean Sea Level.

    Args:
        csv_path: Path to PSMSL CSV file.

    Returns:
        MSL value in meters (np.nan if no valid data).
    """

    import csv

    valid_measurements = []

    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter=";")
            for row in reader:
                if len(row) < 4:
                    continue

                try:
                    # Column 1 is the MSL value in millimeters
                    msl_mm = float(row[1].strip())
                    if msl_mm != -99999.0:
                        valid_measurements.append(msl_mm)
                except ValueError:
                    continue

        if not valid_measurements:
            logger.warning(f"No valid data found in {csv_path}")
            return np.nan

        # Calculate the mean in mm, then convert to meters
        mean_mm = sum(valid_measurements) / len(valid_measurements)
        mean_meters = mean_mm / 1000.0

        logger.info(
            f"Processed {len(valid_measurements)} months of data. MSL: {mean_meters:.3f} m"
        )
        return mean_meters

    except Exception as e:
        logger.error(f"Failed to process PSMSL file {csv_path}: {e}")
        return np.nan


class GridGen:
    @staticmethod
    def from_stations(
        region: Region | str,
        nx: int,
        ny: int,
        datum_in: str,
        datum_out: str,
        shapefiles: Optional[List[str]] = None,
        baseline_grid: Optional[np.ndarray] = None,
    ) -> Optional[np.ndarray]:
        """Dynamically generates a tidal shift grid using live tide stations.

        If a station lacks the target datum, it falls back to MSL and uses the
        baseline_grid (FES) to bridge the gap to the geodetic frame.

        Args:
            region: Geographic region object.
            nx: Number of pixels along x-axis.
            ny: Number of pixels along y-axis.
            datum_in: Source datum name (lowercase).
            datum_out: Target datum name (lowercase).
            shapefiles: Optional list of coastline shapefile paths.
            baseline_grid: Optional baseline grid (FES offset) for floating stations.

        Returns:
            Interpolated shift grid (2D array), or None if generation failed.
        """

        import json
        from fetchez.modules.tides import Tides
        from fetchez.core import run_fetchez

        if isinstance(region, str):
            regions = parse_region(region)
            if not regions:
                raise ValueError(f"Could not parse region: {region}")
            region = regions[0]

        if not isinstance(region, Region):
            raise ValueError(f"Could not parse region: {region}")

        tides_fetcher = Tides(src_region=region, mode="search")
        tides_fetcher.run()

        if not tides_fetcher.results:
            logger.error("Failed to fetch tide stations GeoJSON.")
            return None

        _ = run_fetchez([tides_fetcher], threads=1)

        geojson_path = tides_fetcher.results[0]["dst_fn"]
        if not os.path.exists(geojson_path):
            logger.error(f"GeoJSON file not found: {geojson_path}")
            return None

        with open(geojson_path, "r") as f:
            data = json.load(f)

        features = data.get("features", [])
        if not features:
            logger.error("No valid tide stations found in this region.")
            return None

        x: List[float] = []
        y: List[float] = []
        z: List[float] = []

        d_in = datum_in.lower()
        d_out = datum_out.lower()

        # Calculate pixel resolution for baseline grid sampling
        res_x = (region.xmax - region.xmin) / nx
        res_y = (region.ymax - region.ymin) / ny

        for feat in features:
            props = feat.get("properties", {})
            geom = feat.get("geometry", {})

            val_in = props.get(d_in)
            if val_in is None or val_in < -90000:
                continue

            val_out = props.get(d_out)
            shift: Optional[float] = None
            units = props.get("units", "meters").lower()

            # --- Perfect Data (Station has NAVD88) ---
            if val_out is not None and val_out > -90000:
                shift = val_in - val_out
                if units == "feet":
                    shift *= 0.3048

            # --- Floating Station (Lacks NAVD88, but has MSL) ---
            elif baseline_grid is not None and "msl" in props:
                val_msl = props.get("msl")
                if val_msl is not None and val_msl > -90000:
                    lon = geom["coordinates"][0]
                    lat = geom["coordinates"][1]

                    x_idx = int((lon - region.xmin) / res_x)
                    y_idx = int((region.ymax - lat) / res_y)

                    if 0 <= x_idx < nx and 0 <= y_idx < ny:
                        fes_offset = baseline_grid[y_idx, x_idx]
                        if not np.isnan(fes_offset):
                            # Get the local tidal envelope to MSL
                            shift_to_msl = val_in - val_msl
                            if units == "feet":
                                shift_to_msl *= 0.3048

                            # Add the FES baseline offset to tie it to NAVD88
                            shift = shift_to_msl + fes_offset

            if shift is not None:
                x.append(geom["coordinates"][0])
                y.append(geom["coordinates"][1])
                z.append(shift)

        if len(z) == 0:
            logger.error("No stations with matching datums found in the GeoJSON.")
            return None

        if len(z) < 3:
            logger.warning(
                f"Only {len(z)} station(s) found. Applying a constant average offset instead of RBF."
            )
            constant_shift = sum(z) / len(z)
            rbf_grid = np.full((ny, nx), constant_shift, dtype=np.float32)

        else:
            logger.info(
                f"Interpolating surface using {len(z)} coastal tide stations..."
            )
            rbf = Rbf(x, y, z, function="linear")
            xi = np.linspace(region.xmin, region.xmax, nx)
            yi = np.linspace(region.ymax, region.ymin, ny)
            XI, YI = np.meshgrid(xi, yi)
            rbf_grid = rbf(XI, YI).astype(np.float32)
            rbf_grid = np.clip(rbf_grid, min(z), max(z))

        return rbf_grid
