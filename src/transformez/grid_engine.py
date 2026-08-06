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
import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling
from rasterio.transform import from_bounds
from scipy import ndimage
from scipy.interpolate import Rbf

os.environ["HDF5_USE_FILE_LOCKING"] = "FALSE"

logger = logging.getLogger(__name__)


class GridCorruptionError(Exception):
    """Raised when a fetched grid is corrupted and needs re-downloading."""

    pass


def plot_grid(grid_array, region, title="Vertical Shift Preview"):
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

    plt.figure(figsize=(10, 6))
    plot_region = [region.xmin, region.xmax, region.ymin, region.ymax]

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


class GridEngine:
    @staticmethod
    def create_land_mask(region, nx, ny, vector_files):
        """Reads a list of vector files and rasterizes them into a boolean land mask.
        Returns a numpy boolean array where True = Land, False = Ocean.
        """

        try:
            from pyogrio.raw import read
            import shapely
            from rasterio.features import rasterize

        except ImportError:
            logger.warning(
                "pyogrio and shapely are required for vector coastline masking."
            )
            return None

        transform = from_bounds(
            region.xmin, region.ymin, region.xmax, region.ymax, nx, ny
        )

        geoms = []
        for vec_path in vector_files:
            try:
                # Use bbox filtering in pyogrio to speed up reading vectors
                bbox = (region.xmin, region.ymin, region.xmax, region.ymax)

                # pyogrio raw read returns a tuple: (meta, geometry_wkb, field_data)
                meta, fids, geometry_wkb, fields = read(vec_path, bbox=bbox)

                if len(geometry_wkb) > 0:
                    # Convert WKB directly to shapely geometries
                    # We also filter out any None/Null geometries
                    valid_geoms = [
                        g for g in shapely.from_wkb(geometry_wkb) if g is not None
                    ]
                    geoms.extend(valid_geoms)

            except Exception as e:
                logger.warning(f"Failed reading coastline vector {vec_path}: {e}")

        if not geoms:
            return None

        # Rasterize: Fill background with 0 (Ocean), draw shapes as 1 (Land)
        mask = rasterize(
            geoms,
            out_shape=(ny, nx),
            transform=transform,
            default_value=0,
            fill=1,
            dtype=np.uint8,
            all_touched=True,
        )

        return mask.astype(bool)

    @staticmethod
    def load_and_interpolate(source_files, target_region, nx, ny, decay_pixels=100):
        """Composites grids using GDAL Warper."""

        xmin, xmax, ymin, ymax = (
            target_region.xmin,
            target_region.xmax,
            target_region.ymin,
            target_region.ymax,
        )
        dst_transform = from_bounds(xmin, ymin, xmax, ymax, nx, ny)
        dst_crs = "EPSG:4326"

        mosaic = np.full((ny, nx), np.nan, dtype=np.float32)

        for fn in source_files:
            if not os.path.exists(fn) and not fn.startswith("netcdf:"):
                continue

            try:
                with rasterio.open(fn) as src:
                    # logger.info(f"{fn}: {src}")
                    src_data = src.read(1).astype(np.float32)
                    src_nodata = src.nodata

                    if src_nodata is not None:
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

            # except Exception as e:
            #     error_msg = str(e)

            #     if "-101" in error_msg or "HDF error" in error_msg:
            #         logger.error(f" CRITICAL: Corrupted NetCDF chunk detected in {fn}!")

            #         # Extract the real file path from the GDAL netcdf string
            #         real_path = fn.split(":")[1] if fn.startswith("netcdf:") else fn

            #         if os.path.exists(real_path):
            #             logger.warning(f"Auto-deleting corrupted cache file: {real_path}")
            #             os.remove(real_path)

            #         raise RuntimeError(
            #             f"Transformation aborted to prevent math corruption. "
            #             f"The corrupted file has been deleted. Please re-run your command to fetch a fresh copy!"
            #         )

            #     # For all other normal errors, log and continue as usual
            #     logger.exception(f"Failed to reproject {fn}: {e}")
            #     continue
            # except Exception as e:
            #     logger.exception(f"Failed to reproject {fn}: {e}")
            #     continue

        # Fill inland areas (decaying to 0) before we clear the remaining NaNs
        # mosaic = GridEngine.fill_nans(mosaic, decay_pixels=decay_pixels)
        # mosaic[np.isnan(mosaic)] = 0.0

        return mosaic

    @staticmethod
    def smart_blend(in_grid, background_grid, blend_pixels=50):
        """Smoothly blends the grid into a background grid."""

        mask = np.isnan(in_grid)

        if not mask.any():
            return in_grid

        if mask.all():
            return background_grid

        dist = ndimage.distance_transform_edt(mask)
        alpha = np.clip(dist / blend_pixels, 0.0, 1.0)

        # --- Hermite Interpolation ---
        # This converts the linear gradient into a smooth S-curve
        alpha = alpha * alpha * (3.0 - 2.0 * alpha)

        nearest_indices = ndimage.distance_transform_edt(
            mask, return_distances=False, return_indices=True
        )
        extended_vdatum = in_grid.copy()
        extended_vdatum[mask] = in_grid[tuple(nearest_indices)][mask]

        blended_data = (extended_vdatum * (1.0 - alpha)) + (background_grid * alpha)

        return blended_data

    @staticmethod
    def coastal_aware_composite(
        vdatum_grid,
        global_grid,
        region,
        nx,
        ny,
        shapefiles=None,  # Deprecated
        land_mask=None,
        decay_pixels=100,
        buffer_pixels=10,
        blend_pixels=50,
    ):
        """Handles inland decay vs. offshore blending, while
        filtering out low-resolution global artifacts.
        """

        final_grid = vdatum_grid.copy()

        # Fallback just in case shapefiles are passed directly
        if shapefiles and land_mask is None:
            land_mask = GridEngine.create_land_mask(region, nx, ny, shapefiles)
            if land_mask is not None:
                # Carve out the VDatum rivers!
                land_mask[~np.isnan(vdatum_grid)] = False

        if land_mask is not None:
            global_grid[~land_mask] = np.nan

        is_vdatum = ~np.isnan(vdatum_grid)
        is_ocean = ~np.isnan(global_grid)

        is_inland = ~is_vdatum & ~is_ocean
        is_offshore = ~is_vdatum & is_ocean

        if is_offshore.any():
            blended_ocean = GridEngine.smart_blend(
                vdatum_grid, global_grid, blend_pixels=blend_pixels
            )
            final_grid[is_offshore] = blended_ocean[is_offshore]

        if is_inland.any():
            decayed_inland = GridEngine.fill_nans(
                final_grid,
                decay_pixels=decay_pixels,
                buffer_pixels=buffer_pixels,
                land_mask=land_mask,
            )
            final_grid[is_inland] = decayed_inland[is_inland]

        return final_grid

    @staticmethod
    def fill_nans(data, decay_pixels=100, buffer_pixels=10, land_mask=None):
        """Fills NaNs by extrapolating nearest valid coastal values.
        Melted Voronoi ridges ensure C1 continuity deep inland.
        """

        out_data = data.copy()

        if land_mask is not None:
            out_data[~land_mask] = np.nan

        mask = np.isnan(out_data)
        if not mask.any() or mask.all():
            return out_data

        dist, indices = ndimage.distance_transform_edt(
            mask, return_distances=True, return_indices=True
        )

        raw_extrapolation = out_data[tuple(indices)]
        # Blur the "Voronoi Ridges" deep inland
        blurred_extrapolation = ndimage.gaussian_filter(raw_extrapolation, sigma=25)
        # Crossfade! Beach = Raw Data, Inland = Blurred Data
        blur_blend = np.clip(dist / 50.0, 0, 1)
        coast_values = (raw_extrapolation * (1.0 - blur_blend)) + (
            blurred_extrapolation * blur_blend
        )

        if decay_pixels and decay_pixels > 0:
            # --- Inland Decay ---
            effective_dist = np.clip(dist - buffer_pixels, 0, None)

            # Calculate the linear decay (1.0 down to 0.0)
            linear_decay = np.clip((decay_pixels - effective_dist) / decay_pixels, 0, 1)

            # Apply Smoothstep (Hermite) easing to create the S-curve!
            decay_factor = linear_decay * linear_decay * (3.0 - 2.0 * linear_decay)

            out_data[mask] = coast_values[mask] * decay_factor[mask]

        else:
            # --- Infinite Extrapolation (Default) ---
            out_data[mask] = coast_values[mask]

        return out_data

    @staticmethod
    def apply_vertical_shift(
        src_dem, shift_array, dst_dem, z_unit_in="m", z_unit_out="m"
    ):
        """Apply a vertical shift array to a source DEM."""

        from .definitions import Datums

        factor_in = Datums.get_unit_factor(z_unit_in)
        factor_out = Datums.get_unit_factor(z_unit_out)

        try:
            with rasterio.open(src_dem) as src:
                profile = src.profile.copy()
                data = src.read(1)

                if data.shape != shift_array.shape:
                    raise ValueError(
                        f"Dimension mismatch: DEM {data.shape} vs Shift {shift_array.shape}"
                    )

                nodata = src.nodata if src.nodata is not None else -9999
                profile.update(nodata=nodata)

                valid_mask = (data != nodata) & (~np.isnan(shift_array))

                # Scale input to meters
                data_meters = data[valid_mask] * factor_in

                # Add the meter-based datum shift
                data_shifted_meters = data_meters + shift_array[valid_mask]

                # Scale to target output units
                data[valid_mask] = data_shifted_meters / factor_out
                data[~valid_mask] = nodata

                # valid_mask = (data != nodata) & (~np.isnan(shift_array))
                # data[valid_mask] += shift_array[valid_mask]
                # data[~valid_mask] = nodata

                with rasterio.open(dst_dem, "w", **profile) as dst:
                    dst.write(data, 1)
            logger.info(f"Successfully wrote transformed DEM to: {dst_dem}")
            return True
        except Exception as e:
            logger.error(f"Failed to apply shift to DEM: {e}")
            # return False
            raise


class GridWriter:
    @staticmethod
    def write(filename, data, region):
        """Write a vertical shift grid using Rasterio."""

        dirname = os.path.dirname(filename)
        if dirname and not os.path.exists(dirname):
            os.makedirs(dirname)

        if not filename.endswith(".tif"):
            filename = os.path.splitext(filename)[0] + ".tif"

        rows, cols = data.shape
        xmin, xmax, ymin, ymax = region.xmin, region.xmax, region.ymin, region.ymax

        res_x = (xmax - xmin) / cols
        res_y = (ymax - ymin) / rows
        transform = rasterio.transform.from_origin(xmin, ymax, res_x, res_y)

        try:
            with rasterio.open(
                filename,
                "w",
                driver="GTiff",
                height=rows,
                width=cols,
                count=1,
                dtype="float32",
                crs="EPSG:4326",
                transform=transform,
                compress="deflate",
                tiled=True,
            ) as dst:
                dst.write(data.astype("float32"), 1)
            return filename
        except Exception:
            raise


def calculate_psmsl_msl(csv_path: str) -> float:
    """Reads a PSMSL time-series CSV generated by fetchez, filters out
    missing data flags (-99999), and calculates the all-time Mean Sea Level.

    Returns the MSL value in METERS.
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

                    # -99999 is the PSMSL nodata flag
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
        region, nx, ny, datum_in, datum_out, shapefiles=None, baseline_grid=None
    ):
        """Dynamically generates a tidal shift grid using live tide stations.
        If a station lacks the target datum, it falls back to MSL and uses the
        baseline_grid (FES) to bridge the gap to the geodetic frame.
        """

        import json
        from fetchez.modules.tides import Tides
        import fetchez

        tides_fetcher = Tides(src_region=region.to_list(), mode="search")
        tides_fetcher.run()

        if not tides_fetcher.results:
            logger.error("Failed to fetch tide stations GeoJSON.")
            return None

        fetchez.core.run_fetchez([tides_fetcher], threads=1)

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

        x, y, z = [], [], []
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
            shift = None
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

                            # Add the FES baseline offset to mathematically tie it to NAVD88
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

        if shapefiles:
            logger.info("Applying vector coastline mask to station surface...")
            land_mask = GridEngine.create_land_mask(region, nx, ny, shapefiles)
            if land_mask is not None:
                rbf_grid[~land_mask] = np.nan

        return rbf_grid
