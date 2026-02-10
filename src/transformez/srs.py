#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.srs
~~~~~~~~~~~~~

SRS functions; defining a proj horizontal transformer
and a self generated vertical transformation grid.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import logging
import pyproj
from pyproj import CRS, Transformer

from fetchez.spatial import Region
from .definitions import Datums
from .transform import VerticalTransform
from .grid_engine import GridWriter

logger = logging.getLogger(__name__)

class SRSParser:
    """Parses SRS and prepares a Decoupled Transformation:

    - Horizontal: Source -> Hub (NAD83) -> Dest
    - Vertical:   Z + Shift_Grid
    """

    def __init__(self, src_srs, dst_srs, region=None, vert_grid=None, cache_dir='.', **kwargs):
        self.src_srs_input = src_srs
        self.dst_srs_input = dst_srs
        self.region = region
        self.manual_vert_grid = vert_grid
        self.cache_dir = cache_dir
        
        self.tc = {
            'src_crs': None, 'dst_crs': None,
            'src_vert_epsg': None, 'dst_vert_epsg': None,
            'src_geoid': None, 'dst_geoid': None,
            'want_vertical': False,
            'trans_fn': None
        }
        
        self._parse_srs()

        
    def _extract_geoid(self, srs_str):
        parts = str(srs_str).split('+geoid:')
        return parts[0], (parts[1] if len(parts) > 1 else None)

    
    def _get_epsg_int(self, crs):
        """Extract EPSG integer from a CRS."""
        
        try:
            return int(crs.to_epsg())
        except:
            return None

        
    def _parse_srs(self):
        # Parse Input Strings
        clean_src, self.tc['src_geoid'] = self._extract_geoid(self.src_srs_input)
        clean_dst, self.tc['dst_geoid'] = self._extract_geoid(self.dst_srs_input)

        try:
            self.tc['src_crs'] = CRS.from_user_input(clean_src)
            self.tc['dst_crs'] = CRS.from_user_input(clean_dst)
        except Exception as e:
            logger.error(f"Invalid SRS: {e}")
            return
        
        # Extract vertical components before flattening
        if self.tc['src_crs'].is_compound:
            self.tc['src_vert_epsg'] = self._get_epsg_int(self.tc['src_crs'].sub_crs_list[1])
            # Strip to Horizontal for PROJ Transformer
            self.tc['src_crs'] = self.tc['src_crs'].sub_crs_list[0]
        elif self.tc['src_crs'].is_vertical:
            self.tc['src_vert_epsg'] = self._get_epsg_int(self.tc['src_crs'])

        if self.tc['dst_crs'].is_compound:
            self.tc['dst_vert_epsg'] = self._get_epsg_int(self.tc['dst_crs'].sub_crs_list[1])
            self.tc['dst_crs'] = self.tc['dst_crs'].sub_crs_list[0]
        elif self.tc['dst_crs'].is_vertical:
            self.tc['dst_vert_epsg'] = self._get_epsg_int(self.tc['dst_crs'])

        # Lookup default geoids
        # If we have a vertical EPSG but no manual geoid, look it up in definitions.py
        if self.tc['src_vert_epsg'] and not self.tc['src_geoid']:
            self.tc['src_geoid'] = Datums.get_default_geoid(self.tc['src_vert_epsg'])
            
        if self.tc['dst_vert_epsg'] and not self.tc['dst_geoid']:
            self.tc['dst_geoid'] = Datums.get_default_geoid(self.tc['dst_vert_epsg'])

        # We want vertical if we have explicit vertical EPSGs OR manual geoids
        has_src_vert = (self.tc['src_vert_epsg'] is not None) or (self.tc['src_geoid'] is not None)
        has_dst_vert = (self.tc['dst_vert_epsg'] is not None) or (self.tc['dst_geoid'] is not None)
        
        self.tc['want_vertical'] = has_src_vert or has_dst_vert


    def set_vertical_transform(self):
        """Generates the vertical shift grid using VerticalTransform."""
        
        if not self.region or not self.tc['want_vertical']:
            return

        try:
            proc_region = self.region.copy()
            proc_region.buffer(pct=5)
        except AttributeError:
            proc_region = Region.from_list(self.region)
            proc_region.buffer(pct=5)
            
        s_ident = self.tc['src_vert_epsg']
        d_ident = self.tc['dst_vert_epsg']
            
        if not s_ident and self.tc['src_geoid']: s_ident = 6319 
        if not d_ident and self.tc['dst_geoid']: d_ident = 6319        
        if not s_ident or not d_ident: return

        s_name = str(s_ident).replace(':', '_').replace(' ', '_').replace('/', '_')
        d_name = str(d_ident).replace(':', '_').replace(' ', '_').replace('/', '_')
        grid_name = f"_vdatum_trans_{s_name}_{d_name}_{proc_region.format('fn')}.tif"
        self.tc['trans_fn'] = grid_name.replace('\\', '/')

        if not os.path.exists(self.tc['trans_fn']):
            logger.info(f"Generating vertical grid: {s_ident} -> {d_ident} : {self.tc['trans_fn']} :")
            bbox = proc_region.to_bbox()
            vt = VerticalTransform(
                proc_region,
                nx=max(10, int(proc_region.width / 0.0008333)),
                ny=max(10, int(proc_region.height / 0.0008333)),
                epsg_in=s_ident,
                epsg_out=d_ident,
                geoid_in=self.tc['src_geoid'],
                geoid_out=self.tc['dst_geoid']
            )
            shift_arr, _ = vt._vertical_transform(vt.epsg_in, vt.epsg_out)
            GridWriter.write(self.tc['trans_fn'], shift_arr, proc_region)

        self.manual_vert_grid = self.tc['trans_fn']

        
    def get_components(self):
        """Returns the components:

        - Transformer: Source -> Hub (NAD83 2D)
        - Transformer: Hub -> Dest (2D)
        - Grid Path (str) or None
        """
        
        if self.tc['want_vertical'] and not self.manual_vert_grid:
            self.set_vertical_transform()

        # Define Hub: NAD83(2011) 2D - maybe this should be wgs(transit)
        hub_crs = CRS.from_epsg(4269)

        # only build 2D transformer (for proj). We'll apply the vertical grid ourselves,
        # as pyproj seems finicky when it comes to this.
        t_to_hub = Transformer.from_crs(self.tc['src_crs'], hub_crs, always_xy=True)
        t_from_hub = Transformer.from_crs(hub_crs, self.tc['dst_crs'], always_xy=True)
        
        return t_to_hub, t_from_hub, self.manual_vert_grid
