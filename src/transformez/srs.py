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
import hashlib
import logging
from typing import Any, Dict, Optional, Tuple

from pyproj import CRS, Transformer
import numpy as np
from rasterio.warp import reproject, Resampling, calculate_default_transform
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

    @staticmethod
    def _vertical_grid_region_crs(region):
        """Return the CRS of the supplied processing region.

        Fetchez/Globato processing regions are geographic and commonly arrive
        without an explicit ``Region.srs`` label. Treat an unlabeled processing
        region as WGS84 rather than relabeling its longitude/latitude numbers as
        the source file CRS. Callers using a non-WGS84 region must label it.
        """
        region_srs = getattr(region, "srs", None)
        if isinstance(region_srs, (list, tuple)) and len(region_srs) == 1:
            region_srs = region_srs[0]
        return CRS.from_user_input(region_srs or "EPSG:4326")

    @classmethod
    def _vertical_grid_wgs84_region(cls, region):
        """Return a copy of ``region`` expressed in WGS84."""
        working = region.copy()
        region_crs = cls._vertical_grid_region_crs(working)
        working.srs = region_crs
        if region_crs != CRS.from_epsg(4326):
            working.warp("EPSG:4326")
        return working

    @staticmethod
    def _align_vertical_grid_to_source_crs(shift_arr, vt_region, source_crs):
        """Return a shift grid whose pixel coordinates match source x/y coordinates.

        VerticalTransform evaluates its models on a WGS84 grid. Point-stream
        consumers query the cached result before horizontal reprojection, so the
        stored grid must be expressed in the exact source horizontal CRS.
        """
        wgs84 = CRS.from_epsg(4326)
        source_crs = CRS.from_user_input(source_crs)
        rows, cols = shift_arr.shape
        wgs_transform = from_bounds(
            vt_region.xmin,
            vt_region.ymin,
            vt_region.xmax,
            vt_region.ymax,
            cols,
            rows,
        )
        source_data = np.asarray(shift_arr, dtype=np.float32)
        if source_crs == wgs84:
            return source_data, wgs_transform, source_crs

        native_transform, native_width, native_height = calculate_default_transform(
            wgs84,
            source_crs,
            cols,
            rows,
            left=vt_region.xmin,
            bottom=vt_region.ymin,
            right=vt_region.xmax,
            top=vt_region.ymax,
        )
        if native_width < 1 or native_height < 1:
            raise RuntimeError(
                "Could not derive a valid source-CRS vertical-grid shape for "
                f"{source_crs.to_string()}"
            )

        native_shift_array = np.full(
            (native_height, native_width), np.nan, dtype=np.float32
        )
        reproject(
            source=source_data,
            destination=native_shift_array,
            src_transform=wgs_transform,
            src_crs=wgs84,
            src_nodata=np.nan,
            dst_transform=native_transform,
            dst_crs=source_crs,
            dst_nodata=np.nan,
            resampling=Resampling.bilinear,
            init_dest_nodata=True,
        )
        if not np.isfinite(native_shift_array).any():
            raise RuntimeError(
                "Vertical-grid reprojection produced no finite source-CRS coverage for "
                f"{source_crs.to_string()}"
            )
        return native_shift_array, native_transform, source_crs

    @staticmethod
    def _vertical_grid_crs_cache_key(crs):
        """Return a collision-resistant canonical CRS identity for cache keys."""
        if isinstance(crs, (list, tuple)) and len(crs) == 1:
            crs = crs[0]
        return CRS.from_user_input(crs).to_wkt()

    def _vertical_grid_cache_token(self, proc_region, s_ident, d_ident):
        """Return a stable token for one natively aligned vertical-shift grid."""
        src_crs_key = self._vertical_grid_crs_cache_key(self.tc["src_crs"])
        # Fetchez/Globato processing regions are geographic and may be unlabeled.
        # Do not relabel longitude/latitude bounds as a projected source CRS.
        effective_region_srs = getattr(proc_region, "srs", None) or "EPSG:4326"
        region_crs_key = self._vertical_grid_crs_cache_key(effective_region_srs)
        parts = [
            "vertical-grid-cache-v3",
            src_crs_key,
            region_crs_key,
            str(s_ident),
            str(d_ident),
            str(self.tc["src_geoid"] or ""),
            str(self.tc["dst_geoid"] or ""),
            format(float(proc_region.xmin), ".17g"),
            format(float(proc_region.xmax), ".17g"),
            format(float(proc_region.ymin), ".17g"),
            format(float(proc_region.ymax), ".17g"),
        ]
        payload = "\x1f".join(parts).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:16]

    def _vertical_grid_name(self, proc_region, s_ident, d_ident):
        """Return the cache filename for one generated vertical-shift grid."""
        s_name = str(s_ident).replace(":", "_").replace(" ", "_").replace("/", "_")
        d_name = str(d_ident).replace(":", "_").replace(" ", "_").replace("/", "_")
        grid_token = self._vertical_grid_cache_token(proc_region, s_ident, d_ident)
        return (
            f"transformez_{s_name}_{d_name}_{proc_region.format('fn')}_{grid_token}.tif"
        )

    def set_vertical_transform(self) -> None:
        """Generate a cached vertical-shift grid aligned to source query coordinates."""
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

        # Keep the legacy filename block here so the independent cache-identity
        # experiment can compose on top of this alignment correction.
        grid_name = self._vertical_grid_name(proc_region, s_ident, d_ident)
        self.tc["trans_fn"] = grid_name.replace("\\", "/")

        if not os.path.exists(self.tc["trans_fn"]):
            logger.info(
                f"Generating vertical grid: {s_ident} -> {d_ident} : {self.tc['trans_fn']} :"
            )
            from .transform import VerticalTransform

            # Globato/Fetchez processing regions are geographic unless explicitly
            # labeled otherwise. Convert that real region to WGS84 for the vertical
            # model instead of relabeling lon/lat bounds as the source file CRS.
            vt_region = self._vertical_grid_wgs84_region(proc_region)

            # Generate grid resolution based on WGS84 bounds (approx 3 arc-seconds).
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
            shift_arr, grid_transform, grid_crs = (
                self._align_vertical_grid_to_source_crs(
                    shift_arr, vt_region, self.tc["src_crs"]
                )
            )
            GridWriter.write(
                self.tc["trans_fn"],
                shift_arr,
                proc_region,
                crs=grid_crs,
                transform=grid_transform,
                nodata=np.nan,
            )

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
