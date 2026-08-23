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
from typing import Any, Dict, Optional, Tuple

from pyproj import CRS, Transformer
import numpy as np
from rasterio.warp import reproject, Resampling
from rasterio.transform import from_bounds

from fetchez.spatial import Region
from .definitions import Datums
from .grid_engine import GridWriter

logger = logging.getLogger(__name__)


class SRSParser:
    """Parses SRS and prepares a Decoupled Transformation:

    - Horizontal: Source -> Hub (NAD83) -> Dest
    - Vertical:   Z + Shift_Grid
    """

    def __init__(
        self,
        src_srs: str,
        dst_srs: str,
        region: Optional[Any] = None,
        vert_grid: Optional[Any] = None,
        cache_dir: str = ".",
        **kwargs: Any,
    ):
        self.src_srs_input = src_srs
        self.dst_srs_input = dst_srs
        self.region = region
        self.manual_vert_grid = vert_grid
        self.cache_dir = cache_dir

        self.tc: Dict[str, Any] = {
            "src_crs": None,
            "dst_crs": None,
            "src_vert_epsg": None,
            "dst_vert_epsg": None,
            "src_geoid": None,
            "dst_geoid": None,
            "want_vertical": False,
            "trans_fn": None,
        }

        self._parse_srs()

    def _extract_geoid(self, srs_str: str) -> Tuple[str, Optional[str]]:
        """Extract geoid from SRS string."""

        parts = str(srs_str).split("+geoid:")
        return parts[0], (parts[1] if len(parts) > 1 else None)

    def _extract_vertical(self, srs_str: str) -> Tuple[str, Optional[str | int]]:
        """Extract vertical component from SRS string."""

        if "+" in srs_str:
            horz_str, vert_str = srs_str.rsplit("+", 1)
            try:
                if "EPSG" in vert_str.upper():
                    vert_str = vert_str.split(":")[-1]
                return horz_str, int(vert_str)
            except Exception as e:
                logger.debug(f"Failed to build compound CRS from '{srs_str}': {e}")
                return srs_str, None
        return srs_str, None

    def _get_epsg_int(self, crs: Optional[CRS]) -> Optional[int]:
        """Extract EPSG integer from a CRS."""

        if crs is None:
            return None
        try:
            return crs.to_epsg()
        except Exception:
            return None

    def _parse_srs(self) -> None:
        """Parse source and destination SRS strings."""

        clean_src, self.tc["src_geoid"] = self._extract_geoid(self.src_srs_input)
        clean_dst, self.tc["dst_geoid"] = self._extract_geoid(self.dst_srs_input)

        try:
            self.tc["src_crs"] = CRS.from_user_input(clean_src)
            self.tc["dst_crs"] = CRS.from_user_input(clean_dst)
            vert_epsg_src = None
            vert_epsg_dst = None
        except Exception:
            clean_src, vert_epsg_src = self._extract_vertical(self.src_srs_input)
            clean_dst, vert_epsg_dst = self._extract_vertical(self.dst_srs_input)

            try:
                self.tc["src_crs"] = CRS.from_user_input(clean_src)
                self.tc["dst_crs"] = CRS.from_user_input(clean_dst)
            except Exception as e:
                logger.error(f"Invalid SRS: {e}")
                return

        # Extract vertical components before flattening
        if self.tc["src_crs"].is_compound:
            self.tc["src_vert_epsg"] = self._get_epsg_int(
                self.tc["src_crs"].sub_crs_list[1]
            )
            # Strip to Horizontal for PROJ Transformer
            self.tc["src_crs"] = self.tc["src_crs"].sub_crs_list[0]
        elif self.tc["src_crs"].is_vertical:
            self.tc["src_vert_epsg"] = self._get_epsg_int(self.tc["src_crs"])

        if self.tc["dst_crs"].is_compound:
            self.tc["dst_vert_epsg"] = self._get_epsg_int(
                self.tc["dst_crs"].sub_crs_list[1]
            )
            self.tc["dst_crs"] = self.tc["dst_crs"].sub_crs_list[0]
        elif self.tc["dst_crs"].is_vertical:
            self.tc["dst_vert_epsg"] = self._get_epsg_int(self.tc["dst_crs"])

        if self.tc["src_vert_epsg"] is None:
            if vert_epsg_src is None:
                _, vert_epsg_src = self._extract_vertical(self.src_srs_input)
            self.tc["src_vert_epsg"] = vert_epsg_src
        if self.tc["dst_vert_epsg"] is None:
            if vert_epsg_dst is None:
                _, vert_epsg_dst = self._extract_vertical(self.dst_srs_input)
            self.tc["dst_vert_epsg"] = vert_epsg_dst

        # Lookup default geoids
        # If we have a vertical EPSG but no manual geoid, look it up in definitions.py
        if self.tc["src_vert_epsg"] and not self.tc["src_geoid"]:
            self.tc["src_geoid"] = Datums.get_default_geoid(self.tc["src_vert_epsg"])

        if self.tc["dst_vert_epsg"] and not self.tc["dst_geoid"]:
            self.tc["dst_geoid"] = Datums.get_default_geoid(self.tc["dst_vert_epsg"])

        # We want vertical if we have explicit vertical EPSGs OR manual geoids
        has_src_vert = (self.tc["src_vert_epsg"] is not None) or (
            self.tc["src_geoid"] is not None
        )
        has_dst_vert = (self.tc["dst_vert_epsg"] is not None) or (
            self.tc["dst_geoid"] is not None
        )

        self.tc["want_vertical"] = has_src_vert or has_dst_vert

    def set_vertical_transform(self) -> None:
        """Generates the vertical shift grid using VerticalTransform."""

        if not self.region or not self.tc["want_vertical"]:
            return

        try:
            proc_region = self.region.copy()
            proc_region.buffer(pct=5)
        except AttributeError:
            proc_region = Region.from_list(self.region)
            proc_region.buffer(pct=5)

        s_ident = self.tc["src_vert_epsg"]
        d_ident = self.tc["dst_vert_epsg"]

        if not s_ident and self.tc["src_geoid"]:
            s_ident = 6319
        if not d_ident and self.tc["dst_geoid"]:
            d_ident = 6319

        if not s_ident or not d_ident:
            return

        s_name = str(s_ident).replace(":", "_").replace(" ", "_").replace("/", "_")
        d_name = str(d_ident).replace(":", "_").replace(" ", "_").replace("/", "_")
        grid_name = f"transformez_{s_name}_{d_name}_{proc_region.format('fn')}.tif"
        self.tc["trans_fn"] = grid_name.replace("\\", "/")

        if not os.path.exists(self.tc["trans_fn"]):
            logger.info(
                f"Generating vertical grid: {s_ident} -> {d_ident} : {self.tc['trans_fn']} :"
            )

            from .transform import VerticalTransform

            # Determine Native WGS84 Region for Transformez
            src_is_projected = self.tc["src_crs"].is_projected
            if not proc_region.srs:
                proc_region.srs = (self.tc["src_crs"],)

            if src_is_projected:
                # Transform the native bounding box to WGS84 to query the shift models
                vt_region = proc_region.copy()
                vt_region.warp("EPSG:4326")
            else:
                vt_region = proc_region.copy()

            # Generate grid resolution based on WGS84 bounds (approx 3 arc-seconds)
            inc_deg = 3.0 / 3600.0
            vt_nx = max(10, int(vt_region.width / inc_deg))
            vt_ny = max(10, int(vt_region.height / inc_deg))

            vt = VerticalTransform(
                vt_region,
                nx=vt_nx,
                ny=vt_ny,
                epsg_in=s_ident,
                epsg_out=d_ident,
                geoid_in=self.tc["src_geoid"],
                geoid_out=self.tc["dst_geoid"],
                cache_dir=self.cache_dir,
            )
            shift_arr, _ = vt._vertical_transform()

            # Warp the Grid Back to the Source CRS
            if src_is_projected:
                logger.info(
                    f"Warping shift grid to native input CRS ({self.tc['src_crs'].name})..."
                )
                wgs_transform = from_bounds(
                    vt_region.xmin,
                    vt_region.ymin,
                    vt_region.xmax,
                    vt_region.ymax,
                    vt_nx,
                    vt_ny,
                )

                # Output grid dimensions for the native projection
                out_nx = max(10, int(proc_region.width / (proc_region.width / vt_nx)))
                out_ny = max(10, int(proc_region.height / (proc_region.height / vt_ny)))
                native_transform = from_bounds(
                    proc_region.xmin,
                    proc_region.ymin,
                    proc_region.xmax,
                    proc_region.ymax,
                    out_nx,
                    out_ny,
                )

                native_shift_array = np.zeros((out_ny, out_nx), dtype=np.float32)

                reproject(
                    source=shift_arr,
                    destination=native_shift_array,
                    src_transform=wgs_transform,
                    src_crs="EPSG:4326",
                    dst_transform=native_transform,
                    dst_crs=self.tc["src_crs"],
                    resampling=Resampling.bilinear,
                )
                shift_arr = native_shift_array

                # We artificially inject the native transform into proc_region to satisfy GridWriter
                proc_region.transform = native_transform

            # Write the natively-aligned grid to disk!
            GridWriter.write(self.tc["trans_fn"], shift_arr, proc_region)

        self.manual_vert_grid = self.tc["trans_fn"]

    def get_components(self) -> Tuple[Transformer, Optional[str]]:
        """Returns the components: Transformer and Grid Path.

        Returns:
            Tuple of (horizontal_transformer, vertical_grid_path).
        """

        if self.tc["want_vertical"] and not self.manual_vert_grid:
            self.set_vertical_transform()

        horz_transformer = Transformer.from_crs(
            self.tc["src_crs"],
            self.tc["dst_crs"],
            always_xy=True,  # type: ignore[arg-type]
        )

        return horz_transformer, self.manual_vert_grid
