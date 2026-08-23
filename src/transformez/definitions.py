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

from typing import Any, Dict, Optional, Union
import logging

logger = logging.getLogger(__name__)


class Datums:
    """Class to manage vertical datum definitions and lookups."""

    # =========================================================================
    # Unit Conversions (Multiplier to convert TO meters)
    # =========================================================================
    UNITS = {
        "m": 1.0,
        "meter": 1.0,
        "meters": 1.0,
        "ft": 0.3048,  # International Foot
        "foot": 0.3048,
        "us-ft": 1200.0 / 3937.0,  # US Survey Foot
        "us-foot": 1200.0 / 3937.0,
    }

    @classmethod
    def get_unit_factor(cls, unit_str: str) -> float:
        """Get conversion factor from unit string to meters.

        Args:
            unit_str: Unit identifier (e.g., 'm', 'ft', 'us-ft').

        Returns:
            Multiplier to convert to meters. Defaults to 1.0 if unknown.
        """

        if not unit_str:
            return 1.0
        return cls.UNITS.get(unit_str.lower(), 1.0)

    # =========================================================================
    # Vertical Datum References
    # =========================================================================
    SURFACES: Dict[int, Dict[str, Any]] = {
        # --- Tidal Datums ---
        1089: {"name": "mllw", "description": "Mean Lower Low Water", "region": "usa"},
        5866: {"name": "mllw", "description": "Mean Lower Low Water", "region": "usa"},
        1091: {"name": "mlw", "description": "Mean Low Water", "region": "usa"},
        5869: {
            "name": "mhhw",
            "description": "Mean Higher High Water",
            "region": "usa",
        },
        5868: {"name": "mhw", "description": "Mean High Water", "region": "usa"},
        5714: {"name": "msl", "description": "Mean Sea Level", "region": "usa"},
        5713: {"name": "mtl", "description": "Mean Tide Level", "region": "usa"},
        # --- Hydraulic / River Datums ---
        # Columbia River Datum (No standard EPSG, using 0 placeholder or custom)
        0: {
            "name": "crd",
            "description": "Columbia River Datum",
            "uncertainty": 0,
            "epsg": 0,
            "region": "usa",
        },
        # IGLD 1985 (Dynamic Height)
        5609: {
            "name": "IGLD85",
            "description": "International Great Lakes Datum 1985",
            "uncertainty": 0,
            "epsg": 5609,
            "region": "usa",
        },
        # IGLD Low Water Datum (Chart Datum for Lakes)
        # VDatum uses 'LWD_IGLD85' string
        9000: {
            "name": "LWD_IGLD85",
            "description": "IGLD85 Low Water Datum",
            "uncertainty": 0,
            "epsg": 5609,
            "region": "usa",
        },
        # --- Legacy Vertical ---
        # NGVD29 is often best handled via VDatum (VERTCON) if PROJ isn't configured
        5702: {
            "name": "NGVD29",
            "description": "National Geodetic Vertical Datum 1929",
            "uncertainty": 0.05,
            "epsg": 5702,
        },
        # --- Global Tidal Datums (DTU/FES) ---
        # Using pseudo-EPSG codes or negative placeholders for custom logic
        9001: {
            "name": "lat",
            "description": "Lowest Astronomical Tide",
            "region": "global",
        },
        9002: {
            "name": "hat",
            "description": "Highest Astronomical Tide",
            "region": "global",
        },
        9003: {"name": "mss", "description": "Mean Sea Surface", "region": "global"},
    }

    GLOBAL_ALIASES: Dict[str, Any] = {
        "mllw": "lat",  # Mean Lower Low Water -> Lowest Astronomical Tide
        "mlw": "lat",  # Mean Low Water       -> LAT (Conservative)
        "mhhw": "hat",  # Mean Higher High Water -> Highest Astronomical Tide
        "mhw": "hat",  # Mean High Water        -> HAT (Conservative)
        "msl": "mss",  # Mean Sea Level         -> Mean Sea Surface
        "mtl": "mss",  # Mean Tide Level        -> MSS
        "dtl": "mss",  # Diurnal Tide Level     -> MSS
    }

    HTDP: Dict[int, Dict[str, Any]] = {
        4269: {
            "name": "NAD_83(2011/CORS96/2007)",
            "description": "(North American plate fixed)",
            "htdp_id": 1,
            "uncertainty": 0.02,
            "epoch": 1997.0,
        },
        6781: {
            "name": "NAD_83(2011/CORS96/2007)",
            "description": "(North American plate fixed)",
            "htdp_id": 1,
            "uncertainty": 0.02,
            "epoch": 1997.0,
        },
        6319: {
            "name": "NAD_83(2011/CORS96/2007)",
            "description": "(North American plate fixed)",
            "htdp_id": 1,
            "uncertainty": 0.02,
            "epoch": 1997.0,
        },
        6321: {
            "name": "NAD_83(PA11/PACP00)",
            "description": "(Pacific plate fixed)",
            "htdp_id": 2,
            "uncertainty": 0.02,
            "epoch": 1997.0,
        },
        6324: {
            "name": "NAD_83(MA11/MARP00)",
            "description": "(Mariana plate fixed)",
            "htdp_id": 3,
            "uncertainty": 0.02,
            "epoch": 1997.0,
        },
        4979: {
            "name": "WGS_84(G2139)",
            "description": "(NAD_83(2011) used)",
            "htdp_id": 10,
            "uncertainty": 0,
            "epoch": 2020.0,
        },
        7815: {
            "name": "WGS_84(original)",
            "description": "(NAD_83(2011) used)",
            "htdp_id": 4,
            "uncertainty": 0,
            "epoch": 1997.0,
        },
        7816: {
            "name": "WGS_84(original)",
            "description": "(NAD_83(2011) used)",
            "htdp_id": 4,
            "uncertainty": 0,
            "epoch": 1997.0,
        },
        7656: {
            "name": "WGS_84(G730)",
            "description": "(ITRF91 used)",
            "htdp_id": 5,
            "uncertainty": 0,
            "epoch": 1997.0,
        },
        7657: {
            "name": "WGS_84(G730)",
            "description": "(ITRF91 used)",
            "htdp_id": 5,
            "uncertainty": 0,
            "epoch": 1997.0,
        },
        7658: {
            "name": "WGS_84(G873)",
            "description": "(ITRF94 used)",
            "htdp_id": 6,
            "uncertainty": 0,
            "epoch": 1997.0,
        },
        7659: {
            "name": "WGS_84(G873)",
            "description": "(ITRF94 used)",
            "htdp_id": 6,
            "uncertainty": 0,
            "epoch": 1997.0,
        },
        7660: {
            "name": "WGS_84(G1150)",
            "description": "(ITRF2000 used)",
            "htdp_id": 7,
            "uncertainty": 0,
            "epoch": 1997.0,
        },
        7661: {
            "name": "WGS_84(G1150)",
            "description": "(ITRF2000 used)",
            "htdp_id": 7,
            "uncertainty": 0,
            "epoch": 1997.0,
        },
        7662: {
            "name": "WGS_84(G1674)",
            "description": "(ITRF2008 used)",
            "htdp_id": 8,
            "uncertainty": 0,
            "epoch": 2000.0,
        },
        7663: {
            "name": "WGS_84(G1674)",
            "description": "(ITRF2008 used)",
            "htdp_id": 8,
            "uncertainty": 0,
            "epoch": 2000.0,
        },
        7664: {
            "name": "WGS_84(G1762)",
            "description": "(IGb08 used)",
            "htdp_id": 9,
            "uncertainty": 0,
            "epoch": 2000.0,
        },
        7665: {
            "name": "WGS_84(G1762)",
            "description": "(IGb08 used)",
            "htdp_id": 9,
            "uncertainty": 0,
            "epoch": 2000.0,
        },
        7666: {
            "name": "WGS_84(G2139)",
            "description": "(ITRF2014=IGS14=IGb14 used)",
            "htdp_id": 10,
            "uncertainty": 0,
            "epoch": 1997.0,
        },
        7667: {
            "name": "WGS_84(G2139)",
            "description": "(ITRF2014=IGS14=IGb14 used)",
            "htdp_id": 10,
            "uncertainty": 0,
            "epoch": 1997.0,
        },
        4910: {
            "name": "ITRF88",
            "description": "",
            "htdp_id": 11,
            "uncertainty": 0,
            "epoch": 1988.0,
        },
        4911: {
            "name": "ITRF89",
            "description": "",
            "htdp_id": 12,
            "uncertainty": 0,
            "epoch": 1988.0,
        },
        7901: {
            "name": "ITRF89",
            "description": "",
            "htdp_id": 12,
            "uncertainty": 0,
            "epoch": 1988.0,
        },
        7902: {
            "name": "ITRF90",
            "description": "(PNEOS90/NEOS90)",
            "htdp_id": 13,
            "uncertainty": 0,
            "epoch": 1988.0,
        },
        7903: {
            "name": "ITRF91",
            "description": "",
            "htdp_id": 14,
            "uncertainty": 0,
            "epoch": 1988.0,
        },
        7904: {
            "name": "ITRF92",
            "description": "",
            "htdp_id": 15,
            "uncertainty": 0,
            "epoch": 1988.0,
        },
        7905: {
            "name": "ITRF93",
            "description": "",
            "htdp_id": 16,
            "uncertainty": 0,
            "epoch": 1988.0,
        },
        7906: {
            "name": "ITRF94",
            "description": "",
            "htdp_id": 17,
            "uncertainty": 0,
            "epoch": 1988.0,
        },
        7907: {
            "name": "ITRF96",
            "description": "",
            "htdp_id": 18,
            "uncertainty": 0,
            "epoch": 1996.0,
        },
        7908: {
            "name": "ITRF97",
            "description": "IGS97",
            "htdp_id": 19,
            "uncertainty": 0,
            "epoch": 1997.0,
        },
        7909: {
            "name": "ITRF2000",
            "description": "IGS00/IGb00",
            "htdp_id": 20,
            "uncertainty": 0,
            "epoch": 2000.0,
        },
        7910: {
            "name": "ITRF2005",
            "description": "IGS05",
            "htdp_id": 21,
            "uncertainty": 0,
            "epoch": 2000.0,
        },
        7911: {
            "name": "ITRF2008",
            "description": "IGS08/IGb08",
            "htdp_id": 22,
            "uncertainty": 0,
            "epoch": 2000.0,
        },
        7912: {
            "name": "ELLIPSOID",
            "description": "IGS14/IGb14/WGS84/ITRF2014 Ellipsoid",
            "htdp_id": 23,
            "uncertainty": 0,
            "epoch": 2000.0,
        },
        1322: {
            "name": "ITRF2020",
            "description": "IGS20",
            "htdp_id": 24,
            "uncertainty": 0,
            "epoch": 2000.0,
        },
    }

    CDN: Dict[int, Dict[str, Any]] = {
        # CONUS / Alaska / Hawaii / PR / VI
        5703: {
            "name": "NAVD88 height",
            "vdatum_id": "navd88:m:height",
            "default_geoid": "g2018",
            "ellipsoid": 6319,
        },
        6360: {"name": "NAVD88 height (usFt)", "default_geoid": "g2018"},
        8228: {
            "name": "NAVD88 height (Ft)",
            "default_geoid": "g2012b",
            "z_unit": "us-ft",
        },
        # Puerto Rico
        6641: {
            "name": "PRVD02 height",
            "vdatum_id": "prvd02:m:height",
            "default_geoid": "g2018",
            "ellipsoid": 6319,
        },
        # Virgin Islands
        6642: {
            "name": "VIVD09 height",
            "vdatum_id": "vivd09:m:height",
            "default_geoid": "g2018",
            "ellipsoid": 6319,
        },
        # Canada (CGVD2013 uses CGG2013 geoid)
        # Note: You need to ensure 'CGG2013' is fetchable via your fetcher or map it to a filename
        6647: {
            "name": "CGVD2013(CGG2013)",
            "vdatum_id": "cgvd2013:m:height",
            "default_geoid": "CGG2013",
        },
        # Global EGM
        3855: {
            "name": "EGM2008 height",
            "vdatum_id": "egm2008:m:height",
            "default_geoid": "egm2008",
            "ellipsoid": 4979,
        },
        5773: {
            "name": "EGM96 height",
            "vdatum_id": "egm96:m:height",
            "default_geoid": "egm96",
            "ellipsoid": 4979,
        },
        # # Ellipsoidal (Hubs) - No Geoid needed
        # 6319: {'name': 'NAD83(2011)', 'vdatum_id': 'nad83_2011:m:height'},
        # 4979: {'name': 'WGS84', 'vdatum_id': 'wgs84:m:height'},
    }

    GEOIDS: Dict[str, Dict[str, Any]] = {
        # Standard PROJ-CDN Geoids (Default provider is 'proj')
        "g2018": {"name": "geoid 2018", "uncertainty": 0.0127, "provider": "proj"},
        "g2012b": {"name": "geoid 2012b", "uncertainty": 0.017, "provider": "proj"},
        "geoid09": {"name": "geoid 2009", "uncertainty": 0.05, "provider": "proj"},
        # New XGEOIDs via VDatum (Provider is 'vdatum')
        "xgeoid20b": {"name": "xgeoid20b", "uncertainty": 0.02, "provider": "vdatum"},
        "xgeoid19b": {"name": "xgeoid19b", "uncertainty": 0.02, "provider": "vdatum"},
        "egm2008": {"name": "EGM2008", "uncertainty": 0, "provider": "proj"},
        "egm96": {"name": "EGM96", "uncertainty": 0, "provider": "proj"},
        "CGG2013": {"name": "CGG2013", "uncertainty": 0.01, "provider": "proj"},
    }

    MODELS: Dict[str, Dict[str, Any]] = {
        "fes2014": {"provider": "seanoe", "grids": {"lat": "lat", "mss": "msl"}},
        "dtu25": {"provider": "transformez.dtu", "grids": {"mss": "mss25"}},
        "egm2008": {"provider": "proj", "grid": "egm2008"},
    }

    @classmethod
    def get_unit(cls, epsg: Optional[Union[int, str]]) -> str:
        """Retrieves the Z-unit for a given EPSG code, defaulting to meters.

        Args:
            epsg: EPSG code (integer or string representation).

        Returns:
            Unit string ('m', 'ft', 'us-ft', etc.).
        """

        if not epsg:
            return "m"

        try:
            epsg_int = int(epsg)
        except (ValueError, TypeError):
            return "m"

        if epsg_int in cls.CDN:
            return cls.CDN[epsg_int].get("z_unit", "m")

        if epsg_int in cls.SURFACES:
            return cls.SURFACES[epsg_int].get("z_unit", "m")

        return "m"

    @classmethod
    def get_vdatum_by_name(
        cls,
        datum_name: str,
        region_check: Optional[bool] = None,
    ) -> Optional[int]:
        """Return the datum ID by name.

        Args:
            datum_name: The requested datum (e.g., 'mllw', '5703').
            region_check: If True, considers regional datums differently.

        Returns:
            EPSG code as integer, or None if not found.
        """

        if not datum_name:
            return None

        try:
            return int(datum_name)
        except ValueError:
            pass

        s_name = str(datum_name).lower()

        # Direct Match (e.g. 'mllw' -> 5866)
        for epsg, info in cls.SURFACES.items():
            if s_name == info["name"]:
                return epsg

        # We should check for aliases here
        return None

    @classmethod
    def get_global_proxy(cls, datum_name: str) -> Optional[str]:
        """Returns the Global Model equivalent name (e.g. 'mllw' -> 'lat').

        Args:
            datum_name: Datum name or EPSG code string.

        Returns:
            Global proxy name (e.g., 'lat', 'hat', 'mss'), or None.
        """

        s_name = str(datum_name).lower()

        if s_name in ["lat", "hat", "mss"]:
            return s_name

        for epsg, info in cls.SURFACES.items():
            if str(epsg) == s_name:
                s_name = info["name"]
                break

        return cls.GLOBAL_ALIASES.get(s_name)

    @classmethod
    def get_frame_type(cls, epsg: Optional[Union[int, str]]) -> Optional[str]:
        """Identify frame set (Surface, HTDP, CDN).

        Args:
            epsg: EPSG code.

        Returns:
            Frame type string ('surface', 'htdp', 'cdn', 'global_tidal') or None.
        """

        if epsg is None:
            return None

        try:
            epsg_int = int(epsg)
        except (ValueError, TypeError):
            return None

        if epsg_int in cls.SURFACES:
            # Distinguish between NOAA VDatum and Global
            if cls.SURFACES[epsg_int].get("region") == "global":
                return "global_tidal"
            return "surface"

        if epsg_int in cls.HTDP:
            return "htdp"

        if epsg_int in cls.CDN:
            return "cdn"

        return None

    @classmethod
    def get_default_geoid(cls, epsg: Optional[Union[int, str]]) -> Optional[str]:
        """Return default geoid for a generic CDN EPSG, or None.

        Args:
            epsg: EPSG code.

        Returns:
            Geoid name string, or None if not applicable.
        """

        if epsg is None:
            return None

        try:
            e_int = int(epsg)
        except Exception:
            return None

        if e_int in cls.CDN:
            return cls.CDN[e_int].get("default_geoid")
        return None

    @classmethod
    def get_vdatum_id(cls, epsg: Optional[Union[int, str]]) -> Optional[str]:
        """Retrieve the NOAA VDatum CLI string for an EPSG.

        Args:
            epsg: EPSG code.

        Returns:
            VDatum CLI string (e.g., 'navd88:m:height'), or None.
        """

        if epsg is None:
            return None

        try:
            epsg_int = int(epsg)
        except (ValueError, TypeError):
            return None

        if epsg_int in cls.SURFACES:
            return cls.SURFACES[epsg_int].get("vdatum_id")

        if epsg_int in cls.CDN:
            return cls.CDN[epsg_int].get("vdatum_id")

        if epsg_int == 6319:
            return "nad83_2011:m:height"

        return None
