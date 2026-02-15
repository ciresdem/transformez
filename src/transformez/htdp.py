#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.htdp
~~~~~~~~~~~~~

This wraps the NGS 'htdp' tool.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import sys
import subprocess
from typing import Optional, Tuple, List
import numpy as np

import logging

from . import utils

logger = logging.getLogger(__name__)

__version__ = '0.2.0'

ae = '.exe' if sys.platform == 'win32' else ''
htdp_cmd = 'echo 0 | htdp 2>&1' if sys.platform == 'win32' else "echo 0 | htdp 2>&1 | grep SOFTWARE | awk '{print $3}'"
HAS_HTDP = utils.cmd_check(f'htdp{ae}', htdp_cmd)#.decode()

# =============================================================================
# wrapper and functions for using the htdp program
# https://geodesy.noaa.gov/TOOLS/Htdp/Htdp.shtml
#
# version 3.3.0
#  1...NAD_83(2011/CORS96/2007)  (North American plate fixed) 
#  2...NAD_83(PA11/PACP00)       (Pacific plate fixed) 
#  3...NAD_83(MA11/MARP00)       (Mariana plate fixed)
#  5...WGS_84(original) (NAD_83(2011) used) 15...ITRF91 
#  6...WGS_84(G730) (ITRF91 used)           16...ITRF92 
#  7...WGS_84(G873) (ITRF94 used)           17...ITRF93 
#  8...WGS_84(G1150) (ITRF2000 used)        18...ITRF94 
#  9...WGS_84(G1674) (ITRF2008 used)        19...ITRF96 
# 10...WGS_84(G1762) (IGb08 used)           20...ITRF97 or IGS97
# 11...SIO/MIT_92 (ITRF91 used)    21...ITRF2000 or IGS00/IGb00
# 12...ITRF88                      22...ITRF2005 or IGS05 
# 13...ITRF89                      23...ITRF2008 or IGS08/IGb08
# 14...ITRF90 or (PNEOS90/NEOS90)  24...ITRF2014 or IGS14/IGb14
#
# version 3.4.0
#  1...NAD_83(2011/CORS96/2007)  North America plate fixed     
#  2...NAD_83(PA11/PACP00)       Pacific plate fixed           
#  3...NAD_83(MA11/MARP00)       Mariana plate fixed                                                             
#  4...WGS84 original (Transit)                                
#  5...WGS84(G730)   ITRF91 used                               
#  6...WGS84(G873)   ITRF94=ITRF96=ITRF97 used                 
#  7...WGS84(G1150)  ITRF2000=IGS00=IGb00 used                 
#  8...WGS84(G1674)  ITRF2008=IGS08=IGb08 used                 
#  9...WGS84(G1762)  ITRF2008=IGS08=IGb08 used                 
# 10...WGS84(G2139)  ITRF2014=IGS14=IGb14 used                                                                             
# 11...ITRF88                      18...ITRF96 (=ITRF94=ITRF97)
# 12...ITRF89                      19...ITRF97 (=ITRF94=ITRF96)
# 13...ITRF90 (or PNEOS90/NEOS90)  20...ITRF2000 or IGS00/IGb00
# 14...ITRF91 (or SIO/MIT_92)      21...ITRF2005 or IGS05      
# 15...ITRF92                      22...ITRF2008 or IGS08/IGb08
# 16...ITRF93                      23...ITRF2014 or IGS14/IGb14
# 17...ITRF94 (=ITRF96=ITRF97)
# =============================================================================
class HTDP:
    """Wrapper for the NGS HTDP (Horizontal Time-Dependent Positioning) software."""

    def __init__(self, htdp_bin: str = 'htdp', verbose: bool = True):
        self.htdp_bin = htdp_bin
        self.verbose = verbose

        # Check if HTDP is configured/installed
        if not HAS_HTDP:
            logger.error(
                'You must have HTDP installed to perform vertical transformations.'
            )


    def _next_point(self, fd) -> Optional[Tuple[int, int, float, float, float]]:
        """Parse the next point from the HTDP output file object."""
        
        while True:
            line = fd.readline()
            if not line:
                return None
            
            line = line.strip()
            # Look for lines containing the point ID tag "PNT_"
            if 'PNT_' in line:
                try:
                    # Robust parsing: Replace double quotes to handle "PNT_..." sticking to numbers
                    clean_line = line.replace('"', ' "') 
                    parts = clean_line.split()
                    
                    # We expect: Lat, Lon, Height, "PNT_x_y"
                    # Sometimes HTDP puts a * warning at the start
                    if parts[0] == '*': 
                        parts = parts[1:]

                    lat_dst = float(parts[0])
                    lon_dst = float(parts[1])
                    eht_dst = float(parts[2])
                    
                    # Find the part that contains PNT_
                    name_tag = next(p for p in parts if 'PNT_' in p).strip('"')
                    
                    # Parse indices from name "PNT_X_Y"
                    name_tokens = name_tag.split('_')
                    x_idx = int(name_tokens[1])
                    y_idx = int(name_tokens[2])

                    return x_idx, y_idx, lat_dst, lon_dst, eht_dst
                except (ValueError, IndexError) as e:
                    # Log failing lines to help debug "Points found" mismatches
                    logging.debug(f"Failed to parse HTDP line: {line} -> {e}")
                    continue
                

    def _read_grid(self, filename: str, shape: Tuple[int, int]) -> np.ndarray:
        """Read the output grid created by HTDP.
        
        Args:
            filename: Path to the HTDP output file.
            shape: Tuple of (rows, cols) representing grid dimensions.
        """
        
        grid = np.zeros(shape)
        expected_points = shape[0] * shape[1]
        points_found = 0

        with open(filename, 'r') as fd:
            if self.verbose:
                # Echo header info (approx first 5 lines)
                for _ in range(5):
                    header_line = fd.readline().strip()
                    if header_line:
                        logger.info(header_line)

            ptuple = self._next_point(fd)
            while ptuple is not None:
                # ptuple: (x_idx, y_idx, lat, lon, height)
                # grid indices: [row/y, col/x]
                try:
                    grid[ptuple[1], ptuple[0]] = ptuple[4]
                    points_found += 1
                except IndexError:
                    logger.error(f'Grid index out of bounds: {ptuple}')
                
                ptuple = self._next_point(fd)

        if points_found < expected_points:
            logger.error(
                f'Points found: {points_found}, Points expected: {expected_points}'
            )
            sys.exit(1)

        return grid


    def _new_create_grid(self, griddef: List[float]) -> np.ndarray:
        """Create a regular meshgrid of lat/long values.
        
        Args:
            griddef: [lon_min, lat_min, lon_max, lat_max, lon_steps, lat_steps]
                     Expected input is standard signed decimal degrees (West is Negative).
        """
        
        # FIX: Removed the "-1 *" inversion. Use coordinates exactly as provided.
        lon_start = griddef[0]  # West
        lat_start = griddef[1]  # South
        lon_end = griddef[2]    # East
        lat_end = griddef[3]    # North

        lon_steps = int(griddef[4])
        lat_steps = int(griddef[5])

        # Generate axes
        # Ensure we always scan Min -> Max (West->East, South->North)
        # This prevents "inverted" grids if the input bounds were swapped
        l_min, l_max = sorted([lon_start, lon_end])
        t_min, t_max = sorted([lat_start, lat_end])

        lon_axis = np.linspace(l_min, l_max, lon_steps)
        lat_axis = np.linspace(t_min, t_max, lat_steps)

        # indexing='xy' ensures:
        # xv (lon) has shape (lat_steps, lon_steps)
        # yv (lat) has shape (lat_steps, lon_steps)
        xv, yv = np.meshgrid(lon_axis, lat_axis, indexing='xy')

        # Return stacked array: [lon_grid, lat_grid]
        return np.array([xv, yv])
    

    def _write_grid(self, grid: np.ndarray, out_filename: str):
        """Write a grid to a file suitable for HTDP input.
        
        Args:
            grid: Numpy array of shape (2, rows, cols) where grid[0] is lon, grid[1] is lat.
            out_filename: Output file path.
        """
        
        # grid shape: (2, rows, cols)
        rows = grid.shape[1]
        cols = grid.shape[2]

        with open(out_filename, 'w') as fd_out:
            for i in range(cols):
                for j in range(rows):
                    # FIX: Use f-string formatting {:.9f} to prevent scientific notation (1e-5)
                    # and ensure strict space separation.
                    lat = grid[1, j, i]
                    lon = grid[0, j, i]
                    
                    # Note: HTDP allows free format but prefers spaces.
                    fd_out.write(
                        f'{lat:.9f} {lon:.9f} 0.000 "PNT_{i}_{j}"\n'
                    )
                    
                    
    def _write_control(self, control_fn: str, out_grid_fn: str,
                       in_grid_fn: str, src_crs_id: int, src_crs_date: str,
                       dst_crs_id: int, dst_crs_date: str):
        """Write the HTDP control file."""
        
        # 4 = Mode: Transform positions
        # 2 = Date format: decimal years
        # 2 = Date format: decimal years
        # 3 = Height code: Ellipsoidal
        # 0 = Velocity output: No
        # 0 = Output format: Standard        
        control_content = (
            f'4\n'
            f'{out_grid_fn}\n'
            f'{src_crs_id}\n'
            f'{dst_crs_id}\n'
            f'2\n'
            f'{src_crs_date}\n'
            f'2\n'
            f'{dst_crs_date}\n'
            f'3\n'
            f'{in_grid_fn}\n'
            f'0\n'
            f'0\n'
        )
        
        with open(control_fn, 'w') as f:
            f.write(control_content)

            
    def run(self, htdp_control: str):
        """Execute HTDP using the generated control file."""
        
        if not HAS_HTDP:
            return

        # Use subprocess to pipe the control file content to HTDP stdin
        try:
            with open(htdp_control, 'r') as stdin_f:
                if self.verbose:
                    logger.info(f'Running HTDP with control file: {htdp_control}')
                
                subprocess.run(
                    [self.htdp_bin],
                    stdin=stdin_f,
                    check=True,
                    stdout=None if self.verbose else subprocess.DEVNULL,
                    stderr=subprocess.PIPE
                )
        except subprocess.CalledProcessError as e:
            logger.error(f'HTDP execution failed: {e}')
            if e.stderr:
                logger.error(e.stderr.decode())
        except FileNotFoundError:
            logger.error(f'Control file not found: {htdp_control}')
        except Exception as e:
            logger.error(f'An unexpected error occurred running HTDP: {e}')
