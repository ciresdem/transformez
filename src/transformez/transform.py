#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.transform
~~~~~~~~~~~~~

This is the main transformation class.
Implements a Hub-and-Spoke transformation model centered on NAD83(2011).

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

# The Geodetic Pivot: NAD83(2011) / EPSG:6319
# We should change this to wgs i think
HUB_EPSG = 6319

def region_geo_transform(region, nx: int, ny: int):
    """Generate a GDAL-style GeoTransform from region and dimensions."""
    
    min_x, min_y, max_x, max_y = region
    x_res = (max_x - min_x) / float(nx)
    y_res = (max_y - min_y) / float(ny)
    return (min_x, x_res, 0, max_y, 0, -y_res)


class VerticalTransform:
    """Generate a vertical transformation grid using Transformez definitions and fetchez."""
    
    def __init__(self, region, nx, ny, epsg_in, epsg_out,
                 geoid_in=None, geoid_out=None, epoch_in=1997.0, epoch_out=1997.0,
                 cache_dir=None, verbose=True):
        
        self.region = region
        self.nx = nx
        self.ny = ny
        self.gt = region_geo_transform(self.region, self.nx, self.ny)
        self.cache_dir = cache_dir or os.path.join(os.getcwd(), 'transformez_cache')
        self.verbose = verbose
        
        # Resolve EPSGs
        self.epsg_in = Datums.get_vdatum_by_name(str(epsg_in))
        self.epsg_out = Datums.get_vdatum_by_name(str(epsg_out))
        
        # Resolve Geoids
        self.geoid_in = geoid_in or Datums.get_default_geoid(self.epsg_in)
        self.geoid_out = geoid_out or Datums.get_default_geoid(self.epsg_out)

        self.epoch_in = float(epoch_in) if epoch_in else 1997.0
        self.epoch_out = float(epoch_out) if epoch_out else 1997.0
        
        # Frame Types
        self.ref_in = Datums.get_frame_type(self.epsg_in)
        self.ref_out = Datums.get_frame_type(self.epsg_out)

        
    # =========================================================================
    # Data Fetching
    # =========================================================================    
    def fetch_grid(self, module_name, **kwargs):
        """Generic fetcher wrapper."""
        
        Mod = fetchez.registry.FetchezRegistry.load_module(module_name)
        if not Mod:
            logger.error(f"Module '{module_name}' not found.")
            return []

        fetcher = Mod(src_region=self.region, **kwargs)#outdir=self.cache_dir, **kwargs)
        fetcher.run()
        
        if fetcher.results:
            fetchez.core.run_fetchez([fetcher], threads=2)
            
        valid = []
        for r in fetcher.results:
            fn = r['dst_fn']
            if fn.endswith('.zip') and os.path.exists(fn):
                extracted = fetchez.utils.p_f_unzip(fn, fns=[r['data_type']], outdir=self.cache_dir)
                valid.extend([f for f in extracted if f.endswith(('.gtx', '.tif'))])
            elif os.path.exists(fn) and fn.endswith(('.gtx', '.tif')):
                valid.append(fn)
        return valid

    
    def _get_grid(self, provider, name):
        """Helper to fetch and interpolate a grid."""
        
        if not name: return np.zeros((self.ny, self.nx))        
        if not provider: provider = 'proj'

        if 'geoid=' in name: name = name[6:]

        files = self.fetch_grid(provider, datatype=name, query=name)
        if not files:
            # we should try to check other providers here just in case...
            logger.warning(f"No grids found for {name} via {provider}")
            return np.zeros((self.ny, self.nx))
            
        return GridEngine.load_and_interpolate(files, self.region, self.nx, self.ny)

    
    # =========================================================================
    # The VDatum Chain 
    # =========================================================================
    def _get_vdatum_chain(self, datum_name, geoid_name):
        """Builds the shift from Tidal Datum -> NAD83 Ellipsoid (Hub).

        Equation: Hub_Z = Tidal_Z + Tidal_Sep + TSS + Geoid_N
        """
        
        total_shift = np.zeros((self.ny, self.nx))
        desc = []

        # Tidal -> LMSL (Add Separation)
        # mllw.gtx is positive (LMSL is above MLLW)
        if datum_name not in ['msl', '5714', 'lmsl']:
            grid = self._get_grid('vdatum', datum_name)
            total_shift += grid
            desc.append(f"({datum_name}->LMSL)")

        # LMSL -> Ortho (Add TSS)
        # tss.gtx is positive (NAVD88 is above LMSL usually? VDatum convention: TSS = NAVD88 - LMSL)
        # So LMSL + TSS = NAVD88
        tss = self._get_grid('vdatum', 'tss')
        total_shift += tss
        desc.append("TSS")

        # Ortho -> Ellipsoid (Add Geoid N)
        # N is negative. Ortho + N = Ellipsoid.
        actual_geoid = geoid_name if geoid_name else 'g2018'
        
        geoid_def = Datums.GEOIDS.get(actual_geoid, {})
        provider = geoid_def.get('provider', 'proj')
        
        geoid = self._get_grid(provider, actual_geoid)
        total_shift += geoid
        desc.append(f"Geoid({actual_geoid})")
        
        return total_shift, " + ".join(desc)

    
    def _get_htdp_shift(self, epsg_from, epsg_to, epoch_from, epoch_to):
        """Calculate Ellipsoid Frame/Epoch shift."""
        
        if epsg_from == epsg_to and epoch_from == epoch_to:
            return np.zeros((self.ny, self.nx))
            
        from . import htdp
        try:
            tool = htdp.HTDP(verbose=False)
            return tool.run_grid(self.region, self.nx, self.ny, epsg_from, epsg_to, epoch_from, epoch_to)
        except Exception:
            return np.zeros((self.ny, self.nx))

        
    # =========================================================================
    # The Transformation
    # =========================================================================
    def _step_to_hub(self, epsg, ref_type, geoid=None, epoch=None):
        """Calculate shift FROM Input TO Hub (NAD83_2011)."""
        
        shift = np.zeros((self.ny, self.nx))
        desc = ""

        if epsg == HUB_EPSG and epoch == 1997.0:
            return shift, "Already at Hub"

        if ref_type == 'surface':
            # Tidal -> [LMSL -> Ortho -> Geoid] -> Hub
            # Hub = Input + Chain
            datum_name = Datums.SURFACES[epsg]['name']
            chain_shift, chain_desc = self._get_vdatum_chain(datum_name, geoid)
            
            shift = chain_shift
            desc = f"Tidal({datum_name}) -> Hub [Add Chain: {chain_desc}]"

        elif ref_type == 'cdn':
            # Ortho -> Hub (Ellipsoid = Ortho + Geoid)
            if geoid:
                geoid_def = Datums.GEOIDS.get(geoid, {})
                provider = geoid_def.get('provider', 'proj')
                shift = self._get_grid(provider, geoid)
                desc = f"Ortho(via {geoid}) -> Hub [Geoid Add]"
            else:
                desc = "Ortho -> Hub [Missing Geoid - Zero Shift]"

        elif ref_type == 'htdp':
            # Ellipsoid -> Hub
            shift = self._get_htdp_shift(epsg, HUB_EPSG, epoch, 1997.0)
            desc = f"Ellipsoid({epsg}@{epoch}) -> Hub [HTDP]"

        return shift, desc

    
    def _step_from_hub(self, epsg, ref_type, geoid=None, epoch=None):
        """Calculate shift FROM Hub (NAD83_2011) TO Output.
        Output_Z = Hub_Z + Shift
        """
        
        shift = np.zeros((self.ny, self.nx))
        desc = ""

        if epsg == HUB_EPSG and epoch == 1997.0:
            return shift, "Remain at Hub"

        if ref_type == 'surface':
            # Hub -> Tidal
            # Inverse of Chain: Tidal = Hub - Chain
            datum_name = Datums.SURFACES[epsg]['name']
            chain_geoid = geoid if geoid else 'g2018'
            
            chain_shift, chain_desc = self._get_vdatum_chain(datum_name, chain_geoid)
            
            shift = chain_shift * -1
            desc = f"Hub -> Tidal({datum_name}) [Subtract Chain: {chain_desc}]"

        elif ref_type == 'cdn':
            # Hub -> Ortho (Ortho = Ellipsoid - Geoid)
            target_geoid = geoid if geoid else 'g2018'
            geoid_def = Datums.GEOIDS.get(target_geoid, {})
            provider = geoid_def.get('provider', 'proj')
            grid = self._get_grid(provider, target_geoid)
            
            shift = grid * -1
            desc = f"Hub -> Ortho(via {target_geoid}) [Geoid Subtract]"

        elif ref_type == 'htdp':
            # Hub -> Ellipsoid
            shift = self._get_htdp_shift(HUB_EPSG, epsg, 1997.0, epoch)
            desc = f"Hub -> Ellipsoid({epsg}@{epoch}) [HTDP]"

        return shift, desc    

    
    def _vertical_transform(self, epsg_in, epsg_out):
        """Execute the transformation pipeline via the Hub."""
        
        logger.info("-" * 60)
        logger.info(f"Transformation Plan: EPSG:{self.epsg_in} -> EPSG:{self.epsg_out}")
        
        total_shift = np.zeros((self.ny, self.nx))
        total_unc = np.zeros((self.ny, self.nx)) 

        if self.epsg_in == self.epsg_out and self.epoch_in == self.epoch_out and self.geoid_in == self.geoid_out:
            logger.info("  1. Identity Transform (Zero Shift)")
            return total_shift, total_unc

        # 1. Input -> Hub
        grid_1, desc_1 = self._step_to_hub(self.epsg_in, self.ref_in, self.geoid_in, self.epoch_in)
        if np.any(grid_1):
            logger.info(f"  1. {desc_1}")
            total_shift += grid_1
        else:
            logger.info(f"  1. {desc_1} (No Shift/Zero)")

        # 2. Hub -> Output
        grid_2, desc_2 = self._step_from_hub(self.epsg_out, self.ref_out, self.geoid_out, self.epoch_out)
        if np.any(grid_2):
            logger.info(f"  2. {desc_2}")
            total_shift += grid_2
        else:
            logger.info(f"  2. {desc_2} (No Shift/Zero)")

        logger.info("-" * 60)
        
        return total_shift, total_unc
