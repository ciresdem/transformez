#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.grid_engine
~~~~~~~~~~~~~

This is the grid engine utility for combining data into a grid.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import logging
import numpy as np
import rasterio
from scipy.interpolate import RegularGridInterpolator
from scipy import ndimage

logger = logging.getLogger(__name__)

def plot_grid(grid_array, region, title="Vertical Shift Preview"):
    """Plot the transformation grid using Matplotlib.
    
    Args:
        grid_array (np.array): The shift array.
        region (tuple): Region obj
        title (str): Plot title.
    """
    
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        logger.warning("Matplotlib is not installed. Cannot generate preview.")
        return

    masked_data = np.ma.masked_where(
        (np.isnan(grid_array)) | (grid_array == -9999) | (grid_array == 0), 
        grid_array
    )

    if masked_data.count() == 0:
        logger.warning("Preview skipped: Grid contains no valid data.")
        return

    plt.figure(figsize=(10, 6))
    
    plot_region = [region[0], region[1], region[2], region[3]]

    im = plt.imshow(masked_data, extent=plot_region, cmap='RdBu_r', origin='upper')
    cbar = plt.colorbar(im)
    cbar.set_label('Vertical Shift (meters)')
    
    plt.title(title)
    plt.xlabel('Longitude')
    plt.ylabel('Latitude')
    plt.grid(True, linestyle=':', alpha=0.6)
    
    stats = (f"Min: {masked_data.min():.3f} m\n"
             f"Max: {masked_data.max():.3f} m\n"
             f"Mean: {masked_data.mean():.3f} m")
    
    plt.annotate(stats, xy=(0.02, 0.02), xycoords='axes fraction',
                 bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="gray", alpha=0.8))

    logger.info("Displaying preview... Close the plot window to continue.")
    plt.show()

    
class GridEngine:
    @staticmethod
    def load_and_interpolate(source_files, target_region, nx, ny):
        """Mosaic/Resample raster inputs onto the target grid.
        
        Args:
            source_files (list): List of file paths (.gtx, .tif, etc).
            target_region (tuple): (xmin, ymin, xmax, ymax).
            nx, ny (int): Output dimensions.
            
        Returns:
            np.array: The composited grid (ny, nx).
        """
        
        # Create Target Grid Coordinates (Pixel Centers)
        tx = np.linspace(target_region[0], target_region[1], nx)
        ty = np.linspace(target_region[2], target_region[3], ny)
        
        mosaic = np.full((ny, nx), np.nan, dtype=np.float32)
        
        # Grid for interpolation queries
        tv, tu = np.meshgrid(ty, tx, indexing='ij')
        query_pts = np.array([tv.ravel(), tu.ravel()]).T

        for src_fn in source_files:
            try:
                if not os.path.exists(src_fn): continue

                #lons, lats, data = GridEngine._read_raster(src_fn, target_region)
                lons, lats, data = GridEngine._read_raster(src_fn)#, target_region)
                if data is None: continue
                # Fill internal NaNs to prevent holes during interpolation
                if np.isnan(data).any():
                    data = GridEngine.fill_nans(data, decay_pixels=100)

                # --- OVERLAP CHECK ---
                # Skip if file is totally outside region
                if (lons.min() > target_region[1] or lons.max() < target_region[0] or
                    lats.min() > target_region[3] or lats.max() < target_region[2]):
                    logger.debug(f"Skipping {os.path.basename(src_fn)}: Outside target bounds.")
                    continue

                # --- STANDARDIZE FOR SCIPY ---
                # RegularGridInterpolator requires strictly increasing axes.
                if lons[0] > lons[-1]:
                    lons = np.flip(lons)
                    data = np.flip(data, axis=1)
                
                if lats[0] > lats[-1]:
                    lats = np.flip(lats)
                    data = np.flip(data, axis=0)

                # --- INTERPOLATE ---
                # (y_coords, x_coords), data_array
                interp = RegularGridInterpolator(
                    (lats, lons), 
                    data, 
                    bounds_error=False, 
                    fill_value=None,
                    method='linear',
                )
                
                # Interpolate onto target grid
                patch = interp(query_pts).reshape(ny, nx)
                # --- MOSAIC (Fill NaNs) ---
                # Overwrite existing NaNs with valid data from this patch
                mask = np.isnan(mosaic) & ~np.isnan(patch)
                mosaic[mask] = patch[mask]
                
            except Exception as e:
                logger.error(f"Error processing {src_fn}: {e}")
                
        return mosaic

    
    @staticmethod
    def fill_nans(data, decay_pixels=100):
        """Fill NaNs with the nearest valid value, decayed to zero over distance."""
        
        mask = np.isnan(data)
        if not mask.any(): return data
        if mask.all(): return data 

        # Distance transform to nearest valid pixel
        dist, indices = ndimage.distance_transform_edt(
            mask, 
            return_distances=True, 
            return_indices=True
        )
        
        # Get value at nearest valid pixel
        coast_values = data[tuple(indices)]
        
        # Decay factor (1.0 at edge -> 0.0 at decay_pixels distance)
        decay_factor = np.clip((decay_pixels - dist) / decay_pixels, 0, 1)
        
        filled_values = coast_values * decay_factor
        
        out_data = data.copy()        
        out_data[mask] = filled_values[mask]
        
        return out_data

    
    @staticmethod
    def _read_raster(filename):
        """Unified Raster Reader using Rasterio.

        For .tif and .gtx files.
        """
        
        try:
            with rasterio.open(filename) as src:
                data = src.read(1)

                height, width = data.shape
                bounds = src.bounds # left, bottom, right, top
                
                if src.nodata is not None:
                    data[data == src.nodata] = np.nan
                
                if filename.endswith('.gtx'):
                    data[data == -88.8888] = np.nan
                    #data = data.reshape((height, width))

                res_x = (bounds.right - bounds.left) / width
                res_y = (bounds.top - bounds.bottom) / height
                
                lons = np.linspace(bounds.left + res_x/2, bounds.right - res_x/2, width)
                lats = np.linspace(bounds.top - res_y/2, bounds.bottom + res_y/2, height)
                
                # Longitude Normalization (0-360 -> -180-180)
                # If grid uses 0-360 but data is -180-180, we wrap it.
                if np.any(lons > 180):
                    lons = ((lons + 180) % 360) - 180
                    
                return lons, lats, data

        except Exception as e:
            logger.warning(f"Failed to read {filename}: {e}")
            return None, None, None    

        
    @staticmethod
    def apply_vertical_shift(src_dem, shift_array, dst_dem):
        """Apply a vertical shift array to a source DEM and write to destination.
        
        Args:
            src_dem (str): Path to input DEM.
            shift_array (np.array): Shift grid (must match src_dem dimensions).
            dst_dem (str): Path to output DEM.
        """
        
        try:
            with rasterio.open(src_dem) as src:
                profile = src.profile.copy()
                data = src.read(1)
                
                # Check dimensions
                if data.shape != shift_array.shape:
                    raise ValueError(f"Dimension mismatch: DEM {data.shape} vs Shift {shift_array.shape}")
                
                # Handle NoData
                nodata = src.nodata
                if nodata is None:
                    nodata = -9999
                    profile.update(nodata=nodata)
                
                # Create validity mask
                # If existing data is valid AND shift is valid
                valid_mask = (data != nodata) & (~np.isnan(shift_array))
                
                # Apply Shift: Output = Input + Shift
                # Transformez convention: Shift is "Input -> Output"
                data[valid_mask] += shift_array[valid_mask]
                
                # Ensure invalid shift areas don't corrupt valid data?
                # Or should they become nodata? 
                # Decision: If shift is missing (NaN), result is undefined -> NoData
                data[~valid_mask] = nodata
                
                # Write Output
                with rasterio.open(dst_dem, 'w', **profile) as dst:
                    dst.write(data, 1)
                    
            logger.info(f"Successfully wrote transformed DEM to: {dst_dem}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to apply shift to DEM: {e}")
            return False

        
class GridWriter:
    @staticmethod
    def write(filename, data, region):
        """Write a vertical shift grid using Rasterio.

        PROJ prefers GeoTIFF (.tif) over legacy GTX.
        """
        
        if not filename.endswith('.tif'):
            filename = os.path.splitext(filename)[0] + '.tif'

        rows, cols = data.shape
        xmin, xmax, ymin, ymax = region
        
        res_x = (xmax - xmin) / cols
        res_y = (ymax - ymin) / rows
        
        transform = rasterio.transform.from_origin(xmin, ymax, res_x, res_y)

        with rasterio.open(
            filename,
            'w',
            driver='GTiff',
            height=rows,
            width=cols,
            count=1,
            dtype='float32',
            crs='EPSG:4326',  # VDatum grids are WGS84
            transform=transform,
            compress='deflate',
            tiled=True
        ) as dst:
            dst.write(data.astype('float32'), 1)
            
        return filename
