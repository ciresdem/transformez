#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.spatial
~~~~~~~~~~~~~

srs aware Region from fetchez

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
import warnings
import numpy as np
from fetchez.utils import str_or
from fetchez.spatial import Region as fetchezRegion
from . import srs

try:
    import pyproj
    from pyproj import CRS, Transformer
    HAS_PYPROJ = True
except ImportError:
    HAS_PYPROJ = False


logger = logging.getLogger(__name__)

class Region(fetchezRegion):

    def geo_transform(self, x_inc: float = 0, y_inc: float = None, node: str = 'grid'):
        """Return dimensions and a geotransform based on the region and a cellsize.

        Returns:
          list: [xcount, ycount, geot]
        """
        
        if y_inc is None:
            y_inc = -x_inc
        elif y_inc > 0:
            y_inc = -y_inc

        dst_gt = (self.xmin, x_inc, 0, self.ymax, 0, y_inc)
        this_origin = _geo2pixel(self.xmin, self.ymax, dst_gt, node=node)
        this_end = _geo2pixel(self.xmax, self.ymin, dst_gt, node=node)
        
        return int(this_end[0] - this_origin[0]), int(this_end[1] - this_origin[1]), dst_gt

    
    def to_geo_transform(region, nx: int, ny: int):
        """Generate a GDAL-style GeoTransform from extent and dimensions.
    
        Args:
        region (tuple): (min_x, min_y, max_x, max_y) - 'te' format.
        nx (int): Number of columns (x count).
        ny (int): Number of rows (y count).
        
        Returns:
        tuple: (top_left_x, x_res, 0, top_left_y, 0, -y_res)
        """
    
        x_res = (self.xmax - self.xmin) / float(nx)
        y_res = (self.ymax - self.ymin) / float(ny)
        return (self.xmin, x_res, 0, self.ymax, 0, -y_res)

    
    def densify_edges(self, density=20):
        """Generate a list of points along the perimeter of the region.

        Args:
            region (Region): Input region.
            density (int): Number of points per edge.

        Returns:
            list: A list of (x, y) tuples representing the densified perimeter.
        """

        if not self.valid_p():
            return []

        xs = []
        ys = []

        ys.extend(np.linspace(self.ymin, self.ymax, density))
        xs.extend([self.xmin] * density)

        xs.extend(np.linspace(self.xmin, self.xmax, density))
        ys.extend([self.ymax] * density)

        ys.extend(np.linspace(self.ymax, self.ymin, density))
        xs.extend([self.xmax] * density)

        xs.extend(np.linspace(self.xmax, self.xmin, density))
        ys.extend([self.ymin] * density)

        #return list(zip(xs, ys))
        return xs, ys

    
    def transform_densify(self, transformer=None, transform_direction="FORWARD"):
        if transformer is None or not self.valid_p():
            logger.error(f'Could not perform region transformation; {self}')
            return self
        
        points_x, points_y = self.densify_edges(20)
        trans_points_x, trans_points_y = transformer.transform(points_x, points_y, direction=transform_direction)

        self.xmin = min(trans_points_x)
        self.xmax = max(trans_points_x)
        self.ymin = min(trans_points_y)
        self.ymax = max(trans_points_y)
        
        ## set the new SRS
        #self.src_srs = d_srs.ExportToWkt()

        return self


    def transform(self, transformer=None, transform_direction="FORWARD"):
        if transformer is None or not self.valid_p():
            logger.error(f'Could not perform region transformation; {self}')
            return self

        self.xmin, self.ymin = transformer.transform(self.xmin, self.ymin, direction=transform_direction)
        self.xmax, self.ymax = transformer.transform(self.xmax, self.ymax, direction=transform_direction)

        return self

    
    def warp(self, dst_srs='epsg:4326'):
        """Transform region horizontally to a new CRS."""

        if not HAS_PYPROJ:
            logger.error("pyproj is required for reprojection.")
            return self
        
        if str_or(self.srs) is None:
            logger.warning(f'Region has no valid associated srs: {self.srs}')
            return self

        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            transform = srs.SRSParser(src_srs=self.srs, dst_srs=dst_srs)

            if transform.tc['src_horz_crs'] and transform.tc['dst_horz_crs']:        
                pipeline_str = '+proj=pipeline +step {} +inv +step {}'.format(
                    transform.tc['src_horz_crs'].to_proj4(), 
                    transform.tc['dst_horz_crs'].to_proj4()
                )
                transformer = pyproj.Transformer.from_pipeline(pipeline_str)

                self.src_srs = dst_srs
                self.wkt = None
                return self.transform_densify(transformer)

        return self
    

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


def transform_increment(dst_inc_x, dst_inc_y, transformer, region_center):
    """Transform grid increments from Destination SRS to Source SRS.
    
    Args:
        dst_inc_x (float): X increment in destination units (e.g. 1/3600 for 1s).
        dst_inc_y (float): Y increment in destination units.
        transformer (pyproj.Transformer): The pipeline transforming Source -> Dest.
        region_center (tuple): (x, y) center of the region in Source CRS.
        
    Returns:
        (float, float): The estimated (src_inc_x, src_inc_y) in source units.
    """
    
    if transformer is None:
        return dst_inc_x, dst_inc_y

    cx, cy = region_center
    dest_cx, dest_cy = transformer.transform(cx, cy)
    dest_off_x = dest_cx + dst_inc_x
    dest_off_y = dest_cy + dst_inc_y
    
    src_off_x, _ = transformer.transform(dest_off_x, dest_cy, direction="INVERSE")
    _, src_off_y = transformer.transform(dest_cx, dest_off_y, direction="INVERSE")
    
    src_inc_x = abs(src_off_x - cx)
    src_inc_y = abs(src_off_y - cy)
    
    return src_inc_x, src_inc_y
