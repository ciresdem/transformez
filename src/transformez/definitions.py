#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.definitions
~~~~~~~~~~~~~

This file contains the various vertical datum transformation references 
and definitions.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging

logger = logging.getLogger(__name__)

class Datums:
    """Class to manage vertical datum definitions and lookups."""

    # =========================================================================
    # Vertical Datum References
    # =========================================================================
    SURFACES = {
        # --- Tidal Datums ---
        1089: {'name': 'mllw', 'description': 'Mean Lower Low Water', 'uncertainty': 0, 'epsg': 5866},
        5866: {'name': 'mllw', 'description': 'Mean Lower Low Water', 'uncertainty': 0, 'epsg': 5866},
        1091: {'name': 'mlw',  'description': 'Mean Low Water', 'uncertainty': 0, 'epsg': 1091},
        5869: {'name': 'mhhw', 'description': 'Mean Higher High Water', 'uncertainty': 0, 'epsg': 5869},
        5868: {'name': 'mhw', 'description': 'Mean High Water', 'uncertainty': 0, 'epsg': 5868},
        5714: {'name': 'msl', 'description': 'Mean Sea Level', 'uncertainty': 0, 'epsg': 5714},
        5713: {'name': 'mtl', 'description': 'Mean Tide Level', 'uncertainty': 0, 'epsg': 5713},
        
        # --- Hydraulic / River Datums ---
        # Columbia River Datum (No standard EPSG, using 0 placeholder or custom)
        0:    {'name': 'crd', 'description': 'Columbia River Datum', 'uncertainty': 0, 'epsg': 0},
        
        # IGLD 1985 (Dynamic Height)
        5609: {'name': 'IGLD85', 'description': 'International Great Lakes Datum 1985', 'uncertainty': 0, 'epsg': 5609},
        
        # IGLD Low Water Datum (Chart Datum for Lakes)
        # VDatum uses 'LWD_IGLD85' string
        9000: {'name': 'LWD_IGLD85', 'description': 'IGLD85 Low Water Datum', 'uncertainty': 0, 'epsg': 5609},
        
        # --- Legacy Vertical ---
        # NGVD29 is often best handled via VDatum (VERTCON) if PROJ isn't configured
        5702: {'name': 'NGVD29', 'description': 'National Geodetic Vertical Datum 1929', 'uncertainty': 0.05, 'epsg': 5702},
    }

    HTDP = {
        4269: {'name': 'NAD_83(2011/CORS96/2007)', 'description': '(North American plate fixed)', 'htdp_id': 1, 'uncertainty': .02, 'epoch': 1997.0},
        6781: {'name': 'NAD_83(2011/CORS96/2007)', 'description': '(North American plate fixed)', 'htdp_id': 1, 'uncertainty': .02, 'epoch': 1997.0},
        6319: {'name': 'NAD_83(2011/CORS96/2007)', 'description': '(North American plate fixed)', 'htdp_id': 1, 'uncertainty': .02, 'epoch': 1997.0},
        6321: {'name': 'NAD_83(PA11/PACP00)', 'description': '(Pacific plate fixed)', 'htdp_id': 2, 'uncertainty': .02, 'epoch': 1997.0},
        6324: {'name': 'NAD_83(MA11/MARP00)', 'description': '(Mariana plate fixed)', 'htdp_id': 3, 'uncertainty': .02, 'epoch': 1997.0},
        4979: {'name': 'WGS_84(original)', 'description': '(NAD_83(2011) used)', 'htdp_id': 4, 'uncertainty': 0, 'epoch': 1997.0},
        7815: {'name': 'WGS_84(original)', 'description': '(NAD_83(2011) used)', 'htdp_id': 4, 'uncertainty': 0, 'epoch': 1997.0},
        7816: {'name': 'WGS_84(original)', 'description': '(NAD_83(2011) used)', 'htdp_id': 4, 'uncertainty': 0, 'epoch': 1997.0},
        7656: {'name': 'WGS_84(G730)', 'description': '(ITRF91 used)', 'htdp_id': 5, 'uncertainty': 0, 'epoch': 1997.0},
        7657: {'name': 'WGS_84(G730)', 'description': '(ITRF91 used)', 'htdp_id': 5, 'uncertainty': 0, 'epoch': 1997.0},
        7658: {'name': 'WGS_84(G873)', 'description': '(ITRF94 used)', 'htdp_id': 6, 'uncertainty': 0, 'epoch': 1997.0},
        7659: {'name': 'WGS_84(G873)', 'description': '(ITRF94 used)', 'htdp_id': 6, 'uncertainty': 0, 'epoch': 1997.0},
        7660: {'name': 'WGS_84(G1150)', 'description': '(ITRF2000 used)', 'htdp_id': 7, 'uncertainty': 0, 'epoch': 1997.0},
        7661: {'name': 'WGS_84(G1150)', 'description': '(ITRF2000 used)', 'htdp_id': 7, 'uncertainty': 0, 'epoch': 1997.0},
        7662: {'name': 'WGS_84(G1674)', 'description': '(ITRF2008 used)', 'htdp_id': 8, 'uncertainty': 0, 'epoch': 2000.0},
        7663: {'name': 'WGS_84(G1674)', 'description': '(ITRF2008 used)', 'htdp_id': 8, 'uncertainty': 0, 'epoch': 2000.0},
        7664: {'name': 'WGS_84(G1762)', 'description': '(IGb08 used)', 'htdp_id': 9, 'uncertainty': 0, 'epoch': 2000.0},
        7665: {'name': 'WGS_84(G1762)', 'description': '(IGb08 used)', 'htdp_id': 9, 'uncertainty': 0, 'epoch': 2000.0},
        7666: {'name': 'WGS_84(G2139)', 'description': '(ITRF2014=IGS14=IGb14 used)', 'htdp_id': 10, 'uncertainty': 0, 'epoch': 1997.0},
        7667: {'name': 'WGS_84(G2139)', 'description': '(ITRF2014=IGS14=IGb14 used)', 'htdp_id': 10, 'uncertainty': 0, 'epoch': 1997.0},
        4910: {'name': 'ITRF88', 'description': '', 'htdp_id': 11, 'uncertainty': 0, 'epoch': 1988.0},
        4911: {'name': 'ITRF89', 'description': '', 'htdp_id': 12, 'uncertainty': 0, 'epoch': 1988.0},
        7901: {'name': 'ITRF89', 'description': '', 'htdp_id': 12, 'uncertainty': 0, 'epoch': 1988.0},
        7902: {'name': 'ITRF90', 'description': '(PNEOS90/NEOS90)', 'htdp_id': 13, 'uncertainty': 0, 'epoch': 1988.0},
        7903: {'name': 'ITRF91', 'description': '', 'htdp_id': 14, 'uncertainty': 0, 'epoch': 1988.0},
        7904: {'name': 'ITRF92', 'description': '', 'htdp_id': 15, 'uncertainty': 0, 'epoch': 1988.0},
        7905: {'name': 'ITRF93', 'description': '', 'htdp_id': 16, 'uncertainty': 0, 'epoch': 1988.0},
        7906: {'name': 'ITRF94', 'description': '', 'htdp_id': 17, 'uncertainty': 0, 'epoch': 1988.0},
        7907: {'name': 'ITRF96', 'description': '', 'htdp_id': 18, 'uncertainty': 0, 'epoch': 1996.0},
        7908: {'name': 'ITRF97', 'description': 'IGS97', 'htdp_id': 19, 'uncertainty': 0, 'epoch': 1997.0},
        7909: {'name': 'ITRF2000', 'description': 'IGS00/IGb00', 'htdp_id': 20, 'uncertainty': 0, 'epoch': 2000.0},
        7910: {'name': 'ITRF2005', 'description': 'IGS05', 'htdp_id': 21, 'uncertainty': 0, 'epoch': 2000.0},
        7911: {'name': 'ITRF2008', 'description': 'IGS08/IGb08', 'htdp_id': 22, 'uncertainty': 0, 'epoch': 2000.0},
        7912: {'name': 'ELLIPSOID', 'description': 'IGS14/IGb14/WGS84/ITRF2014 Ellipsoid', 'htdp_id': 23, 'uncertainty': 0, 'epoch': 2000.0},
        1322: {'name': 'ITRF2020', 'description': 'IGS20', 'htdp_id': 24, 'uncertainty': 0, 'epoch': 2000.0},
        
    }

    CDN = {
        # NAVD88 is tied to NAD83(2011) -> EPSG:6319
        5703: {'name': 'NAVD88 height', 'uncertainty': .05, 'default_geoid': 'g2018', 'ellipsoid': 6319, 'shifts': {7662: 'vertcon'}},
        6360: {'name': 'NAVD88 height (usFt)', 'uncertainty': .05, 'default_geoid': 'g2018', 'ellipsoid': 6319},
        8228: {'name': 'NAVD88 height (Ft)', 'uncertainty': .05, 'default_geoid': 'g2018', 'ellipsoid': 6319},
        
        # PRVD02 is tied to NAD83(2011) -> EPSG:6319 (for Puerto Rico)
        6641: {'name': 'PRVD02 height', 'uncertainty': 0, 'ellipsoid': 6319},
        
        # CGVD2013 is tied to NAD83(CSRS) -> EPSG:4617 or generally NAD83(2011) for compatibility
        9245: {'name': 'CGVD2013(CGG2013a) height', 'uncertainty': 0, 'ellipsoid': 6319},
        6647: {'name': 'CGVD2013(CGG2013) height', 'uncertainty': 0, 'ellipsoid': 6319},
        
        3855: {'name': 'EGM2008 height', 'uncertainty': 0},
        5773: {'name': 'EGM96 height', 'uncertainty': 0},
        
        6644: {'name': 'GUVD04 height', 'uncertainty': 0},
        6643: {'name': 'ASVD02 height', 'uncertainty': 0},
        9279: {'name': 'SA LLD height', 'uncertainty': 0},
        5702: {'name': 'NGVD29 height', 'uncertainty': .05, 'ellipsoid': 4267, 'shifts': {5703: 'vertcon'}},
    }

    GEOIDS = {
        # Standard PROJ-CDN Geoids (Default provider is 'proj')
        'g2018':   {'name': 'geoid 2018', 'uncertainty': .0127, 'provider': 'proj'},
        'g2012b':  {'name': 'geoid 2012b', 'uncertainty': .017,  'provider': 'proj'},
        'geoid09': {'name': 'geoid 2009', 'uncertainty': .05,   'provider': 'proj'},
        
        # New XGEOIDs via VDatum (Provider is 'vdatum')
        'xgeoid20b': {'name': 'xgeoid20b', 'uncertainty': .02, 'provider': 'vdatum'},
        'xgeoid19b': {'name': 'xgeoid19b', 'uncertainty': .02, 'provider': 'vdatum'},
    }

    @classmethod
    def get_default_geoid(cls, epsg):
        """Return default geoid for a generic CDN EPSG, or None."""
        
        if epsg in cls.CDN:
            return cls.CDN[epsg].get('default_geoid')
        return None

    
    @classmethod
    def get_vdatum_by_name(cls, datum_name):
        """Return the vertical datum EPSG based on the vertical datum name."""
        
        if datum_name is None:
            return None
        
        try:
            datum_int = int(datum_name)
        except (ValueError, TypeError):
            datum_int = None
        
        for frame_set in [cls.SURFACES, cls.HTDP, cls.CDN]:
            if datum_int in frame_set:
                return datum_int
            
            for epsg, info in frame_set.items():
                if str(datum_name).lower() in info['name'].lower():
                    return epsg
        
        return None

    
    @classmethod
    def get_frame_type(cls, epsg):
        """Identify which frame set an EPSG belongs to."""
        
        if epsg in cls.SURFACES:
            return 'surface'
        if epsg in cls.HTDP:
            return 'htdp'
        if epsg in cls.CDN:
            return 'cdn'
        return None
