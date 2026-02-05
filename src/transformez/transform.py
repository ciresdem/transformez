#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.transform
~~~~~~~~~~~~~

This is the main tranformation class

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import logging
import numpy as np
import fetchez

from .definitions import Datums
from .grid_engine import GridEngine

logger = logging.getLogger(__name__)

def _geo2pixel(geo_x, geo_y, geo_transform, node='grid'):
    """Convert a geographic x,y value to a pixel location."""
    
    if geo_transform[2] + geo_transform[4] == 0:
        pixel_x = (geo_x - geo_transform[0]) / geo_transform[1]
        pixel_y = (geo_y - geo_transform[3]) / geo_transform[5]
        if node == 'grid':
            pixel_x += .5
            pixel_y += .5
    else:
        pixel_x, pixel_y = _apply_gt(geo_x, geo_y, _invert_gt(geo_transform))
        
    return int(pixel_x), int(pixel_y)


def region_geo_transform(region, nx: int, ny: int):
    """Generate a GDAL-style GeoTransform from extent and dimensions.
    
    Args:
        region (tuple): (min_x, min_y, max_x, max_y) - 'te' format.
        nx (int): Number of columns (x count).
        ny (int): Number of rows (y count).
        
    Returns:
        tuple: (top_left_x, x_res, 0, top_left_y, 0, -y_res)
    """
    
    min_x, min_y, max_x, max_y = region
    x_res = (max_x - min_x) / float(nx)
    y_res = (max_y - min_y) / float(ny)
    return (min_x, x_res, 0, max_y, 0, -y_res)


class VerticalTransform:
    """Generate a vertical transformation grid using Transformez definitions and fetchez."""
    
    def __init__(self, extent, nx, ny, epsg_in, epsg_out,
                 geoid_in=None, geoid_out=None, epoch_in=1997.0, epoch_out=1997.0,
                 wm=500, cache_dir=None, verbose=True):
        """
        Args:
            extent (tuple): (xmin, ymin, xmax, ymax) - Standard GDAL 'te' order.
            nx (int): Number of x pixels.
            ny (int): Number of y pixels.
            geo_transform (tuple): GDAL GeoTransform tuple.
        """
        
        self.extent = extent  # (xmin, ymin, xmax, ymax)
        self.nx = nx
        self.ny = ny
        self.gt = region_geo_transform(self.extent, self.nx, self.ny)
        
        self.x_inc = self.gt[1]
        self.y_inc = self.gt[5]
        
        self.epsg_in = Datums.get_vdatum_by_name(str(epsg_in))
        self.epsg_out = Datums.get_vdatum_by_name(str(epsg_out))
        
        self.geoid_in = geoid_in
        self.geoid_out = geoid_out
        if self.geoid_out is None:
            self.geoid_out = Datums.get_default_geoid(self.epsg_out)

        self.epoch_in = float(epoch_in) if epoch_in is not None else 1997.0
        self.epoch_out = float(epoch_out) if epoch_out is not None else 1997.0
            
        self.cache_dir = cache_dir or os.path.join(os.path.expanduser('~'), '.transformez')
        self.wm = wm
        self.verbose = verbose
        
        # Identify frames
        self.ref_in = Datums.get_frame_type(self.epsg_in)
        self.ref_out = Datums.get_frame_type(self.epsg_out)
           

    def fetch_proj_cdn(self, query=None, epsg=None, outdir='./'):
        """Fetch datum from Proj CDN. 

        Accepts either a text 'query' OR a specific 'epsg' integer code.
        """
        
        ProjModule = fetchez.registry.FetchezRegistry.load_module('proj')
        if not ProjModule:
            logger.error("Error: 'proj' module not found in fetchez registry.")
            sys.exit(1)

        search_term = f"EPSG:{epsg}" if epsg else query
        logger.info(f"Fetching CDN datum: {search_term}")            

        fetcher = ProjModule(
            src_region=self.extent,#_get_fetchez_extent(),
            query=query, 
            epsg=epsg,
            outdir=outdir
        )
        
        fetcher.run()
        
        if not fetcher.results:
            logger.warning(f"Fetchez found no data for {search_term}")
            return None

        fetchez.core.run_fetchez([fetcher], threads=1)
        return fetcher.results


    def fetch_vdatum(self, datatype='mllw', outdir='./', unzip=True):
        """Fetch input tidal datum grids from VDatum.

        Returns a list of local file paths (TIFs).
        """
        
        logger.info(f'Fetching tidal datum: {datatype}')
        VDatumModule = fetchez.registry.FetchezRegistry.load_module('vdatum')
        if not VDatumModule:
            logger.error('"vdatum" module not found in fetchez registry.')
            sys.exit(1)

        fetcher = VDatumModule(
            src_region=self.extent,
            datatype=datatype,
            outdir=outdir
        )
    
        fetcher.run()
        
        if not fetcher.results:
            logger.warning(f'Fetchez found no VDatum data for {datatype}.')
            return []

        fetchez.core.run_fetchez([fetcher], threads=2)

        valid_grids = []
        for result in fetcher.results:
            dst_fn = result['dst_fn']
            
            if not os.path.exists(dst_fn):
                continue

            if unzip and dst_fn.endswith('.zip'):
                vdatum_gtx = dst_fn.replace('.zip', '.gtx')
                
                if not os.path.exists(vdatum_gtx):
                    extracted_files = fetchez.utils.p_f_unzip(
                        dst_fn, 
                        fns=[result['data_type']], 
                        outdir=fetcher._outdir
                    )

                    vdatum_gtx = extracted_files[0]
                
                if os.path.exists(vdatum_gtx):
                    valid_grids.append(vdatum_gtx)
            
            elif dst_fn.endswith('.tif') or dst_fn.endswith('.gtx'):
                valid_grids.append(dst_fn)

        return valid_grids

    
    def _tidal_transform(self, vdatum_tidal_in, vdatum_tidal_out):
        """Generate tidal transformation grid using NOAA VDatum via GDAL VRT/Warp.

        Replaces manual interpolation with robust GDAL mosaicking.
        """

        def _get_datum_grid(datatype):
            if datatype in [5714, 'msl']: 
                return np.zeros((self.ny, self.nx))

            grid_files = self.fetch_vdatum(datatype=datatype, outdir=self.cache_dir)
            
            if not grid_files:
                logger.warning(f'Could not locate {datatype} in the region {self.extent}')
                return None

            vrt_path = fetchez.utils.make_temp_fn(f'_{datatype}.vrt', temp_dir=self.cache_dir)

            grid_in = GridEngine.load_and_interpolate(grid_files, self.extent, self.nx, self.ny)
            return grid_in

        grid_in = _get_datum_grid(vdatum_tidal_in)
        grid_out = None
        if vdatum_tidal_out is not None:
            grid_out = _get_datum_grid(vdatum_tidal_out)
        
        if grid_in is None and grid_out is None:
            return np.zeros((self.ny, self.nx)), None

        if grid_in is None:
            return grid_out * -1, Datums.get_vdatum_by_name(vdatum_tidal_out)

        if grid_out is None:
            return grid_in, Datums.get_vdatum_by_name('msl')

        return grid_in - grid_out, Datums.get_vdatum_by_name(vdatum_tidal_out)
    

    def _cdn_transform(self, epsg=None, name=None, geoid='g2018', invert=False):
        """Create a CDN transformation grid."""
        
        default_geoid_id = Datums.CDN.get(epsg, {}).get('default_geoid')
        if name == default_geoid_id:
            logger.debug(f"User requested default geoid '{name}' explicitly. Reverting to EPSG lookup.")
            name = None

        target_geoid = name if name else geoid
        if target_geoid == 'geoid':
            target_geoid = geoid
            
        geoid_def = Datums.GEOIDS.get(target_geoid, {})
        if not geoid_def:
            logger.warning(f"Geoid definition '{target_geoid}' not found. Using zero-shift.")
            return np.zeros((self.ny, self.nx)), epsg

        provider = geoid_def.get('provider', 'proj') 
        grid_path = None
        source_code = None

        if provider == 'vdatum':
            grid_path = self.fetch_vdatum(datatype=target_geoid, outdir=self.cache_dir)
            source_code = 6319 
        else:
            query = geoid if name == 'geoid' else name
            results = self.fetch_proj_cdn(query=query, epsg=epsg, outdir=self.cache_dir)
            if results:
                if name:
                    target = next((r for r in results if name.lower() in r.get('title', '').lower() or 
                                                         name.lower() in os.path.basename(r.get('dst_fn', '')).lower()), 
                                  results[0])
                else:
                    target = results[0]

                if target:
                    grid_path = target.get('dst_fn')
                    source_code = getattr(target, 'source_crs', None)
                    if grid_path and os.path.exists(grid_path):
                        data = GridEngine.load_and_interpolate([grid_path], self.extent, self.nx, self.ny)
                        return (data * -1 if invert else data), source_code

            else:
                logger.error(f"Failed to locate transformation grid for '{target_geoid}' via proj.")
                if name:
                    logger.error(f"Try removing the ':{name}' override to rely on standard EPSG lookup.")
                return np.zeros((self.ny, self.nx)), epsg                    

    
    def _htdp_transform(self, epsg_in, epsg_out):
        """Create an HTDP transformation grid."""

        if epsg_in == epsg_out and self.epoch_in == self.epoch_out:
            logger.info(f"HTDP Identity {epsg_in}@{self.epoch_in} -> {epsg_out}@{self.epoch_out}: Zero shift.")
            return np.zeros((self.ny, self.nx)), epsg_out
        
        from . import htdp
        
        try:
            htdp_tool = htdp.HTDP(verbose=False)
        except Exception as e:
            logger.error(f"HTDP Initialization failed: {e}")
            return np.zeros((self.ny, self.nx)), epsg_out

        logger.info(f"Generating HTDP Shift: {epsg_in}({self.epoch_in}) -> {epsg_out}({self.epoch_out})")
        
        west, east, south, north = self.extent#self.region.format('extent')
        #griddef = (east, north, west, south, self.nx, self.ny)
        griddef = (west, south, east, north, self.nx, self.ny)

        tmp_input = fetchezutils.make_temp_fn('htdp_in.xyz', temp_dir=self.cache_dir)
        tmp_output = fetchez.utils.make_temp_fn('htdp_out.xyz', temp_dir=self.cache_dir)
        tmp_control = fetchez.utils.make_temp_fn('htdp_ctrl.txt', temp_dir=self.cache_dir)

        grid = htdp_tool._new_create_grid(griddef)
        htdp_tool._write_grid(grid, tmp_input)

        id_in = Datums.HTDP[epsg_in]['htdp_id']
        id_out = Datums.HTDP[epsg_out]['htdp_id']
        
        htdp_tool._write_control(
            control_fn=tmp_control,
            out_grid_fn=tmp_output,
            in_grid_fn=tmp_input,
            src_crs_id=id_in,
            src_crs_date=self.epoch_in,
            dst_crs_id=id_out,
            dst_crs_date=self.epoch_out
        )

        htdp_tool.run(tmp_control)

        if os.path.exists(tmp_output):
            out_grid = htdp_tool._read_grid(tmp_output, (self.ny, self.nx))
        else:
            logger.error("HTDP failed to generate output grid.")
            out_grid = np.zeros((self.ny, self.nx))

        for fn in [tmp_input, tmp_output, tmp_control]:
            if os.path.exists(fn):
                os.remove(fn)

        return out_grid, epsg_out

    
    def _vertical_transform(self, epsg_in, epsg_out):
        """ Chaining logic for vertical transformations. """
        
        trans_array = np.zeros((self.ny, self.nx))
        unc_array = np.zeros((self.ny, self.nx))

        if self.geoid_in is not None and Datums.get_frame_type(epsg_in) == 'cdn':
            unc_array = np.sqrt(unc_array**2 + Datums.GEOIDS[self.geoid_in]['uncertainty']**2)
            tmp_trans_geoid, _ = self._cdn_transform(name='geoid', geoid=self.geoid_in)
            trans_array += tmp_trans_geoid
            epsg_in = 6319 # We are now at NAD83(2011)

        while epsg_in != epsg_out and epsg_in is not None:
            ref_in = Datums.get_frame_type(epsg_in)
            ref_out = Datums.get_frame_type(epsg_out)

            tmp_trans = np.zeros((self.ny, self.nx))

            if ref_in == 'surface':
                if ref_out == 'surface':
                    tmp_trans, _ = self._tidal_transform(Datums.SURFACES[epsg_in]['name'], 
                                                         Datums.SURFACES[epsg_out]['name'])
                    epsg_in = epsg_out
                else:
                    target_tidal = 'tss' if epsg_in != 7968 else None
                    tg, _ = self._tidal_transform(Datums.SURFACES[epsg_in]['name'], target_tidal)
                    
                    cg, cv = self._cdn_transform(name='geoid', geoid=self.geoid_out)
                    tmp_trans = tg + cg
                    epsg_in = cv 

            elif ref_in == 'htdp':
                unc_array = np.sqrt(unc_array**2 + Datums.HTDP[epsg_in]['uncertainty']**2)
                
                if ref_out == 'htdp':
                    tmp_trans, _ = self._htdp_transform(epsg_in, epsg_out)
                    epsg_in = epsg_out
                    
                elif ref_out == 'surface':
                    bridge_geoid = self.geoid_out if self.geoid_out else 'g2018'

                    cg, _ = self._cdn_transform(name='geoid', geoid=bridge_geoid)
                    tmp_trans = cg * -1 # Subtract Geoid to get to Ortho
                    
                    epsg_in = 5703 
                    
                else:
                    cg, cv = self._cdn_transform(epsg=epsg_out, invert=True)
                    hg, _ = self._htdp_transform(epsg_in, cv)
                    tmp_trans = cg + hg
                    epsg_in = epsg_out

            elif ref_in == 'cdn':
                if ref_out == 'cdn':
                    tmp_trans, cv = self._cdn_transform(epsg=epsg_in)
                    epsg_in = cv
                elif ref_out == 'surface':
                    tmp_trans, tv = self._tidal_transform('tss', Datums.SURFACES[epsg_out]['name'])
                    epsg_in = tv
                else:
                    tmp_trans, cv = self._cdn_transform(epsg=epsg_in)
                    epsg_in = cv

            trans_array += tmp_trans

        return trans_array, unc_array
