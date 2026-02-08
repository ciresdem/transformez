#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.spatial
~~~~~~~~~~~~~

srs parsing, etc.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import logging
import warnings
from fetchez.utils import int_or, str_or, str2inc

from .spatial import Region, transform_increment
from .definitions import Datums
from .transform import VerticalTransform

try:
    import pyproj
    from pyproj import CRS, Transformer
    HAS_PYPROJ = True
except ImportError:
    HAS_PYPROJ = False

logger = logging.getLogger(__name__)

class SRSParser:
    """Central logic for parsing SRS strings (Horizontal + Vertical)
    and building pyproj Transformers.
    """

    def __init__(self, src_srs, dst_srs, region=None, vert_grid=None, cache_dir='.', **kwargs):

        if not HAS_PYPROJ:
            raise ImportError("pyproj is required for reprojection.")

        self.src_srs_input = src_srs
        self.dst_srs_input = dst_srs
        self.forced_src_srs = src_srs
        self.manual_vert_grid = vert_grid
        self.cache_dir = cache_dir
        
        self._last_src_srs = None
        self.transformer = None
        self.region = region
        
        self.tc = {
            'src_horz_crs': None, 'dst_horz_crs': None,
            'src_vert_crs': None, 'dst_vert_crs': None,
            'src_vert_epsg': None, 'dst_vert_epsg': None,
            'src_geoid': None, 'dst_geoid': None,
            'want_vertical': False,
            'pipeline': None,
            'trans_fn': None  # The vertical grid file path
        }
        #self._parse_srs(self.src_srs_input, self.dst_srs_input)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            self._parse_srs()
            self.set_transform()

        
    def _parse_srs(self):
        if self.src_srs_input is not None and self.dst_srs_input is not None:
            want_vertical = True
            src_geoid = None
            dst_geoid = 'g2018' # dst_geoid is g2018 by default.
            in_vertical_epsg = in_vertical_crs = None
            out_vertical_epsg = out_vertical_crs = None
            
            # parse out the source geoid, which is not standard in proj,
            # reset `self.src_srs` without it.
            tmp_src_srs = self.src_srs_input.split('+geoid:')
            src_srs = tmp_src_srs[0]
            self.src_srs_input = src_srs
            if len(tmp_src_srs) > 1:
                src_geoid = tmp_src_srs[1]

            # parse out the destination geoid, which is not standard in proj
            # reset `self.dst_srs` without it.
            tmp_dst_srs = self.dst_srs_input.split('+geoid:')
            dst_srs = tmp_dst_srs[0]
            self.dst_srs_input = dst_srs
            if len(tmp_dst_srs) > 1:
                dst_geoid = tmp_dst_srs[1]

            # check if this is an ESRI epsg code
            is_esri = False
            in_vertical_epsg_esri = None
            if 'ESRI' in src_srs.upper():
                is_esri = True
                srs_split = src_srs.split('+')
                src_srs = srs_split[0]
                if len(srs_split) > 1:
                    in_vertical_epsg_esri = srs_split[1]

            if int_or(src_srs.split('+')[-1]) in Datums.SURFACES:
                src_srs = '{}+{}'.format(
                    src_srs.split('+')[0],
                    Datums.SURFACES[int_or(src_srs.split('+')[-1])]['epsg']
                )
                
            # set the proj crs from the src and dst srs input
            try:
                in_crs = pyproj.CRS.from_user_input(src_srs)
                out_crs = pyproj.CRS.from_user_input(dst_srs)
            except:
                logger.error([src_srs, dst_srs])

            # if the crs has vertical (compound), parse out the vertical crs
            # and set the horizontal and vertical crs
            if in_crs.is_compound:
                in_crs_list = in_crs.sub_crs_list
                in_horizontal_crs = in_crs_list[0]
                in_vertical_crs = in_crs_list[1]
                in_vertical_name = in_vertical_crs.name
                in_vertical_epsg = in_vertical_crs.to_epsg()
                if in_vertical_epsg is None:
                    in_vertical_epsg = in_vertical_name.split(' ')[0]
            else:
                in_horizontal_crs = in_crs
                want_vertical=False

            if out_crs.is_compound:            
                out_crs_list = out_crs.sub_crs_list
                out_horizontal_crs = out_crs_list[0]
                out_vertical_crs = out_crs_list[1]
                out_vertical_epsg = out_vertical_crs.to_epsg()
            else:
                out_horizontal_crs = out_crs
                want_vertical=False
                out_vertical_epsg=None

            # check if esri vertical
            if (in_vertical_epsg_esri is not None and is_esri):
                in_vertical_epsg = in_vertical_epsg_esri
                if out_vertical_epsg is not None:
                    want_vertical = True

            # make sure the input and output vertical epsg is different
            if want_vertical:
                if (in_vertical_epsg == out_vertical_epsg) and self.tc['src_geoid'] is None:
                    want_vertical = False

            # set `self.tc` with the parsed srs info
            self.tc['src_horz_crs'] = in_horizontal_crs
            self.tc['dst_horz_crs'] = out_horizontal_crs
            self.tc['src_vert_crs'] = in_vertical_crs
            self.tc['dst_vert_crs'] = out_vertical_crs
            self.tc['src_vert_epsg'] = in_vertical_epsg
            self.tc['dst_vert_epsg'] = out_vertical_epsg
            self.tc['src_geoid'] = src_geoid
            self.tc['dst_geoid'] = dst_geoid
            self.tc['want_vertical'] = want_vertical
            
    
    def set_vertical_transform(self):
        print(self.region)
        if self.region is None:
            return
        else:
            vd_region = Region.from_list(self.region)
            vd_region.srs = self.tc['dst_horz_crs'].to_proj4()

        vd_region.warp('epsg:4326')
        vd_region.buffer(pct=2)
        if not vd_region.valid_p():
            logger.warning('failed to generate transformation')
            return

        self.tc['trans_fn'] = os.path.join(
            self.cache_dir, '_vdatum_trans_{}_{}_{}.tif'.format(
                self.tc['src_vert_epsg'],
                self.tc['dst_vert_epsg'],
                vd_region.format('fn')
            )
        )
        
        ## if the transformation grid already exists, skip making a new one,
        ## otherwise, make the new one here with `vdatums.VerticalTransform()`
        if not os.path.exists(self.tc['trans_fn']):
            ## set the vertical transformation grid to be 3 arc-seconds. This
            ## is pretty arbitrary, maybe it's too small...
            vd_x_inc = vd_y_inc = str2inc('3s')
            xcount, ycount, dst_gt = vd_region.geo_transform(
                x_inc=vd_x_inc, y_inc=vd_y_inc, node='grid'
            )

            ## if the input region is so small it creates a tiny grid,
            ## keep increasing the increments until we are at least to
            ## a 10x10 grid.
            while (xcount <=10 or ycount <=10):
                vd_x_inc /= 2
                vd_y_inc /= 2
                xcount, ycount, dst_gt = vd_region.geo_transform(
                    x_inc=vd_x_inc, y_inc=vd_y_inc, node='grid'
                )

            ## run `vdatums.VerticalTransform()`, grid using `nearest`
            #self.transform['trans_fn'], self.transform['trans_fn_unc'] \
            vt = VerticalTransform(
                vd_region,
                xcount,
                ycount,
                epsg_in=self.tc['src_vert_epsg'],
                epsg_out=self.tc['dst_vert_epsg'],
                geoid_in=self.tc['src_geoid'],
                geoid_out=self.tc['dst_geoid'],
                cache_dir=self.cache_dir,
            )
            
            self.tc['trans_fn'], _ = vt._vertical_transform(vt.epsg_in, vt.epsg_out)
            self.manual_vert_grid = self.tc['trans_fn']
            
        ## set the pyproj.Transformer for both horz+vert and vert only
        ## hack for navd88 datums in feet (6360 is us-feet, 8228 is international-feet
        if str_or(self.tc['src_vert_epsg']) == '6360':
            # or 'us-ft' in utils.str_or(src_vert, ''):
            #out_src_srs = out_src_srs + ' +vto_meter=0.3048006096012192'
            uc = ' +step +proj=unitconvert +z_in=us-ft +z_out=m'
        elif str_or(self.tc['src_vert_epsg']) == '8228':
            uc = ' +step +proj=unitconvert +z_in=ft +z_out=m'
        else:
            uc = ''

        if self.tc['trans_fn'] is not None \
           and os.path.exists(self.tc['trans_fn']) \
           and os.stat(self.tc['trans_fn']).st_size > 0:
                
            self.tc['pipeline'] \
                = (f'+proj=pipeline{uc} +step '
                   f'{self.tc["src_horz_crs"].to_proj4()} '
                   '+inv +step +proj=vgridshift '
                   f'+grids="{os.path.abspath(self.tc["trans_fn"])}" '
                   f'+inv +step {self.tc["dst_horz_crs"].to_proj4()}')
            self.tc['vert_transformer'] = pyproj.Transformer.from_pipeline(
                (f'+proj=pipeline{uc} +step +proj=vgridshift '
                 f'+grids="{os.path.abspath(self.tc["trans_fn"])}" +inv')
            )
            logger.debug(self.tc['pipeline'])
            
            
    def set_transform(self):
        """Set the pyproj horizontal and vertical transformations 
        for the dataset
        """

        if self.tc['src_horz_crs'] is not None \
           and self.tc['dst_horz_crs'] is not None:        
            ## horizontal Transformation
            self.tc['horz_pipeline'] \
                = ('+proj=pipeline +step '
                   f'{self.tc["src_horz_crs"].to_proj4()} '
                   f'+inv +step {self.tc["dst_horz_crs"].to_proj4()}')
            
            self.tc['pipeline'] = self.tc['horz_pipeline']                
            ## vertical Transformation
            if self.tc['want_vertical']:
                self.set_vertical_transform()


            #try:
            #print(self.tc['pipeline'])
            self.tc['transformer'] \
                = pyproj.Transformer.from_pipeline(
                    self.tc['pipeline']
                )
            #except Exception as e:
            #    logger.warning(
            #        ('could not set transformation in: '
            #         f'{self.tc["src_horz_crs"].name}, out: '
            #         f'{self.tc["dst_horz_crs"].name}, {e}')
            #        )

            #return

        if self.region is not None:
            self.region.srs = self.src_srs_input
            self.tc['trans_region'] = Region.from_list(self.region)
        else:
            self.tc['trans_region'] = None

        if self.tc['transformer'] is not None:
            if self.tc['trans_region'] is not None:
                self.tc['trans_region'].transform_densify(self.tc['transformer'], transform_direction="INVERSE")
            
        # if self.x_inc is not None and self.y_inc is not None:
        #     # Get center of the native region
        #     center_x = (self.tc['trans_region'].xmax + self.tc['trans_region'].xmin) / 2.0
        #     center_y = (self.tc['trans_region'].ymax + self.tc['trans_region'].ymin) / 2.0
        #     # Calculate increments in Source Units (e.g. Meters)
        #     src_x_inc, src_y_inc = transform_increment(
        #         self.x_inc, self.y_inc, 
        #         self.transform['transformer'], 
        #         (center_x, center_y)
        #     )
        #     self.tc['trans_inc'] = (src_x_inc, src_y_inc)
        # else:
        #     self.tc['trans_inc'] = None
             
            
    def _build_pipeline(self):
        """Construct the PROJ pipeline string based on parsed config."""
        
        # 1. Horizontal Pipeline (Always needed)
        # Format: Source -> Inv -> Dest
        horz_pipe = (
            f"+proj=pipeline +step "
            f"{self.tc['src_horz_crs'].to_proj4()} "
            f"+inv +step {self.tc['dst_horz_crs'].to_proj4()}"
        )

        if not self.tc['want_vertical']:
            return horz_pipe

        # 2. Vertical Logic
        # Try to locate the grid file
        grid_path = self.manual_vert_grid
        
        if not grid_path or not os.path.exists(grid_path):
            logger.debug("Vertical grid not found. Falling back to horizontal transform only.")
            return horz_pipe

        # 3. Handle Units (Feet/Meters) for Vertical Grid
        # NAVD88 often needs unit conversion before applying grid
        uc = ""
        s_epsg = str_or(self.tc['src_vert_epsg'])
        if s_epsg == '6360': # US Feet
            uc = " +step +proj=unitconvert +z_in=us-ft +z_out=m"
        elif s_epsg == '8228': # Int Feet
            uc = " +step +proj=unitconvert +z_in=ft +z_out=m"

        # 4. Construct Full 3D Pipeline
        # Source Horiz -> Unit Convert (if needed) -> VGridShift -> Target Horiz
        pipeline = (
            f"+proj=pipeline{uc} +step "
            f"{self.tc['src_horz_crs'].to_proj4()} "
            f"+inv +step +proj=vgridshift "
            f"+grids=\"{os.path.abspath(grid_path)}\" +multiplier=1 "
            f"+inv +step {self.tc['dst_horz_crs'].to_proj4()}"
        )
        
        logger.debug(f"Reprojection Pipeline: {pipeline}")
        return pipeline


    def _parse_srs_(self, src_srs_input, dst_srs_input):
        """Parse SRS strings to separate Horizontal/Vertical components
        and detect custom Geoids. Adapted from CUDEM.
        """
        
        for k in self.tc: self.tc[k] = None
        self.tc['want_vertical'] = True
        self.tc['dst_geoid'] = 'g2018' 

        tmp_src = src_srs_input.split('+geoid:')
        clean_src = tmp_src[0]
        if len(tmp_src) > 1: self.tc['src_geoid'] = tmp_src[1]

        tmp_dst = dst_srs_input.split('+geoid:')
        clean_dst = tmp_dst[0]
        if len(tmp_dst) > 1: self.tc['dst_geoid'] = tmp_dst[1]

        is_esri = 'ESRI' in clean_src.upper()
        in_vert_epsg_esri = None
        if is_esri:
            parts = clean_src.split('+')
            clean_src = parts[0]
            if len(parts) > 1: in_vert_epsg_esri = parts[1]

        last_part = clean_src.split('+')[-1]
        if int_or(last_part) in Datums.SURFACES:
            clean_src = '{}+{}'.format(
                clean_src.split('+')[0],
                Datums.SURFACES[int_or(last_part)]['epsg']
            )

        try:
            in_crs = CRS.from_user_input(clean_src)
            out_crs = CRS.from_user_input(clean_dst)
        except Exception as e:
            logger.error(f"Invalid SRS input: {clean_src} or {clean_dst}. {e}")
            return False

        if in_crs.is_compound:
            self.tc['src_horz_crs'] = in_crs.sub_crs_list[0]
            self.tc['src_vert_crs'] = in_crs.sub_crs_list[1]
            self.tc['src_vert_epsg'] = self.tc['src_vert_crs'].to_epsg()
            # Fallback for name-based lookup if EPSG missing
            if not self.tc['src_vert_epsg']:
                self.tc['src_vert_epsg'] = self.tc['src_vert_crs'].name.split(' ')[0]
        else:
            self.tc['src_horz_crs'] = in_crs
            self.tc['want_vertical'] = False

        if out_crs.is_compound:
            self.tc['dst_horz_crs'] = out_crs.sub_crs_list[0]
            self.tc['dst_vert_crs'] = out_crs.sub_crs_list[1]
            self.tc['dst_vert_epsg'] = self.tc['dst_vert_crs'].to_epsg()
        else:
            self.tc['dst_horz_crs'] = out_crs
            if not self.tc['dst_geoid']:
                self.tc['want_vertical'] = False

        if (in_vert_epsg_esri and is_esri):
            self.tc['src_vert_epsg'] = in_vert_epsg_esri
            if self.tc['dst_vert_epsg']: self.tc['want_vertical'] = True

        if self.tc['want_vertical']:
            if (self.tc['src_vert_epsg'] == self.tc['dst_vert_epsg']) and not self.tc['src_geoid']:
                self.tc['want_vertical'] = False

        return True

    
    def _get_transformer(self, src_srs):
        """Build or retrieve cached transformer."""
        
        actual_src = self.forced_src_srs if self.forced_src_srs else src_srs
        if not actual_src: return None
            
        if self.transformer and actual_src == self._last_src_srs:
            return self.transformer

        if not self._parse_srs(actual_src, self.dst_srs_input):
            return None

        pipeline_str = self._build_pipeline()
        
        try:
            self.transformer = Transformer.from_pipeline(pipeline_str)
            self._last_src_srs = actual_src
            return self.transformer
        except Exception as e:
            logger.error(f"Failed to init transformer: {e}")
            return None
