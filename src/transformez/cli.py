#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.cli
~~~~~~~~~~~~~

The transformez CLI

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import sys
import argparse
import logging
from osgeo import gdal, osr

from . import __version__
from .transform import VerticalTransform
from .definitions import Datums
from .gtx import GtxFile
from .grid_engine import plot_grid

from fetchez import spatial

logging.basicConfig(level=logging.INFO, format='[ %(levelname)s ] %(name)s: %(message)s', stream=sys.stderr)
logger = logging.getLogger(__name__)

gdal.UseExceptions()

def parse_compound_datum(datum_arg):
    """Parse a datum string that might contain a geoid override.

    Format: "EPSG" or "EPSG:GEOID" or "NAME:GEOID"
    Example: "5703:g2012a" -> (5703, "g2012a")
    """
    
    if ':' in str(datum_arg):
        parts = str(datum_arg).split(':')
        # First part is the datum name/code
        datum = Datums.get_vdatum_by_name(parts[0])
        # Second part is the geoid override
        geoid = parts[1]
        return datum, geoid
    else:
        return Datums.get_vdatum_by_name(datum_arg), None


def get_grid_info(filename):
    """Extract extent, resolution, and SRS from a raster without cudem.gdalfun."""
    
    ds = gdal.Open(filename)
    if not ds:
        raise IOError(f'Could not open file: {filename}')
        
    gt = ds.GetGeoTransform()
    width = ds.RasterXSize
    height = ds.RasterYSize
    
    # Calculate bounding box (min_x, min_y, max_x, max_y)
    min_x = gt[0]
    max_y = gt[3]
    max_x = min_x + (gt[1] * width)
    min_y = max_y + (gt[5] * height)
    
    # Get SRS
    proj = ds.GetProjection()
    srs = osr.SpatialReference()
    srs.ImportFromWkt(proj)
    
    ds = None # Close dataset
    
    return {
        'te': (min_x, min_y, max_x, max_y), # gdalwarp standard -te order
        'nx': width,
        'ny': height,
        'gt': gt,
        'srs_wkt': proj,
        'srs_obj': srs
    }

def transformez_cli():
    parser = argparse.ArgumentParser(
        description=f'%(prog)s ({__version__}): Generate a vertical transformation grid',
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
CUDEM home page: <http://cudem.colorado.edu>
        """
    )

    # Region and Resolution
    sel_grp = parser.add_argument_group('Geospatial Selection')
    sel_grp.add_argument('-R', '--region', required=True, help=spatial.region_help_msg())
    sel_grp.add_argument('-E', '--increment', required=True, help='Grid resolution.')

    datum_group = parser.add_argument_group('Datum Configuration')    
    datum_group.add_argument('-I', '--vdatum_in', default='5703', 
                        help='Input vertical datum. Format: "EPSG" or "EPSG:GEOID" (e.g. "5703:g2012a")')
    datum_group.add_argument('-O', '--vdatum_out', default='7662', 
                        help='Output vertical datum. Format: "EPSG" or "EPSG:GEOID"')
    datum_group.add_argument('--epoch-in', type=float, default=1997.0, 
                        help='Input coordinate epoch (decimal year).')
    datum_group.add_argument('--epoch-out', type=float, default=1997.0, 
                        help='Output coordinate epoch (decimal year).')

    # PROCESSING & OUTPUT
    proc_group = parser.add_argument_group('Processing Options')    
    proc_group.add_argument('--preview', action='store_true', help='Plot the transformation grid (matplotlib) before processing.')
    proc_group.add_argument('--output', required=True, help='Output GeoTIFF filename.')
    
    sys_group = parser.add_argument_group('System & Logging')    
    sys_group.add_argument('-D', '--cache-dir', help='Directory for storing temporary grids.')
    sys_group.add_argument('-k', '--keep-cache', action='store_true', help='Do not delete temporary files after run.')
    sys_group.add_argument('-l', '--list-epsg', action='store_true', help='List supported EPSG codes/names and exit.')
    sys_group.add_argument('-q', '--quiet', action='store_true', help='Suppress log output.')
    sys_group.add_argument('--version', action='version', version=f'%(prog)s {__version__}')

    fixed_argv = spatial.fix_argparse_region(sys.argv[1:])
    args = parser.parse_args(fixed_argv)

    if args.quiet:
        logger.setLevel(logging.WARNING)

    if args.list_epsg:
        def _print_epsg(title, data):
            print(f'{title}:')
            for key, val in data.items():
                print(f'  {key}\t{val["name"]}')
        
        _print_epsg('HTDP EPSG', Datums.HTDP)
        _print_epsg('CDN EPSG', Datums.CDN)
        _print_epsg('Tidal EPSG', Datums.TIDAL)
        sys.exit(0)

    # Setup Cache
    cache_dir = args.cache_dir
    if not cache_dir:
        # Standardize on ~/.transformez
        cache_dir = os.path.join(os.path.expanduser('~'), '.transformez')
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)

    # Determine Output Filename
    if not args.output:
        base, ext = 'transformez_trans', 'gtx'
        # Create a readable suffix, e.g., _6319_g2012a
        v_out_str = str(epsg_out)
        if geoid_out:
            v_out_str += f"_{geoid_out}"
        dst_grid = f"{base}_{v_out_str}{ext}"
    else:
        dst_grid = args.output
        
    epsg_in, geoid_in = parse_compound_datum(args.vdatum_in)
    epsg_out, geoid_out = parse_compound_datum(args.vdatum_out)

    if args.region:
        these_regions = spatial.parse_region(args.region)
        region = these_regions[0]
        
    if args.increment:
        increment = [int(x) for x in args.increment.split('/')]
        
    #extent = spatial.region_to_bbox(region)
    nx = increment[0]
    ny = increment[1]
    
    # Initialize Vertical Transform
    vt = VerticalTransform(
        extent=region,
        nx=nx,
        ny=ny,
        epsg_in=epsg_in, 
        epsg_out=epsg_out,
        geoid_in=geoid_in,
        geoid_out=geoid_out,
        epoch_in=args.epoch_in,
        epoch_out=args.epoch_out,
        cache_dir=cache_dir,
    )
    
    # This returns the vertical *shift* grid.
    logger.info(f"Generating shift grid: {epsg_in} -> {epsg_out}")
    shift_array, _ = vt._vertical_transform(vt.epsg_in, vt.epsg_out)
    
    if shift_array is not None:
        if args.preview:
            plot_grid(
                shift_array, 
                extent=extent, 
                title=f"Shift: {epsg_in} -> {epsg_out}"
            )

        logger.info(f"Saving transformation grid to: {dst_grid}")            
        src_info = {'nx': nx, 'ny': ny, 'gt': vt.gt}
        GtxFile.write(dst_grid, shift_array, extent)
        return 
    else:
        logger.error("Failed to generate transformation grid.")

        
if __name__ == '__main__':
    transformez_cli()
