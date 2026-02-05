#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.grid_engine
~~~~~~~~~~~~~

This is the grid engine utility

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import logging
import numpy as np
import tifffile
from scipy.interpolate import RegularGridInterpolator
from scipy import ndimage
from .gtx import GtxFile

logger = logging.getLogger(__name__)

def plot_grid(grid_array, extent, title="Vertical Shift Preview"):
    """Plot the transformation grid using Matplotlib.
    
    Args:
        grid_array (np.array): The shift array.
        extent (tuple): GDAL-style extent (xmin, ymin, xmax, ymax).
        title (str): Plot title.
    """
    
    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        logger.warning("Matplotlib is not installed. Cannot generate preview.")
        logger.warning("Install it via: pip install matplotlib")
        return

    masked_data = np.ma.masked_where(
        (grid_array == -9999) | (grid_array == 0), 
        grid_array
    )

    if masked_data.count() == 0:
        logger.warning("Preview skipped: Grid contains no valid data.")
        return

    plt.figure(figsize=(10, 6))
    
    plot_extent = [extent[0], extent[2], extent[1], extent[3]]

    im = plt.imshow(masked_data, extent=plot_extent, cmap='RdBu_r', origin='upper')
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
    def load_and_interpolate(source_files, target_extent, nx, ny):
        """Mosaic/Resample for mixed GTX and TIF inputs.
        
        Args:
            source_files (list): List of file paths (.gtx or .tif).
            target_extent (tuple): (xmin, ymin, xmax, ymax).
            nx, ny (int): Output dimensions.
            
        Returns:
            np.array: The composited grid (ny, nx).
        """
        
        # Create Target Grid Coordinates (Pixel Centers)
        tx = np.linspace(target_extent[0], target_extent[2], nx)
        ty = np.linspace(target_extent[1], target_extent[3], ny)
        
        mosaic = np.full((ny, nx), np.nan, dtype=np.float32)
        
        tv, tu = np.meshgrid(ty, tx, indexing='ij')
        query_pts = np.array([tv.ravel(), tu.ravel()]).T

        logger.info(source_files)
        for src_fn in source_files:
            try:
                lons, lats, data = None, None, None
                
                if src_fn.endswith('.gtx'):
                    lons, lats, data = GridEngine._read_gtx(src_fn)
                elif src_fn.endswith(('.tif', '.tiff')):
                    lons, lats, data = GridEngine._read_geotiff(src_fn)
                else:
                    logger.warning(f"Skipping unknown format: {src_fn}")
                    continue

                if data is None: 
                    continue

                if np.isnan(data).any():
                    # 'decay_pixels' defines the buffer zone width (in source grid pixels)
                    data = GridEngine.fill_nans(data, decay_pixels=100)
                
                # --- OVERLAP CHECK ---
                # Skip if file is totally outside region
                if (lons.min() > target_extent[2] or lons.max() < target_extent[0] or
                    lats.min() > target_extent[3] or lats.max() < target_extent[1]):
                    logger.warning(f'data is outisde target bounds: ({target_extent})')
                    continue

                # --- STANDARDIZE FOR SCIPY ---
                # RegularGridInterpolator requires strictly increasing axes.
                # If lats or lons are descending, flip them and the data.
                if lons[0] > lons[-1]:
                    lons = np.flip(lons)
                    data = np.flip(data, axis=1)
                
                if lats[0] > lats[-1]:
                    lats = np.flip(lats)
                    data = np.flip(data, axis=0)

                # --- INTERPOLATE ---
                interp = RegularGridInterpolator(
                    (lats, lons), 
                    data, 
                    bounds_error=False, 
                    fill_value=None,
                    method='linear',
                )
                
                # Interpolate and Reshape
                patch = interp(query_pts).reshape(ny, nx)
                
                # --- MOSAIC (Fill NaNs) ---
                mask = np.isnan(mosaic) & ~np.isnan(patch)
                mosaic[mask] = patch[mask]
                
            except Exception as e:
                logger.error(f"Error processing {src_fn}: {e}")
                
        return mosaic

    
    @staticmethod
    def fill_nans(data, decay_pixels=100):
        """Fill NaNs with the nearest valid value, decayed to zero over distance.
        
        Args:
            data (np.array): Input grid with NaNs.
            decay_pixels (int): Distance (in pixels) over which the value fades to 0.
        """
        
        mask = np.isnan(data)
        
        if not mask.any(): return data
        if mask.all(): return data # Nothing to extrapolate from

        # Get Distance and Indices of nearest valid pixels
        # dist = Euclidean distance to nearest valid pixel
        # indices = (row, col) indices of that nearest valid pixel
        dist, indices = ndimage.distance_transform_edt(
            mask, 
            return_distances=True, 
            return_indices=True
        )
        
        # Retrieve the "Starting Value" (Value at the coast)
        # We look up the value at the nearest valid pixel indices
        coast_values = data[tuple(indices)]
        
        # Decay Factor
        # Factor starts at 1.0 (at the coast) and drops linearly to 0.0 at decay_pixels
        # We clip it to [0, 1] so values beyond decay_pixels stay 0.
        decay_factor = np.clip((decay_pixels - dist) / decay_pixels, 0, 1)
        
        # The new value is the coastal value weighted by distance
        filled_values = coast_values * decay_factor
        
        out_data = data.copy()        
        out_data[mask] = filled_values[mask]
        
        return out_data
    
    
    @staticmethod
    def _read_gtx(filename):
        """Wrapper for GtxFile to return standard vectors."""
        
        gtx = GtxFile(filename)
        gtx.data[gtx.data == -88.8888] = np.nan
        return gtx.lons, gtx.lats, gtx.data

    
    @staticmethod
    def _read_geotiff(filename):
        """Parse GeoTIFF tags using tifffile to extract coordinate vectors."""
        
        with tifffile.TiffFile(filename) as tif:
            page = tif.pages[0]
            try:
                data = page.asarray()
            except ValueError as e:
                # Check for specific compression error
                if 'requires the \'imagecodecs\' package' in str(e):
                    raise ImportError(
                        f"Failed to read {os.path.basename(filename)}. "
                        "This grid uses advanced compression (Predictor 3). "
                        "Please install the decoder: 'pip install imagecodecs'"
                    ) from e
                raise e
            
            # If 3D (bands, y, x), take first band
            if data.ndim == 3:
                data = data[0, :, :]
            
            # Get Nodata (Tag 42113)
            # If tag exists, mask it to NaN
            nodata_tag = page.tags.get(42113)
            if nodata_tag:
                nodata_val = float(nodata_tag.value.split('\0')[0]) # Sometimes stored as string
                data[data == nodata_val] = np.nan
            
            # Parse ModelPixelScale (Tag 33550) -> [ScaleX, ScaleY, ScaleZ]
            # Parse ModelTiepoint (Tag 33922) -> [I, J, K, X, Y, Z]
            # Default to standard top-left anchor
            try:
                scale = page.tags[33550].value
                tiepoint = page.tags[33922].value
            except KeyError:
                raise ValueError("TIFF is missing GeoTIFF ModelTags")

            dx, dy = scale[0], scale[1]
            ref_x, ref_y = tiepoint[3], tiepoint[4]
            
            height, width = data.shape
            
            # Calculate Coordinate Vectors
            # X: Starts at ref_x, increments by dx
            # Note: Tiff tiepoint is usually center of top-left pixel or corner. 
            # We assume "PixelIsArea" (Corner) -> Center = Corner + 0.5 * res
            # But standard construct is usually linspace from min to max.            
            min_x = ref_x
            max_x = ref_x + (width * dx)
            
            # Y: Usually starts at ref_y (top) and decreases (-dy)
            # Tiepoint Y is usually MaxY.
            max_y = ref_y
            min_y = ref_y - (height * dy)
            
            # Generate vectors and return
            lons = np.linspace(min_x + (dx/2), max_x - (dx/2), width)
            lats = np.linspace(max_y - (dy/2), min_y + (dy/2), height)
            if np.any(lons > 180):
                lons = ((lons + 180) % 360) - 180            
            return lons, lats, data    
