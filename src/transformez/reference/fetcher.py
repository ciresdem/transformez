#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.reference.fetcher
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Dedicated raster fetching and compositing engine for the Transformation Executor.
Handles the physical downloading, unpacking, compositing, and coastal blending
of geodetic grids.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import gzip
import shutil
import logging
from pathlib import Path
from typing import Any, List, Optional, Tuple

import numpy as np
import fetchez.api
import fetchez.utils

from transformez.grid_engine import (
    CoastalContext,
    GridEngine,
    GridGen,
    GridCorruptionError,
)
from transformez.engines.htdp import HTDP
from .bindings import OPERATION_BINDINGS

logger = logging.getLogger(__name__)


class MissingGridError(Exception):
    """Raised when a required shift grid cannot be fetched or is persistently corrupted."""

    pass


class GridFetcher:
    """Dedicated fetcher and compositor for the Transformation Execution engine."""

    def __init__(
        self,
        region: Any,
        nx: int,
        ny: int,
        cache_dir: Path,
        decay_pixels: int = 100,
        decay_distance_m: Optional[float] = None,
        buffer_distance_m: float = 0.0,
        max_vdatum_extension_m: Optional[float] = None,
        extrapolate_inland: bool = False,
        use_stations: bool = False,
        epoch_in: str = "2010.0",
        htdp_tool: Optional[HTDP] = None,
        verbose: bool = True,
    ):
        self.region = region
        self.nx = nx
        self.ny = ny
        self.cache_dir = Path(cache_dir)
        self.decay_pixels = decay_pixels
        self.decay_distance_m = decay_distance_m
        self.buffer_distance_m = buffer_distance_m
        self.max_vdatum_extension_m = max_vdatum_extension_m
        self.extrapolate_inland = extrapolate_inland
        self.use_stations = use_stations
        self.epoch_in = epoch_in
        self.verbose = verbose

        # Strictly used for aligning FES (WGS84) to VDatum (NAD83) during blending
        self.htdp_tool = htdp_tool or HTDP(verbose=False)

    def fetch_grid(self, module_name: str, **kwargs: Any) -> List[Path]:
        """Generic fetcher wrapper using the fetchez API."""
        files = fetchez.api.get(
            module=module_name,
            region=self.region,
            outdir=str(self.cache_dir),
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
                fns_to_extract = [datatype, ".met", ".inf"] if datatype else None
                try:
                    extracted = fetchez.utils.p_f_unzip(
                        str(fn), fns=fns_to_extract, outdir=str(self.cache_dir)
                    )
                except OSError as e:
                    if e.errno == 30 or "Read-only" in str(e):
                        logger.debug(
                            f"Read-only cache detected. Assuming {fn} is already unzipped."
                        )
                        extracted = [
                            str(Path(root) / f)
                            for root, _, filenames in os.walk(self.cache_dir)
                            for f in filenames
                        ]
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
                        with gzip.open(fn, "rb") as f_in, out_fn.open("wb") as f_out:
                            shutil.copyfileobj(f_in, f_out)
                    valid.append(out_fn)
                except Exception as e:
                    logger.error(f"Failed to decompress {fn}: {e}")

            elif fn.suffix in [".gtx", ".tif", ".grd", ".nc", ".mss"]:
                valid.append(fn)
        return valid

    def _get_grid(self, provider: str, name: str, max_retries: int = 3) -> np.ndarray:
        """Fetch and load a grid with corruption recovery."""
        if not name:
            raise MissingGridError("A valid grid name must be provided to the fetcher.")
        if not provider:
            provider = "proj"

        name = name.split(":")[-1] if ":" in name else name

        for attempt in range(max_retries):
            files = self.fetch_grid(provider, datatype=name, query=name)

            if provider == "vdatum":
                import rasterio
                from datetime import datetime

                def get_vdatum_date(gtx_path: Path) -> datetime:
                    meta_files = [
                        f
                        for f in list(gtx_path.parent.iterdir())
                        if f.suffix in [".met", ".inf"]
                    ]
                    if not meta_files:
                        return datetime(1970, 1, 1)
                    try:
                        with meta_files[0].open("r") as f:
                            content = f.read().splitlines()
                        for line in content:
                            if "released_date=" in line:
                                m, d, y = map(
                                    int, line.split("=")[1].strip().split("/")
                                )
                                return datetime(y, m, d)
                    except Exception:
                        pass
                    return datetime(1970, 1, 1)

                def sort_key(filepath: Path) -> Tuple[float, float]:
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
                        f"Grid '{name}' not found. Wiping cache for '{provider}' and retrying..."
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
                raise MissingGridError(
                    f"Required shift grid '{name}' is missing or unavailable."
                )

            try:
                if provider in ("seanoe", "fes"):
                    var_name = (
                        "lat_elevation" if "lat" in name.lower() else "msl_elevation"
                    )
                    nc_path = f"netcdf:{files[0]}:{var_name}"
                    return GridEngine.load_and_interpolate(
                        [nc_path], self.region, self.nx, self.ny
                    )
                return GridEngine.load_and_interpolate(
                    files, self.region, self.nx, self.ny
                )
            except GridCorruptionError:
                if attempt < max_retries - 1:
                    continue
                raise MissingGridError(
                    f"Grid '{name}' is persistently corrupted."
                ) from None

        raise MissingGridError(
            f"Failed to fetch grid '{name}' due to an unknown error."
        )

    def fetch_geoid(self, target_geoid: str) -> Tuple[np.ndarray, str]:
        """Fetch a geoid grid with fallback to older models."""
        target_geoid = (
            target_geoid.split(":")[-1] if ":" in target_geoid else target_geoid
        )

        us_geoids = ["g2018", "g2012b", "geoid09"]
        geoids_to_try = (
            us_geoids[us_geoids.index(target_geoid) :]
            if target_geoid in us_geoids
            else [target_geoid]
        )

        for g in geoids_to_try:
            try:
                # We strictly use the PROJ CDN for geoids in this architecture
                grid = self._get_grid("proj", g)
                if np.any(grid):
                    if g != target_geoid and self.verbose:
                        logger.info(
                            f"    [Geoid Fallback] '{target_geoid}' lacks coverage here. Falling back to '{g}'."
                        )
                    return (grid, g)
            except MissingGridError:
                continue

        raise MissingGridError(
            f"Geoid '{target_geoid}' and fallbacks lack coverage or failed to download."
        )

    def _fetch_coastal_context(
        self, vdatum_grid: Optional[np.ndarray] = None
    ) -> Optional[CoastalContext]:
        """Build the effective water mask plus inland-distance field."""
        try:
            d2c_files = self.fetch_grid("dist2coast", variant="base")
            if not d2c_files:
                return None
            nc_path = f"netcdf:{d2c_files[0]}:dist"

            d2c_grid = GridEngine.load_and_interpolate(
                [nc_path], self.region, self.nx, self.ny, preserve_zero=True
            )
            d2c_m = d2c_grid.astype(np.float32) * 1000.0  # Assumes Dist2Coast is in km

            valid_vdatum = np.isfinite(vdatum_grid) if vdatum_grid is not None else None
            return GridEngine.build_coastal_context(
                signed_distance_m=d2c_m,
                target_region=self.region,
                vdatum_valid=valid_vdatum,
                max_vdatum_extension_m=self.max_vdatum_extension_m,
            )
        except Exception as e:
            logger.error(f"    [Coastline] Failed to build context: {e}")
            return None

    def fetch_global_chain(
        self, datum_name: str, model: str = "fes2014"
    ) -> Tuple[np.ndarray, str]:
        """Build shift: Global Tidal -> WGS84 Native."""
        datum_name = datum_name.split(":")[-1] if ":" in datum_name else datum_name
        tidal_shift = np.zeros((self.ny, self.nx))
        desc = []

        try:
            mss_grid = self._get_grid("transformez.dtu", "mss25")
            if np.any(mss_grid):
                desc.append("DTU25_MSS")
        except Exception:
            return np.zeros((self.ny, self.nx)), "Global Chain Failed"

        if datum_name in ("lat", "hat"):
            try:
                lat_grid = self._get_grid("seanoe", "lat")
                if np.nanmean(lat_grid) > 0:
                    lat_grid *= -1.0
                tidal_shift += lat_grid if datum_name == "lat" else lat_grid * -1.0
                desc.append(f"Global({datum_name.upper()})")
            except Exception:
                pass

        total_shift = mss_grid + tidal_shift
        return total_shift, " + ".join(desc)

    def fetch_vdatum_chain(
        self, datum_name: str, geoid_name: Optional[str]
    ) -> Tuple[Optional[np.ndarray], str]:
        """Build shift chain: Tidal -> [NAD83 Native]."""
        datum_name = datum_name.split(":")[-1] if ":" in datum_name else datum_name
        hydro_shift = np.zeros((self.ny, self.nx))
        desc = []

        # Tidal -> LMSL
        if datum_name not in ["msl", "5714", "lmsl"]:
            try:
                grid = self._get_grid("vdatum", datum_name)
                if np.isnan(grid).all() or (grid == 0).all():
                    grid = np.full((self.ny, self.nx), np.nan)
            except MissingGridError:
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
        actual_geoid = geoid_name or "g2018"
        try:
            geoid_grid, used_geoid = self.fetch_geoid(actual_geoid)
            desc.append(f"Geoid({used_geoid}->NAD83)")
        except MissingGridError:
            return None, "Geoid Missing"

        # Coastal Blend
        if np.isnan(hydro_shift).any():
            coastal_context = self._fetch_coastal_context(hydro_shift)

            # Resolve the proxy from the bindings rather than the old Datums class
            binding = OPERATION_BINDINGS.get(f"vdatum:{datum_name}")
            proxy_id = binding.global_proxy if binding else None
            proxy_datum = proxy_id.split(":")[1] if proxy_id else None

            if self.use_stations:
                rbf_grid = GridGen.from_stations(
                    self.region, self.nx, self.ny, datum_in=datum_name, datum_out="msl"
                )
                if rbf_grid is not None:
                    global_shift, _ = self.fetch_global_chain("mss", model="fes2014")
                    if global_shift is not None and np.any(global_shift):
                        # Align FES (WGS84/10) to VDatum (NAD83/1)
                        htdp_wgs_to_nad = self.htdp_tool.run_grid(
                            region=self.region,
                            nx=self.nx,
                            ny=self.ny,
                            frame_id_in=10,
                            frame_id_out=1,
                            epoch_in=str(self.epoch_in),
                            epoch_out="2010.0",
                        )
                        fes_nad83 = global_shift + htdp_wgs_to_nad
                        combined_shift = rbf_grid + (fes_nad83 - geoid_grid)
                        vdatum_empty = np.isnan(hydro_shift)
                        hydro_shift[vdatum_empty] = combined_shift[vdatum_empty]
                        desc.append("Station RBF (Tidal) + FES (MSS) + Inland Decay")

            elif proxy_datum:
                global_shift, _ = self.fetch_global_chain(proxy_datum, model="fes2014")
                if global_shift is not None and np.any(global_shift):
                    htdp_wgs_to_nad = self.htdp_tool.run_grid(
                        region=self.region,
                        nx=self.nx,
                        ny=self.ny,
                        frame_id_in=10,
                        frame_id_out=1,
                        epoch_in=str(self.epoch_in),
                        epoch_out="2010.0",
                    )
                    fes_nad83 = global_shift + htdp_wgs_to_nad
                    hydro_shift = GridEngine.coastal_aware_composite(
                        vdatum_grid=hydro_shift,
                        global_grid=fes_nad83 - geoid_grid,
                        nx=self.nx,
                        ny=self.ny,
                        coastal_context=coastal_context,
                        decay_pixels=self.decay_pixels,
                        buffer_pixels=10,
                        decay_distance_m=self.decay_distance_m,
                        buffer_distance_m=self.buffer_distance_m,
                    )
                    desc.append(f"Blended w/ Global({proxy_datum.upper()})")

            if not proxy_datum or (global_shift is None or not np.any(global_shift)):
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

        return hydro_shift + geoid_grid, " + ".join(desc)
