#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.cli
~~~~~~~~~~~~~

The transformez CLI.
Generates vertical transformation grids using the Fetchez-DLIM ecosystem.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import sys
import argparse
import logging

import rasterio

from . import __version__
from .transform import VerticalTransform
from .definitions import Datums
from .grid_engine import plot_grid, GridWriter, GridEngine

from fetchez import spatial
from fetchez import utils
from fetchez.spatial import parse_region

logging.basicConfig(level=logging.INFO, format='[ %(levelname)s ] %(name)s: %(message)s', stream=sys.stderr)
logger = logging.getLogger(__name__)

logging.getLogger('fetchez').setLevel(logging.WARNING)

def parse_compound_datum(datum_arg):
    """Parse a datum string that might contain a geoid override.
    Format: "EPSG" or "EPSG:GEOID" or "NAME:GEOID"
    """
    if ':' in str(datum_arg):
        parts = str(datum_arg).split(':')
        datum = Datums.get_vdatum_by_name(parts[0])
        geoid = parts[1]
        return datum, geoid
    else:
        return Datums.get_vdatum_by_name(datum_arg), None

    
def get_grid_info(filename):
    """Extract region, resolution, and SRS from a raster using Rasterio."""
    
    with rasterio.open(filename) as ds:
        bounds = ds.bounds # left, bottom, right, top
        width = ds.width
        height = ds.height
        gt = ds.transform.to_gdal() # (c, a, b, f, d, e)
        srs_wkt = ds.crs.to_wkt() if ds.crs else None
        
        return {
            'te': (bounds.left, bounds.bottom, bounds.right, bounds.top),
            'region': (bounds.left, bounds.right, bounds.bottom, bounds.top),
            'nx': width,
            'ny': height,
            'gt': gt,
            'srs_wkt': srs_wkt
        }


def transformez_cli():
    parser = argparse.ArgumentParser(
        description=f'%(prog)s ({__version__}): Generate a vertical transformation grid',
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="CUDEM home page: <http://cudem.colorado.edu>"
    )

    input_grp = parser.add_mutually_exclusive_group(required=True)
    input_grp.add_argument('-R', '--region', help=spatial.region_help_msg())
    input_grp.add_argument('--dem', help='Input DEM to transform. Automatically sets Region and Resolution.')
    
    sel_grp = parser.add_argument_group('Geospatial Selection')
    sel_grp.add_argument('-E', '--increment', help='Grid resolution (e.g. 0.0001 or 1s) (Required if not using --dem).')

    datum_group = parser.add_argument_group('Datum Configuration')    
    datum_group.add_argument('-I', '--vdatum_in', default='5703', 
                        help='Input vertical datum. Format: "EPSG" or "EPSG:GEOID" (e.g. "5703:g2012a")')
    datum_group.add_argument('-O', '--vdatum_out', default='7662', 
                        help='Output vertical datum. Format: "EPSG" or "EPSG:GEOID"')
    datum_group.add_argument('--epoch-in', type=float, default=1997.0, 
                        help='Input coordinate epoch (decimal year).')
    datum_group.add_argument('--epoch-out', type=float, default=1997.0, 
                        help='Output coordinate epoch (decimal year).')

    proc_group = parser.add_argument_group('Processing Options')    
    proc_group.add_argument('--preview', action='store_true', help='Plot the transformation grid (matplotlib) before processing.')
    proc_group.add_argument('--output', help='Output filename (default auto-generated).')
    
    sys_group = parser.add_argument_group('System & Logging')    
    sys_group.add_argument('-D', '--cache-dir', help='Directory for storing temporary grids.')
    sys_group.add_argument('-k', '--keep-cache', action='store_true', help='Do not delete temporary files after run.')
    sys_group.add_argument('-l', '--list-epsg', action='store_true', help='List supported EPSG codes/names and exit.')
    sys_group.add_argument('-q', '--quiet', action='store_true', help='Suppress log output.')
    sys_group.add_argument('--version', action='version', version=f'%(prog)s {__version__}')

    # Handle negative coordinates in arguments
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

    cache_dir = args.cache_dir or os.path.join(os.path.expanduser('~'), '.transformez')
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)

    epsg_in, geoid_in = parse_compound_datum(args.vdatum_in)
    epsg_out, geoid_out = parse_compound_datum(args.vdatum_out)

    if args.dem:
        if not os.path.exists(args.dem):
            logger.error(f'Input DEM not found: {args.dem}')
            sys.exit(1)
            
        logger.info(f'Extracting grid info from DEM: {args.dem}')
        info = get_grid_info(args.dem)
        logger.info(f'Grid info is: {info}')
        
        # Override region and dimensions from DEM
        # info['te'] is (w, s, e, n)
        region_obj = spatial.Region.from_list(info['region'])
        nx = info['nx']
        ny = info['ny']

        if info.get('srs_wkt'):
            pass
        
        # Default Output Name for DEM
        if not args.output:
            base, ext = os.path.splitext(args.dem)
            dst_grid = f'{base}_trans_{epsg_out}{ext}'
        else:
            dst_grid = args.output
            
    elif args.region:
        # parse_region returns a list of Region objects
        # we're only using one for now.
        these_regions = parse_region(args.region)
        region_obj = these_regions[0]

        try:
            if '/' in args.increment:
                inc_x, inc_y = [float(x) for x in args.increment.split('/')]
            else:
                inc_val = utils.str2inc(args.increment)
                inc_x, inc_y = inc_val, inc_val
                
            width = region_obj.width
            height = region_obj.height
            nx = int(width / inc_x)
            ny = int(height / inc_y)
        except Exception as e:
            logger.error(f'Invalid increment: {args.increment}. {e}')
            sys.exit(1)
        
        if not args.output:
            base, ext = 'transformez_trans', 'tif' # Default to TIF now
            v_out_str = str(epsg_out)
            if geoid_out:
                v_out_str += f"_{geoid_out}"
            dst_grid = f"{base}_{epsg_in}_{v_out_str}.{ext}"
        else:
            dst_grid = args.output                
    else:
        logger.error("Region or DEM is required.")
        sys.exit(1)
            
    # Initialize Vertical Transform
    vt = VerticalTransform(
        region=region_obj, 
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
    
    logger.info(f"Generating shift grid: {epsg_in} -> {epsg_out}")
    shift_array, _ = vt._vertical_transform(vt.epsg_in, vt.epsg_out)
    
    if shift_array is not None:
        if args.preview:
            plot_grid(
                shift_array, 
                region=region_obj, 
                title=f"Shift: {epsg_in} -> {epsg_out}"
            )

        if args.dem:
            # Apply to DEM
            logger.info("Applying transformation to DEM...")
            GridEngine.apply_vertical_shift(args.dem, shift_array, dst_grid)
        else:
            # Just write the grid
            logger.info(f"Saving transformation grid to: {dst_grid}")            
            GridWriter.write(dst_grid, shift_array, region_obj)            
        return            
    else:
        logger.error("Failed to generate transformation grid.")

        
if __name__ == '__main__':
    transformez_cli()
