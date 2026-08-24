#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.transform
~~~~~~~~~~~~~

Main transformation logic.
Implements a Dynamic Hub-and-Spoke model.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import logging
import gzip
import shutil
from typing import Any, List, Optional, Tuple

import numpy as np
import fetchez.api

from .definitions import Datums
from .grid_engine import GridEngine, GridGen, GridCorruptionError

logger = logging.getLogger(__name__)

# Default Hubs
WGS84_EPSG = 4979
NAD83_EPSG = 6319


class MissingGridError(Exception):
    """Raised when a required shift grid cannot be fetched, is missing, or is persistently corrupted."""

    pass


class VerticalTransform:
    """Generate a vertical transformation grid using Transformez."""

    def __init__(
        self,
        region: Any,
        nx: int,
        ny: int,
        epsg_in: int,
        epsg_out: int,
        geoid_in: Optional[str] = None,
        geoid_out: Optional[str] = None,
        epoch_in: str = "2010.0",
        epoch_out: str = "2010.0",
        decay_pixels: int = 100,
        cache_dir: Optional[str] = None,
        use_stations: bool = False,
        verbose: bool = True,
    ):
        """Initialize VerticalTransform.

        Args:
            region: Geographic region object.
            nx: Number of pixels along x-axis.
            ny: Number of pixels along y-axis.
            epsg_in: Source EPSG code.
            epsg_out: Target EPSG code.
            geoid_in: Source geoid name (optional).
            geoid_out: Target geoid name (optional).
            epoch_in: Source epoch (decimal years).
            epoch_out: Target epoch (decimal years).
            decay_pixels: Pixels for inland extrapolation decay.
            cache_dir: Path to store downloaded grids.
            use_stations: Force RBF interpolation using live tide stations.
            verbose: Enable debug logging.
        """

        self.region = region
        self.nx = nx
        self.ny = ny
        self.cache_dir = cache_dir or os.path.join(os.getcwd(), "transformez_cache")
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
        self.verbose = verbose

        self.epsg_in = Datums.get_vdatum_by_name(str(epsg_in))
        self.epsg_out = Datums.get_vdatum_by_name(str(epsg_out))

        self.geoid_in = geoid_in or Datums.get_default_geoid(self.epsg_in)
        self.geoid_out = geoid_out or Datums.get_default_geoid(self.epsg_out)

        self.epoch_in = str(epoch_in) if epoch_in else "2010.0"
        self.epoch_out = str(epoch_out) if epoch_out else "2010.0"

        self.ref_in = Datums.get_frame_type(self.epsg_in)
        self.ref_out = Datums.get_frame_type(self.epsg_out)

        self.decay_pixels = decay_pixels
        self.use_stations = use_stations

        # --- HUB SELECTION ---
        native_in = self._get_native_ellipsoid(self.epsg_in, self.ref_in)
        native_out = self._get_native_ellipsoid(self.epsg_out, self.ref_out)

        if native_in == NAD83_EPSG and native_out == NAD83_EPSG:
            self.hub_epsg = NAD83_EPSG
            if self.verbose:
                logger.info(f"Using Native Hub: NAD83 (EPSG:{self.hub_epsg})")
        else:
            self.hub_epsg = WGS84_EPSG
            if self.verbose:
                logger.info(f"Using Global Hub: WGS84 (EPSG:{self.hub_epsg})")

    def _get_native_ellipsoid(
        self, epsg: Optional[int], ref_type: Optional[str]
    ) -> int:
        """Identify the native frame of a datum.

        Args:
            epsg: EPSG code.
            ref_type: Reference type ('surface', 'global_tidal', 'cdn', 'htdp').

        Returns:
            Native ellipsoid EPSG code.
        """

        if epsg is None or ref_type is None:
            return WGS84_EPSG

        if ref_type in ["surface", "global_tidal"]:
            region = Datums.SURFACES[epsg].get("region")
            return NAD83_EPSG if region == "usa" else WGS84_EPSG
        elif ref_type == "cdn":
            return Datums.CDN.get(epsg, {}).get("ellipsoid", NAD83_EPSG)
        elif ref_type == "htdp":
            return epsg
        return WGS84_EPSG

    def fetch_grid(self, module_name: str, **kwargs: Any) -> List[str]:
        """Generic fetcher wrapper using the new fetchez API.

        Args:
            module_name: Module name to fetch from.
            **kwargs: Additional fetcher arguments.

        Returns:
            List of valid grid file paths.
        """

        files = fetchez.api.get(
            module=module_name,
            region=self.region,
            outdir=self.cache_dir,
            threads=2,
            check_size=True,
            ignore_failures=False,
            **kwargs,
        )

        valid: List[str] = []

        for fn in files:
            if not os.path.exists(fn):
                continue

            if fn.endswith(".zip"):
                datatype = kwargs.get("datatype")
                if datatype:
                    fns_to_extract = [datatype, ".met", ".inf"]
                else:
                    fns_to_extract = None

                try:
                    extracted = fetchez.utils.p_f_unzip(
                        fn, fns=fns_to_extract, outdir=self.cache_dir
                    )
                except OSError as e:
                    if e.errno == 30 or "Read-only" in str(e):
                        logger.debug(
                            f"Read-only cache detected. Assuming {fn} is already unzipped."
                        )
                        extracted = []
                        for root, _, filenames in os.walk(self.cache_dir):
                            for f in filenames:
                                extracted.append(os.path.join(root, f))
                    else:
                        raise
                valid.extend(
                    [
                        f
                        for f in extracted
                        if f.endswith((".gtx", ".tif", ".grd", ".nc"))
                        and "unc." not in f
                    ]
                )

            elif fn.endswith(".gz"):
                try:
                    out_fn = os.path.splitext(fn)[0]
                    if not os.path.exists(out_fn):
                        logger.debug(f"Decompressing {fn}...")
                        with gzip.open(fn, "rb") as f_in:
                            with open(out_fn, "wb") as f_out:
                                shutil.copyfileobj(f_in, f_out)
                    valid.append(out_fn)
                except Exception as e:
                    logger.error(f"Failed to decompress {fn}: {e}")

            elif fn.endswith((".gtx", ".tif", ".grd", ".nc", ".mss")):
                valid.append(fn)
        return valid

    def _get_grid(self, provider: str, name: str, max_retries: int = 3) -> np.ndarray:
        """Fetch and load a grid with corruption recovery.

        Args:
            provider: Provider name (e.g., 'proj', 'vdatum').
            name: Grid name.
            max_retries: Maximum retry attempts.

        Returns:
            2D grid array.

        Raises:
            MissingGridError: If grid cannot be retrieved after retries.
        """

        if not name:
            raise MissingGridError("A valid grid name must be provided to the fetcher.")

        if not provider:
            provider = "proj"

        if "geoid=" in name:
            name = name.split("=")[1]

        for attempt in range(max_retries):
            files = self.fetch_grid(provider, datatype=name, query=name)
            if provider == "vdatum":
                import rasterio
                from datetime import datetime

                def get_vdatum_date(gtx_path: str) -> datetime:
                    """Parse release date from VDatum metadata files."""

                    dir_name = os.path.dirname(gtx_path)
                    meta_files = [
                        f for f in os.listdir(dir_name) if f.endswith((".met", ".inf"))
                    ]

                    if not meta_files:
                        return datetime(1970, 1, 1)

                    meta_path = os.path.join(dir_name, meta_files[0])
                    try:
                        with open(meta_path, "r") as f:
                            content = f.read().splitlines()

                        if not content:
                            return datetime(1970, 1, 1)

                        first_line = content[0]

                        if first_line.startswith("#"):
                            parts = first_line.replace("#", "").split()
                            if len(parts) >= 6:
                                year = int(parts[-1])
                                day = int(parts[2])
                                month_map = {
                                    "Jan": 1,
                                    "Feb": 2,
                                    "Mar": 3,
                                    "Apr": 4,
                                    "May": 5,
                                    "Jun": 6,
                                    "Jul": 7,
                                    "Aug": 8,
                                    "Sep": 9,
                                    "Oct": 10,
                                    "Nov": 11,
                                    "Dec": 12,
                                }
                                month = month_map.get(parts[1][:3].title(), 1)
                                return datetime(year, month, day)

                        for line in content:
                            if "released_date=" in line:
                                date_str = line.split("=")[1].strip()
                                m, d, y = map(int, date_str.split("/"))
                                return datetime(y, m, d)

                    except Exception as e:
                        logger.debug(f"Failed to parse date from {meta_path}: {e}")

                    return datetime(1970, 1, 1)

                def sort_key(filepath: str) -> Tuple[float, float]:
                    """Sort key for time-based ordering."""

                    date_val = get_vdatum_date(filepath)

                    try:
                        with rasterio.open(filepath) as src:
                            b = src.bounds
                            area = (b.right - b.left) * (b.top - b.bottom)
                    except Exception:
                        area = float("inf")

                    return (date_val.timestamp(), -area)

                files.sort(key=sort_key, reverse=True)

            if not files:
                if attempt < max_retries - 1:
                    logger.debug(
                        f"Grid '{name}' not found. Wiping cache for '{provider}' "
                        f"and retrying (Attempt {attempt + 2}/{max_retries})..."
                    )

                    if os.path.exists(self.cache_dir):
                        for f in os.listdir(self.cache_dir):
                            if (
                                name.lower() in f.lower()
                                or provider.lower() in f.lower()
                            ):
                                try:
                                    os.remove(os.path.join(self.cache_dir, f))
                                except OSError:
                                    pass
                    continue
                else:
                    logger.debug(
                        f"Grid probe failed: Could not locate grid '{name}' "
                        f"from '{provider}'. Falling back..."
                    )

                    raise MissingGridError(
                        f"Required shift grid '{name}' is missing or unavailable."
                    )

            try:
                if provider == "seanoe" or provider == "fes":
                    var_name = (
                        "lat_elevation" if "lat" in name.lower() else "msl_elevation"
                    )
                    nc_path = f"netcdf:{files[0]}:{var_name}"
                    return GridEngine.load_and_interpolate(
                        [nc_path],
                        self.region,
                        self.nx,
                        self.ny,
                        decay_pixels=self.decay_pixels,
                    )

                return GridEngine.load_and_interpolate(
                    files, self.region, self.nx, self.ny, decay_pixels=self.decay_pixels
                )
            except GridCorruptionError:
                if attempt < max_retries - 1:
                    logger.warning(
                        "Download corruption detected. Retrying fetch "
                        f"(Attempt {attempt + 2}/{max_retries})..."
                    )
                    continue
                else:
                    logger.error(
                        "Max retries reached. Could not secure an uncorrupted grid."
                    )
                    logger.error(
                        "Max retries reached. Could not secure an uncorrupted grid."
                    )
                    raise MissingGridError(f"Grid '{name}' is persistently corrupted.")

        raise MissingGridError(
            f"Failed to fetch grid '{name}' due to an unknown error."
        )

    def _get_htdp_shift(
        self,
        epsg_from: int,
        epsg_to: int,
        epoch_from: str = "2010.0",
        epoch_to: str = "2010.0",
        context: str = "",
    ) -> np.ndarray:
        """Calculate Frame Shift via HTDP with fallback.

        Args:
            epsg_from: Source EPSG code.
            epsg_to: Target EPSG code.
            epoch_from: Source epoch.
            epoch_to: Target epoch.
            context: Context string for logging.

        Returns:
            2D shift grid.
        """

        if epsg_from == epsg_to and epoch_from == epoch_to:
            return np.zeros((self.ny, self.nx))

        from . import htdp

        try:
            ctx_str = f" {context}" if context else ""
            logger.info(
                f"    [HTDP] Frame Shift: EPSG:{epsg_from} -> EPSG:{epsg_to}{ctx_str}"
            )
            tool = htdp.HTDP(version="3.5.0", verbose=False)

            grid = tool.run_grid(
                self.region,
                self.nx,
                self.ny,
                epsg_from,
                epsg_to,
                str(epoch_from),
                str(epoch_to),
            )

            if not np.any(grid):
                logger.warning(
                    f"    [HTDP WARNING] Cross-epoch shift failed (likely outside "
                    f"modeled velocity region for {epoch_from} -> {epoch_to})."
                )
                logger.warning(
                    f"    [HTDP WARNING] Falling back to static datum shift at Output Epoch {epoch_to}."
                )

                grid = tool.run_grid(
                    self.region,
                    self.nx,
                    self.ny,
                    epsg_from,
                    epsg_to,
                    str(epoch_from),
                    str(epoch_to),
                )

            if np.any(grid):
                logger.info(f"    [HTDP] Component Shift (Mean: {np.mean(grid):.3f}m)")
            else:
                logger.error(
                    "    [HTDP FATAL] Both dynamic and static shifts failed returning zeros."
                )

            return grid

        except Exception as e:
            logger.error(f"    [HTDP] Failed: {e}")
            return np.zeros((self.ny, self.nx))

    def _fetch_geoid_with_fallback(self, target_geoid: str) -> Tuple[np.ndarray, str]:
        """Fetch a geoid grid with fallback to older models.

        Args:
            target_geoid: Target geoid name.

        Returns:
            Tuple of (grid, used_geoid_name).

        Raises:
            MissingGridError: If all geoid fallbacks fail.
        """

        us_geoids = ["g2018", "g2012b", "geoid09"]

        if target_geoid in us_geoids:
            start_idx = us_geoids.index(target_geoid)
            geoids_to_try = us_geoids[start_idx:]
        else:
            geoids_to_try = [target_geoid]

        for g in geoids_to_try:
            geoid_def = Datums.GEOIDS.get(g, {})
            provider = geoid_def.get("provider", "proj")

            try:
                grid = self._get_grid(provider, g)
                if np.any(grid):
                    if g != target_geoid and self.verbose:
                        logger.info(
                            f"    [Geoid Fallback] '{target_geoid}' lacks coverage here. "
                            f"Falling back to '{g}'."
                        )
                    return (grid, g)
            except MissingGridError:
                logger.debug(
                    f"    [Geoid Check] '{g}' missing or out of bounds. "
                    "Trying next fallback..."
                )
                continue

        raise MissingGridError(
            f"Geoid '{target_geoid}' and all fallbacks lack coverage or failed to download."
        )

    def _fetch_ocean_mask(self) -> Optional[np.ndarray]:
        """Fetch NASA Dist2Coast raster and threshold to boolean land mask.

        Returns:
            Boolean ocean mask, or None if fetch failed.
        """

        logger.info("    [Coastline] Fetching Dist2Coast raster for inland masking...")

        try:
            d2c_files = self.fetch_grid("dist2coast", variant="base")
            if not d2c_files:
                logger.warning(
                    "    [Coastline] Dist2Coast fetch failed. No land mask applied."
                )
                return None

            nc_path = f"netcdf:{d2c_files[0]}:dist"
            d2c_grid = GridEngine.load_and_interpolate(
                [nc_path], self.region, self.nx, self.ny, decay_pixels=0
            )

            ocean_mask = d2c_grid > 0

            logger.info("    [Coastline] Successfully generated raster land mask.")
            return ocean_mask

        except Exception as e:
            logger.error(
                f"    [Coastline] Failed to generate land mask from Dist2Coast: {e}"
            )
            return None

    # =========================================================================
    # Chains
    # =========================================================================
    def _get_vdatum_chain(
        self, datum_name: str, geoid_name: Optional[str]
    ) -> Tuple[Optional[np.ndarray], str]:
        """Build shift chain: Tidal -> [NAD83 Native].

        Args:
            datum_name: Tidal datum name.
            geoid_name: Geoid name for orthometric conversion.

        Returns:
            Tuple of (shift_grid, description).
        """

        hydro_shift = np.zeros((self.ny, self.nx))
        desc: List[str] = []

        # Tidal -> LMSL
        if datum_name not in ["msl", "5714", "lmsl"]:
            try:
                grid = self._get_grid("vdatum", datum_name)
                if np.isnan(grid).all() or (grid == 0).all():
                    grid = np.full((self.ny, self.nx), np.nan)
            except MissingGridError:
                logger.debug(
                    f"    [VDatum Check] '{datum_name}' missing. "
                    "Flagging for offshore proxy."
                )
                grid = np.full((self.ny, self.nx), np.nan)

            hydro_shift += grid
            desc.append(f"({datum_name}->LMSL)")

        # LMSL -> Ortho (TSS)
        try:
            tss = self._get_grid("vdatum", "tss")
            if np.isnan(tss).all() or (tss == 0).all():
                tss = np.full((self.ny, self.nx), np.nan)
        except MissingGridError:
            tss = np.full((self.ny, self.nx), np.nan)

        hydro_shift -= tss
        desc.append("TSS(LMSL->NAVD88)")

        # Ortho -> NAD83 (Geoid)
        actual_geoid = geoid_name if geoid_name else "g2018"
        try:
            geoid_grid, used_geoid = self._fetch_geoid_with_fallback(actual_geoid)
            desc.append(f"Geoid({used_geoid}->NAD83)")
        except MissingGridError:
            logger.debug(
                f"    [Vdatum Check] Geoid '{actual_geoid}' missing. "
                "Flagging for global proxy."
            )
            return None, "Geoid Missing"

        # =======================================================
        # Coastal Blend
        # =======================================================
        total_shift = np.zeros((self.ny, self.nx))

        if np.isnan(hydro_shift).any():
            ocean_mask = self._fetch_ocean_mask()
            proxy_name = Datums.get_global_proxy(datum_name)

            if ocean_mask is not None:
                # Carve out the VDatum rivers so they aren't treated as land!
                valid_vdatum = ~np.isnan(hydro_shift)
                ocean_mask[valid_vdatum] = True

            if self.use_stations:
                logger.info("    [Override] Forcing Tide Station RBF interpolation...")
                rbf_grid = GridGen.from_stations(
                    self.region,
                    self.nx,
                    self.ny,
                    datum_in=datum_name,
                    datum_out="msl",
                )

                if rbf_grid is not None:
                    global_shift, d_global = self._get_global_chain(
                        "mss", model="fes2014"
                    )

                    if global_shift is not None and np.any(global_shift):
                        htdp_wgs_to_nad = self._get_htdp_shift(
                            WGS84_EPSG,
                            NAD83_EPSG,
                            self.epoch_in,
                            "2010.0",
                            context="(Aligning Global Proxy to NAD83)",
                        )
                        fes_nad83 = global_shift + htdp_wgs_to_nad
                        fes_navd88 = fes_nad83 - geoid_grid
                        combined_shift = rbf_grid + fes_navd88

                        vdatum_empty = np.isnan(hydro_shift)
                        hydro_shift[vdatum_empty] = combined_shift[vdatum_empty]

                        hydro_shift = GridEngine.fill_nans(
                            hydro_shift,
                            decay_pixels=self.decay_pixels,
                            buffer_pixels=10,
                            ocean_mask=ocean_mask,
                        )
                        desc.append("Station RBF (Tidal) + FES (MSS) + Inland Decay")
                    else:
                        logger.warning("    [Override] FES baseline missing.")
                        hydro_shift = GridEngine.fill_nans(
                            hydro_shift,
                            decay_pixels=self.decay_pixels,
                            buffer_pixels=10,
                            ocean_mask=ocean_mask,
                        )
                        desc.append("Inland Hydro Decay")
                else:
                    logger.warning("    [Override] Tide Station RBF failed.")
                    hydro_shift = GridEngine.fill_nans(
                        hydro_shift,
                        decay_pixels=self.decay_pixels,
                        buffer_pixels=10,
                        ocean_mask=ocean_mask,
                    )
                    desc.append("Inland Hydro Decay")

            elif proxy_name:
                logger.info(
                    f"Partial VDatum coverage detected. Fetching {proxy_name.upper()} "
                    "(FES) for offshore blending..."
                )
                global_shift, d_global = self._get_global_chain(
                    proxy_name, model="fes2014"
                )

                if global_shift is not None and np.any(global_shift):
                    htdp_wgs_to_nad = self._get_htdp_shift(
                        WGS84_EPSG, NAD83_EPSG, self.epoch_in, "2010.0"
                    )
                    fes_nad83 = global_shift + htdp_wgs_to_nad
                    fes_navd88 = fes_nad83 - geoid_grid
                    hydro_shift = GridEngine.coastal_aware_composite(
                        vdatum_grid=hydro_shift,
                        global_grid=fes_navd88,
                        nx=self.nx,
                        ny=self.ny,
                        ocean_mask=ocean_mask,
                        decay_pixels=self.decay_pixels,
                        buffer_pixels=10,
                    )
                    desc.append(f"Blended w/ Global({proxy_name.upper()})")
                else:
                    hydro_shift = GridEngine.fill_nans(
                        hydro_shift,
                        decay_pixels=self.decay_pixels,
                        buffer_pixels=10,
                        ocean_mask=ocean_mask,
                    )
                    desc.append("Inland Hydro Decay")
            else:
                hydro_shift = GridEngine.fill_nans(
                    hydro_shift,
                    decay_pixels=self.decay_pixels,
                    buffer_pixels=10,
                    ocean_mask=ocean_mask,
                )
                desc.append("Inland Hydro Decay")

        total_shift = hydro_shift + geoid_grid
        total_shift[np.isnan(total_shift)] = 0.0

        return total_shift, " + ".join(desc)

    def _get_global_chain(
        self, datum_name: str, model: str = "fes2014"
    ) -> Tuple[np.ndarray, str]:
        """Build shift: Global Tidal -> WGS84 Native.

        Args:
            datum_name: Tidal datum name.
            model: Model name (e.g., 'fes2014', 'dtu25').

        Returns:
            Tuple of (shift_grid, description).
        """

        tidal_shift = np.zeros((self.ny, self.nx))
        desc = []

        proxy_name = Datums.get_global_proxy(datum_name)

        # DTU25 MSS Baseline (Absolute height above WGS84)
        try:
            mss_grid = self._get_grid("transformez.dtu", "mss25")
            if np.any(mss_grid):
                desc.append("DTU25_MSS")
        except Exception:
            logger.debug("    [Global Chain] DTU25 MSS unavailable.")
            return np.zeros((self.ny, self.nx)), "Global Chain Failed"

        # Tidal Extreme Offsets (FES2014 via seanoe)
        if proxy_name == "lat":
            try:
                lat_grid = self._get_grid("seanoe", "lat")
                if np.nanmean(lat_grid) > 0:
                    lat_grid *= -1.0
                tidal_shift += lat_grid
                desc.append("Global(LAT)")
            except Exception:
                logger.debug("    [Global Chain] FES2014 LAT unavailable.")

        elif proxy_name == "hat":
            try:
                lat_grid = self._get_grid("seanoe", "lat")
                if np.nanmean(lat_grid) > 0:
                    lat_grid *= -1.0
                tidal_shift += lat_grid * -1.0
                desc.append("Global(HAT)")
            except Exception:
                logger.debug("    [Global Chain] FES2014 HAT unavailable.")

        # Coastal Mask to MDT / Tidal Arrays
        ocean_mask = self._fetch_ocean_mask()

        tidal_shift = GridEngine.fill_nans(
            tidal_shift,
            decay_pixels=self.decay_pixels,
            buffer_pixels=10,
            ocean_mask=ocean_mask,
        )

        total_shift = mss_grid + tidal_shift
        total_shift[np.isnan(total_shift)] = 0.0

        return total_shift, " + ".join(desc)

    # =========================================================================
    # Steps
    # =========================================================================
    def _step_to_hub(
        self,
        epsg: Optional[int],
        ref_type: Optional[str],
        geoid: Optional[str] = None,
        epoch: str = "2010.0",
    ) -> Tuple[np.ndarray, str]:
        """Step from source datum to central hub.

        Args:
            epsg: EPSG code.
            ref_type: Reference type.
            geoid: Geoid name.
            epoch: Epoch.

        Returns:
            Tuple of (shift_grid, description).
        """

        shift = np.zeros((self.ny, self.nx))
        if epsg == self.hub_epsg:
            return (shift, "Already at Hub")

        native_epsg = self._get_native_ellipsoid(epsg, ref_type)
        chain_shift = None
        chain_desc = ""

        if ref_type in ["surface", "global_tidal"]:
            if epsg is None or epsg not in Datums.SURFACES:
                return (shift, "No surface definition")

            datum_name = Datums.SURFACES[epsg]["name"]
            region_tag = Datums.SURFACES[epsg].get("region")

            if region_tag == "usa":
                s, d = self._get_vdatum_chain(datum_name, geoid)
                if s is None:
                    native_epsg = WGS84_EPSG
                    proxy_name = Datums.get_global_proxy(datum_name)
                    if proxy_name:
                        s, d = self._get_global_chain(proxy_name, model="fes2014")
                        # d = f"Global({proxy_name}) [Proxy] -> WGS84"
                chain_shift, chain_desc = s, d

            elif region_tag == "global":
                chain_shift, chain_desc = self._get_global_chain(datum_name)

        elif ref_type == "cdn":
            target_geoid = geoid if geoid else "g2018"
            chain_shift, used_geoid = self._fetch_geoid_with_fallback(target_geoid)
            chain_desc = f"Ortho(via {used_geoid}) -> Frame({native_epsg})"

        elif ref_type == "htdp":
            chain_shift = np.zeros((self.ny, self.nx))
            chain_desc = f"Frame({epsg})"

        if chain_shift is not None:
            if native_epsg != self.hub_epsg:
                htdp_shift = self._get_htdp_shift(
                    native_epsg,
                    self.hub_epsg,
                    epoch,
                    self.epoch_out,
                    context="(Stepping to Central Hub)",
                )
                chain_shift += htdp_shift
                chain_desc += f" + Frame({native_epsg}->{self.hub_epsg})"
            return (chain_shift, chain_desc)

        return (shift, "")

    def _step_from_hub(
        self,
        epsg: Optional[int],
        ref_type: Optional[str],
        geoid: Optional[str] = None,
        epoch: str = "2010.0",
    ) -> Tuple[np.ndarray, str]:
        """Step from central hub to target datum.

        Args:
            epsg: EPSG code.
            ref_type: Reference type.
            geoid: Geoid name.
            epoch: Epoch.

        Returns:
            Tuple of (shift_grid, description).
        """

        shift = np.zeros((self.ny, self.nx))
        if epsg == self.hub_epsg:
            return shift, "Remain at Hub"

        native_epsg = self._get_native_ellipsoid(epsg, ref_type)
        total_out = np.zeros((self.ny, self.nx))
        desc_parts = []

        htdp_shift = np.zeros((self.ny, self.nx))

        if self.hub_epsg != native_epsg:
            htdp_shift = self._get_htdp_shift(
                self.hub_epsg,
                native_epsg,
                self.epoch_in,
                epoch,
                context="(Extracting from Central Hub)",
            )
            total_out += htdp_shift
            desc_parts.append(f"Hub({self.hub_epsg}->{native_epsg})")

        if ref_type in ["surface", "global_tidal"]:
            if epsg is None or epsg not in Datums.SURFACES:
                return (np.zeros((self.ny, self.nx)), "FAILED: No surface definition")

            datum_name = Datums.SURFACES[epsg]["name"]
            region_tag = Datums.SURFACES[epsg].get("region")
            chain_geoid = geoid if geoid else "g2018"

            if region_tag == "usa":
                s, d = self._get_vdatum_chain(datum_name, chain_geoid)
                if s is None:
                    proxy_name = Datums.get_global_proxy(datum_name)
                    if proxy_name:
                        # Revert the erroneous HTDP shift to NAD83 (since global is WGS84)
                        total_out -= htdp_shift
                        if desc_parts:
                            desc_parts.pop()

                        s, d = self._get_global_chain(proxy_name, model="fes2014")
                        if s is not None:
                            total_out -= s
                            desc_parts.append(d)
                        else:
                            return np.zeros(
                                (self.ny, self.nx)
                            ), "FAILED Output Global Chain"
                    else:
                        return np.zeros((self.ny, self.nx)), "FAILED Output Chain"
                else:
                    total_out -= s
                    desc_parts.append(d)

            elif region_tag == "global":
                s, d = self._get_global_chain(datum_name)
                if s is not None:
                    total_out -= s
                    desc_parts.append(d)

        elif ref_type == "cdn":
            target_geoid = geoid if geoid else "g2018"
            geoid_grid, used_geoid = self._fetch_geoid_with_fallback(target_geoid)

            if not np.any(geoid_grid):
                logger.warning(
                    f"Geoid {target_geoid} (and fallbacks) not found/covered."
                )

            total_out -= geoid_grid
            desc_parts.append(f"Native -> Ortho(via {used_geoid})")

        return (total_out, " + ".join(desc_parts))

    def _vertical_transform(self) -> Tuple[np.ndarray, np.ndarray]:
        """Perform the full vertical transformation.

        Returns:
            Tuple of (shift_grid, uncertainty_grid).
        """

        logger.info("-" * 60)
        logger.info(f"Transformation Plan: {self.epsg_in} -> {self.epsg_out}")
        logger.info(f"Hub Frame: EPSG:{self.hub_epsg}")

        total_shift = np.zeros((self.ny, self.nx))
        total_unc = np.zeros((self.ny, self.nx))

        if self.epsg_in == self.epsg_out:
            logger.info("  1. Identity Transform (Zero Shift)")
            return total_shift, total_unc

        # Input -> Hub
        grid_1, desc_1 = self._step_to_hub(
            self.epsg_in, self.ref_in, self.geoid_in, self.epoch_in
        )
        if np.any(grid_1):
            logger.info(f"  1. {desc_1}")
            total_shift += grid_1
        else:
            logger.info(f"  1. {desc_1} (No Shift/Zero)")

        # Hub -> Output
        grid_2, desc_2 = self._step_from_hub(
            self.epsg_out, self.ref_out, self.geoid_out, self.epoch_out
        )
        if np.any(grid_2):
            logger.info(f"  2. {desc_2}")
            total_shift += grid_2
        else:
            logger.info(f"  2. {desc_2} (No Shift/Zero)")

        if np.any(total_shift) and not np.isnan(total_shift).all():
            mean_shift = np.nanmean(total_shift)
            min_shift = np.nanmin(total_shift)
            max_shift = np.nanmax(total_shift)
            logger.info(
                f"  => Total Shift Applied (Mean: {mean_shift:.3f}m | Min: {min_shift:.3f}m | Max: {max_shift:.3f}m)"
            )
        else:
            logger.info("  => Total Shift Applied (Zero / Identity)")

        logger.info("-" * 60)
        return (total_shift, total_unc)
