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
from pathlib import Path
from typing import Any, List, Optional, Tuple

import numpy as np
import fetchez.api
from fetchez.utils import float_or

from .definitions import Datums
from .grid_engine import CoastalContext, GridEngine, GridGen, GridCorruptionError
from .utils import normalize_epoch

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
        decay_distance_m: Optional[float] = None,
        buffer_distance_m: Optional[float] = None,
        extrapolate_inland: bool = False,
        max_vdatum_extension_m: Optional[float] = None,
        cache_dir: Optional[str | Path] = None,
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
            decay_pixels: Legacy pixel-based inland decay distance.
            decay_distance_m: Preferred inland decay distance in meters.
                If None, legacy ``decay_pixels`` behavior is retained.
            buffer_distance_m: No-decay buffer landward of the effective
                shoreline when ``decay_distance_m`` is used.
            extrapolate_inland: No decay will be performed and the shift values
                will be extrapolated for the entire region.
            max_vdatum_extension_m: Optional guard limiting how far inland VDatum
                coverage may override the native Dist2Coast shoreline. None keeps
                the current behavior of accepting all valid VDatum coverage.
            cache_dir: Path to store downloaded grids.
            use_stations: Force RBF interpolation using live tide stations.
            verbose: Enable debug logging.
        """

        self.region = region
        self.nx = nx
        self.ny = ny

        self.cache_dir = (
            Path(cache_dir)
            if cache_dir is not None
            else Path.cwd() / "transformez_cache"
        )
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.verbose = verbose

        self.epsg_in = Datums.get_vdatum_by_name(str(epsg_in))
        self.epsg_out = Datums.get_vdatum_by_name(str(epsg_out))

        self.geoid_in = geoid_in or Datums.get_default_geoid(self.epsg_in)
        self.geoid_out = geoid_out or Datums.get_default_geoid(self.epsg_out)

        self.epoch_in = normalize_epoch(epoch_in)
        self.epoch_out = normalize_epoch(epoch_out)

        self.ref_in = Datums.get_frame_type(self.epsg_in)
        self.ref_out = Datums.get_frame_type(self.epsg_out)

        self.decay_pixels = decay_pixels
        self.decay_distance_m = decay_distance_m
        self.buffer_distance_m = float_or(buffer_distance_m, 0.0)
        self.max_vdatum_extension_m = max_vdatum_extension_m
        self.extrapolate_inland = extrapolate_inland

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

    def fetch_grid(self, module_name: str, **kwargs: Any) -> List[Path]:
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

        valid: List[Path] = []

        for fn in files:
            fn = Path(fn)
            if not fn.exists():
                continue

            if fn.suffix == ".zip":
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
                                extracted.append(Path(root) / f)
                    else:
                        raise
                for extracted_file in extracted:
                    path = Path(extracted_file)
                    if (
                        path.suffix in {".gtx", ".tif", ".grd", ".nc"}
                        and "unc." not in path.name
                    ):
                        valid.append(path)

            elif fn.suffix == ".gz":
                try:
                    out_fn = fn.parent / fn.stem
                    if not out_fn.exists():
                        logger.debug(f"Decompressing {fn}...")
                        with gzip.open(fn, "rb") as f_in:
                            with out_fn.open("wb") as f_out:
                                shutil.copyfileobj(f_in, f_out)
                    valid.append(out_fn)
                except Exception as e:
                    logger.error(f"Failed to decompress {fn}: {e}")

            elif fn.suffix in [".gtx", ".tif", ".grd", ".nc", ".mss"]:
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

                def get_vdatum_date(gtx_path: Path) -> datetime:
                    """Parse release date from VDatum metadata files."""

                    dir_name = gtx_path.parent
                    meta_files = [
                        f
                        for f in list(dir_name.iterdir())
                        if f.suffix in [".met", ".inf"]
                    ]

                    if not meta_files:
                        return datetime(1970, 1, 1)

                    meta_path = meta_files[0]
                    try:
                        with meta_path.open("r") as f:
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

                def sort_key(filepath: Path) -> Tuple[float, float]:
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

                    if self.cache_dir.exists():
                        for f in list(self.cache_dir.iterdir()):
                            if (
                                name.lower() in str(f).lower()
                                or provider.lower() in str(f).lower()
                            ):
                                try:
                                    f.unlink()
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
                    raise MissingGridError(
                        f"Grid '{name}' is persistently corrupted."
                    ) from None

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

            logger.debug(
                "HTDP request: EPSG:%s @ %r -> EPSG:%s @ %r",
                epsg_from,
                epoch_from,
                epsg_to,
                epoch_to,
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
                    str(epoch_to),
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

    def _fetch_dist2coast_m(self) -> Optional[np.ndarray]:
        """Fetch NASA Dist2Coast as a signed physical-distance field in meters.

        Positive values are treated as water and negative values as land.
        The continuous field is bilinearly resampled because we want the
        signed distance itself, not a categorical shoreline raster.
        """

        logger.info("    [Coastline] Fetching Dist2Coast signed distance field...")

        try:
            import rasterio

            d2c_files = self.fetch_grid("dist2coast", variant="base")
            if not d2c_files:
                logger.warning(
                    "    [Coastline] Dist2Coast fetch failed. No coastal context applied."
                )
                return None

            nc_path = f"netcdf:{d2c_files[0]}:dist"
            # Dist2Coast declares 0 as nodata even though zero is a meaningful
            # coastline class (the source cell intersects the shoreline). Preserve
            # those cells so build_coastal_context() can resolve the transition.
            d2c_grid = GridEngine.load_and_interpolate(
                [nc_path],
                self.region,
                self.nx,
                self.ny,
                decay_pixels=0,
                preserve_zero=True,
            )

            # Prefer dataset metadata when available.  The dist2coast product reports
            # distance in km, so unknown units retain that assumption but log it  for
            # validation.
            unit = ""
            try:
                with rasterio.open(nc_path) as src:
                    if src.units and src.units[0]:
                        unit = str(src.units[0]).strip().lower()
                    if not unit:
                        unit = str(src.tags(1).get("units", "")).strip().lower()
                    if not unit:
                        unit = str(src.tags().get("units", "")).strip().lower()
            except Exception as e:
                logger.debug(f"    [Coastline] Could not inspect Dist2Coast units: {e}")

            if unit in {"m", "meter", "meters", "metre", "metres"}:
                scale = 1.0
            elif unit in {"km", "kilometer", "kilometers", "kilometre", "kilometres"}:
                scale = 1000.0
            else:
                scale = 1000.0
                logger.warning(
                    "    [Coastline] Dist2Coast units not identified from metadata; "
                    "assuming kilometers. Verify this against the fetched product."
                )

            d2c_m = d2c_grid.astype(np.float32) * scale
            logger.info(
                f"    [Coastline] Dist2Coast loaded as signed meters (source units: {unit or 'assumed km'})."
            )
            return d2c_m

        except Exception as e:
            logger.error(
                f"    [Coastline] Failed to generate Dist2Coast distance field: {e}"
            )
            return None

    def _fetch_coastal_context(
        self,
        vdatum_grid: Optional[np.ndarray] = None,
    ) -> Optional[CoastalContext]:
        """Build the effective water mask plus inland-distance field.

        Dist2Coast defines the native water domain.  Valid VDatum coverage may
        extend that domain landward so decay starts at the VDatum coverage edge.

        Args:
            vdatum_grid: The vdatum coverage array.

        Returns:
            Coastal Context dataclass or None
        """

        d2c_m = self._fetch_dist2coast_m()
        if d2c_m is None:
            return None

        valid_vdatum = None
        if vdatum_grid is not None:
            valid_vdatum = np.isfinite(vdatum_grid)

        context = GridEngine.build_coastal_context(
            signed_distance_m=d2c_m,
            target_region=self.region,
            vdatum_valid=valid_vdatum,
            max_vdatum_extension_m=self.max_vdatum_extension_m,
        )

        if valid_vdatum is not None:
            native_water = np.isfinite(d2c_m) & (d2c_m > 0.0)
            extension_count = np.count_nonzero(
                context.water_mask & valid_vdatum & ~native_water
            )
            logger.info(
                f"    [Coastline] Effective water mask includes {extension_count} "
                "VDatum cells beyond native Dist2Coast water."
            )

        return context

    def _fetch_ocean_mask(self) -> Optional[np.ndarray]:
        """Compatibility wrapper returning only the effective Dist2Coast water mask."""

        context = self._fetch_coastal_context()
        return context.water_mask.copy() if context is not None else None

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
            coastal_context = self._fetch_coastal_context(hydro_shift)
            proxy_name = Datums.get_global_proxy(datum_name)

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
                            coastal_context=coastal_context,
                            decay_distance_m=self.decay_distance_m,
                            buffer_distance_m=self.buffer_distance_m,
                            extrapolate_inland=self.extrapolate_inland,
                        )
                        desc.append("Station RBF (Tidal) + FES (MSS) + Inland Decay")
                    else:
                        logger.warning("    [Override] FES baseline missing.")
                        hydro_shift = GridEngine.fill_nans(
                            hydro_shift,
                            decay_pixels=self.decay_pixels,
                            buffer_pixels=10,
                            coastal_context=coastal_context,
                            decay_distance_m=self.decay_distance_m,
                            buffer_distance_m=self.buffer_distance_m,
                            extrapolate_inland=self.extrapolate_inland,
                        )
                        desc.append("Inland Hydro Decay")
                else:
                    logger.warning("    [Override] Tide Station RBF failed.")
                    hydro_shift = GridEngine.fill_nans(
                        hydro_shift,
                        decay_pixels=self.decay_pixels,
                        buffer_pixels=10,
                        coastal_context=coastal_context,
                        decay_distance_m=self.decay_distance_m,
                        buffer_distance_m=self.buffer_distance_m,
                        extrapolate_inland=self.extrapolate_inland,
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
                        coastal_context=coastal_context,
                        decay_pixels=self.decay_pixels,
                        buffer_pixels=10,
                        decay_distance_m=self.decay_distance_m,
                        buffer_distance_m=self.buffer_distance_m,
                    )
                    desc.append(f"Blended w/ Global({proxy_name.upper()})")
                else:
                    hydro_shift = GridEngine.fill_nans(
                        hydro_shift,
                        decay_pixels=self.decay_pixels,
                        buffer_pixels=10,
                        coastal_context=coastal_context,
                        decay_distance_m=self.decay_distance_m,
                        buffer_distance_m=self.buffer_distance_m,
                        extrapolate_inland=self.extrapolate_inland,
                    )
                    desc.append("Inland Hydro Decay")
            else:
                hydro_shift = GridEngine.fill_nans(
                    hydro_shift,
                    decay_pixels=self.decay_pixels,
                    buffer_pixels=10,
                    coastal_context=coastal_context,
                    decay_distance_m=self.decay_distance_m,
                    buffer_distance_m=self.buffer_distance_m,
                    extrapolate_inland=self.extrapolate_inland,
                )
                desc.append("Inland Hydro Decay")

        total_shift = hydro_shift + geoid_grid

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

        # Coastal context clips tidal proxy values to water and supplies a
        # physical landward distance field for optional meter-based decay.
        coastal_context = self._fetch_coastal_context()

        tidal_shift = GridEngine.fill_nans(
            tidal_shift,
            decay_pixels=self.decay_pixels,
            buffer_pixels=10,
            coastal_context=coastal_context,
            decay_distance_m=self.decay_distance_m,
            buffer_distance_m=self.buffer_distance_m,
            extrapolate_inland=self.extrapolate_inland,
        )

        total_shift = mss_grid + tidal_shift

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
