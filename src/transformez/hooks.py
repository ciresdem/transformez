#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.hooks
~~~~~~~~~~~~~

Some hooks for `fetchez`

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import logging
import numpy as np

from fetchez.hooks import FetchHook
from fetchez import utils
from fetchez import spatial

from .transform import VerticalTransform
from . import grid_engine

logger = logging.getLogger(__name__)

class TransformezHook(FetchHook):
    """Dual-stage Vertical Transformation Hook.
    
    - Stage 'pre': Generates the master shift grid using module.region.
    - Stage 'file': Applies the shift grid to each downloaded file.
    
    Usage:
      fetchez copernicus --hook transformez:datum_in=5703,datum_out=6319,stage=pre
      fetchez copernicus --hook transformez:apply=True
    """
    
    name = 'transformez'
    stage = 'pre'
    desc = 'Generate a vertical transformation shift grid. Usage: --hook transformez:datum_in=3855,datum_out=5703,output_grid=shift.gtx'

    def __init__(self, datum_in='5703', datum_out='6319', increment="3s", 
                 output_grid="shift.gtx", keep_grid=True, apply=False,
                 **kwargs):
        super().__init__(**kwargs)
        self.datum_in = datum_in
        self.datum_out = datum_out
        self.increment = increment
        self.output_grid = output_grid
        self.keep_grid = utils.str2bool(keep_grid)
        self.apply = utils.str2bool(apply)


    def run(self, entries):
        if not entries: return entries

        module = entries[0][0]
        region = getattr(module, 'region', None)
        if not region:
            logger.warning("Module has no region defined. Cannot generate shift grid in PRE stage.")
            return entries

        logger.info(f"Generating vertical shift grid for region: {region}")
        self._generate_grid(region)

        for mod, entry in entries:
            entry['shift_grid_path'] = self.output_grid
            entry['vdatum_in'] = self.datum_in
            entry['vdatum_out'] = self.datum_out
            entry['transformed'] = False
        
        return entries


    def _run_file(self, entries):
        """Apply the shift grid to specific files."""
        
        if not os.path.exists(self.output_grid):
            # maybe we can generate a tiny grid just for this file? 
            logger.warning(f"Shift grid {self.output_grid} not found. Skipping transform.")
            return entries

        for mod, entry in entries:
            if entry.get('status') != 0: continue
            
            filepath = entry['dst_fn']
            
            # Enrich Metadata
            entry['shift_grid_path'] = self.output_grid
            entry['vdatum_in'] = self.datum_in
            entry['vdatum_out'] = self.datum_out
            entry['transformed'] = False
            
            if not self.apply:
                continue

            ext = os.path.splitext(filepath)[1].lower()
            transformed_path = None
            
            if ext in ['.tif', '.gtx']:
                transformed_path = self._apply_raster(filepath, self.output_grid)
            elif ext in ['.laz', '.las', 'xyz']:
                transformed_path = self._apply_pointcloud(filepath, self.output_grid)
            
            if new_path:
                entry['dst_fn'] = transformed_path
                entry['transformed'] = True
                
        return entries

    
    def _generate_grid(self, region):
        """Core logic to call VerticalTransform."""

        nx, ny = spatial.region_and_inc_to_width_height(region, self.increment)

        vt = VerticalTransform(
            extent=region,
            nx=nx, ny=ny,
            epsg_in=self.datum_in,
            epsg_out=self.datum_out,
            verbose=False
        )
        
        shift_array, _ = vt._vertical_transform(vt.epsg_in, vt.epsg_out)
        
        if shift_array is not None:
            gtx.GtxFile.write(self.output_grid, shift_array, region)
            logger.info(f"Saved shift grid to {self.output_grid}")

            
    def _apply_raster(self, src, grid):
        """Placeholder for GDAL warp/calc logic."""
        
        pass

    def _apply_pointcloud(self, src, grid):
        """Placeholder for PDAL logic."""
        
        pass
