#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.gtx
~~~~~~~~~~~~~

This holds the GtxFile reader/writer.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import struct
import numpy as np

class GtxFile:
    """Reader/Writer for NOAA .gtx binary grids (Big Endian).
    Replaces GDAL for reading VDatum/VERTCON grids.
    """

    def __init__(self, filename):
        self.filename = filename
        self.data = None
        self.extent = None # (xmin, ymin, xmax, ymax)
        self.lons = None
        self.lats = None
        
        self._read()

    def _read(self):
        file_size = os.path.getsize(self.filename)
        
        with open(self.filename, 'rb') as f:
            # Parse Header (40 bytes, Big Endian)
            # 4 doubles (8 bytes each) + 2 integers (4 bytes each)
            # d = double, i = integer, > = Big Endian
            header_fmt = '>4d2i' 
            header_bytes = f.read(40)
            
            (lat_min, lon_min, delta_lat, delta_lon, 
             n_rows, n_cols) = struct.unpack(header_fmt, header_bytes)

            expected_count = n_rows * n_cols
            
            # Parse Data (Float32, Big Endian)
            # The rest of the file is the grid data
            dtype = np.dtype('>f4') # Big Endian Float32
            self.data = np.fromfile(f, dtype=dtype)

            if self.data.size > expected_count:
                self.data = self.data[:expected_count]

            elif self.data.size < expected_count:
                # File ended too early.
                raise IOError(f"GTX file incomplete. Expected {expected_count} points, got {self.data.size}")
            
            # GTX stores data row by row
            try:
                self.data = self.data.reshape((n_rows, n_cols))
            except ValueError:
                expected = n_rows * n_cols
                if self.data.size != expected:
                    raise IOError(f"GTX file size mismatch. Expected {expected}, got {self.data.size}")

            # GTX lon_min is usually 0-360 positive East.
            # We construct the coordinate arrays.
            self.lats = np.linspace(lat_min, lat_min + (n_rows * delta_lat), n_rows)
            self.lons = np.linspace(lon_min, lon_min + (n_cols * delta_lon), n_cols)
            
            if np.any(self.lons > 180):
                self.lons = ((self.lons + 180) % 360) - 180
                
            self.extent = (self.lons.min(), self.lats.min(), 
                           self.lons.max(), self.lats.max())

            
    @staticmethod
    def write(filename, data, extent):
        """Write a numpy array to a NOAA .gtx binary file.
        
        Args:
            filename (str): Output filename (.gtx).
            data (np.array): 2D numpy array (rows, cols) of vertical shifts.
            extent (tuple): (xmin, ymin, xmax, ymax) representing the grid NODES.
                            Note: VDatum grids are node-based (PixelIsPoint).
        """
        
        if data.ndim != 2:
            raise ValueError("Data must be a 2D array (rows, cols)")

        rows, cols = data.shape
        xmin, ymin, xmax, ymax = extent

        # Calculate Deltas (Node-based)
        # delta = distance between points = width / (count - 1)
        delta_lat = (ymax - ymin) / (rows - 1) if rows > 1 else 0
        delta_lon = (xmax - xmin) / (cols - 1) if cols > 1 else 0
        
        # Coordinates:
        # Standard VDatum GTX files use 0-360 longitude (Positive East).
        # Transformez uses -180 to 180.
        header_lon_min = xmin
        if xmin < 0:
            header_lon_min = (xmin + 360) % 360
            
        with open(filename, 'wb') as f:
            # Write Header (40 bytes, Big Endian)
            # Format: > 4 doubles, 2 ints
            # lat_min, lon_min, delta_lat, delta_lon, nrows, ncols
            header_struct = struct.pack('>4d2i', 
                ymin, 
                header_lon_min, 
                delta_lat, 
                delta_lon, 
                rows, 
                cols
            )
            f.write(header_struct)
            
            # Write Data (Float32, Big Endian)
            # Ensure Float32 and convert to Big Endian bytes
            data.astype('>f4').tofile(f)
            
        return filename
