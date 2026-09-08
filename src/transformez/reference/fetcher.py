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

import gzip
import logging
import os
import shutil
import zipfile
from pathlib import Path
from typing import Any, List, Optional, Tuple

import numpy as np
import rasterio

import fetchez.api
import fetchez.utils
from fetchez.core import run_fetchez
from fetchez.modules.vdatum import VDatum

from transformez.engines.htdp import HTDP
from transformez.grid.engine import (
    CoastalContext,
    GridCorruptionError,
    GridEngine,
    GridGen,
)
from .bindings import HTDP_FRAME_BINDINGS, OPERATION_BINDINGS
from .vdatum import (
    parse_vdatum_registry,
    tss_reference,
    vdatum_priority,
    vdatum_grid_datum,
)

logger = logging.getLogger(__name__)


MIN_VDATUM_FALLBACK_CELLS = 4


class MissingGridError(Exception):
    """Raised when a required shift grid cannot be fetched or is unavailable."""

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

        self.htdp_tool = htdp_tool or HTDP(verbose=False)

    def fetch_grid(
        self,
        module_name: str,
        *,
        extract_names: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> List[Path]:
        """Generic Fetchez wrapper returning extracted raster resources.

        ``extract_names`` controls archive extraction only; it is deliberately
        not forwarded to Fetchez. This lets a VDatum query for one datum
        extract other components from the *same* returned coverage package
        (notably its matching ``tss.gtx``).
        """
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
                fns_to_extract: list[str] | None = None
                if extract_names is not None:
                    fns_to_extract = extract_names
                else:
                    fns_to_extract = [datatype, ".met", ".inf"] if datatype else None
                try:
                    extracted = fetchez.utils.p_f_unzip(
                        str(fn), fns=fns_to_extract, outdir=str(self.cache_dir)
                    )
                except OSError as exc:
                    if exc.errno == 30 or "Read-only" in str(exc):
                        logger.debug(
                            "Read-only cache detected. Assuming %s is already unzipped.",
                            fn,
                        )
                        extracted = [
                            str(Path(root) / filename)
                            for root, _, filenames in os.walk(self.cache_dir)
                            for filename in filenames
                        ]
                    else:
                        raise

                for extracted_file in extracted:
                    path = Path(extracted_file)
                    if (
                        path.suffix.casefold() in {".gtx", ".tif", ".grd", ".nc"}
                        and "unc." not in path.name.casefold()
                    ):
                        valid.append(path)

            elif fn.suffix == ".gz":
                try:
                    out_fn = fn.parent / fn.stem
                    if not out_fn.exists():
                        logger.debug("Decompressing %s...", fn)
                        with gzip.open(fn, "rb") as f_in, out_fn.open("wb") as f_out:
                            shutil.copyfileobj(f_in, f_out)
                    valid.append(out_fn)
                except Exception as exc:
                    logger.error("Failed to decompress %s: %s", fn, exc)

            elif fn.suffix.casefold() in {".gtx", ".tif", ".grd", ".nc", ".mss"}:
                valid.append(fn)

        return valid

    @staticmethod
    def _grid_resolution_area(path: Path) -> float:
        """Return approximate source pixel area for deterministic grid ordering."""
        try:
            with rasterio.open(path) as src:
                return abs(float(src.transform.a) * float(src.transform.e))
        except Exception:
            return float("inf")

    def _get_grid(self, provider: str, name: str, max_retries: int = 3) -> np.ndarray:
        """Fetch and load a generic grid with corruption recovery."""
        if not name:
            raise MissingGridError("A valid grid name must be provided to the fetcher.")
        if not provider:
            provider = "proj"

        name = name.split(":")[-1] if ":" in name else name
        name = name.casefold()

        for attempt in range(max_retries):
            if provider == "vdatum" and name.startswith("xgeoid"):
                return self._fetch_vdatum_model_grid(name)

            files = self.fetch_grid(provider, datatype=name, query=name)

            if not files:
                if attempt < max_retries - 1:
                    logger.debug("Grid '%s' not found. Retrying...", name)
                    continue
                raise MissingGridError(
                    f"Required shift grid '{name}' is missing or unavailable."
                )

            try:
                if provider in ("seanoe", "fes"):
                    var_name = "lat_elevation" if "lat" in name else "msl_elevation"
                    nc_path = f"netcdf:{files[0]}:{var_name}"
                    return GridEngine.load_and_interpolate(
                        [nc_path], self.region, self.nx, self.ny
                    )

                return GridEngine.load_and_interpolate(
                    files,
                    self.region,
                    self.nx,
                    self.ny,
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
        """Fetch a conventional NAVD88 geoid or a VDatum xGEOID model."""
        target_geoid = (
            target_geoid.split(":")[-1] if ":" in target_geoid else target_geoid
        ).casefold()

        if target_geoid.startswith("xgeoid"):
            grid = self._get_grid("vdatum", target_geoid)
            if np.isfinite(grid).any():
                return grid, target_geoid
            raise MissingGridError(
                f"xGEOID '{target_geoid}' lacks coverage or failed to download."
            )

        us_geoids = ["g2018", "g2012b", "geoid09"]
        geoids_to_try = (
            us_geoids[us_geoids.index(target_geoid) :]
            if target_geoid in us_geoids
            else [target_geoid]
        )

        for geoid in geoids_to_try:
            try:
                grid = self._get_grid("proj", geoid)
                if np.isfinite(grid).any():
                    if geoid != target_geoid and self.verbose:
                        logger.info(
                            "    [Geoid Fallback] '%s' lacks coverage here. "
                            "Falling back to '%s'.",
                            target_geoid,
                            geoid,
                        )
                    return grid, geoid
            except MissingGridError:
                continue

        raise MissingGridError(
            f"Geoid '{target_geoid}' and fallbacks lack coverage or failed to download."
        )

    def _fetch_dist2coast_m(self) -> Optional[np.ndarray]:
        logger.info("    [Coastline] Fetching Dist2Coast signed distance field...")

        try:
            d2c_files = self.fetch_grid("dist2coast", variant="base")
            if not d2c_files:
                logger.warning(
                    "    [Coastline] Dist2Coast fetch failed. No coastal context applied."
                )
                return None

            nc_path = f"netcdf:{d2c_files[0]}:dist"
            d2c_grid = GridEngine.load_and_interpolate(
                [nc_path],
                self.region,
                self.nx,
                self.ny,
                decay_pixels=0,
                preserve_zero=True,
            )

            unit = ""
            try:
                with rasterio.open(nc_path) as src:
                    if src.units and src.units[0]:
                        unit = str(src.units[0]).strip().casefold()
                    if not unit:
                        unit = str(src.tags(1).get("units", "")).strip().casefold()
                    if not unit:
                        unit = str(src.tags().get("units", "")).strip().casefold()
            except Exception as exc:
                logger.debug(
                    "    [Coastline] Could not inspect Dist2Coast units: %s", exc
                )

            if unit in {"m", "meter", "meters", "metre", "metres"}:
                scale = 1.0
            elif unit in {
                "km",
                "kilometer",
                "kilometers",
                "kilometre",
                "kilometres",
            }:
                scale = 1000.0
            else:
                scale = 1000.0
                logger.warning(
                    "    [Coastline] Dist2Coast units unknown; assuming kilometers."
                )

            return d2c_grid.astype(np.float32) * scale

        except Exception as exc:
            logger.error(
                "    [Coastline] Failed to generate Dist2Coast distance field: %s",
                exc,
            )
            return None

    def _fetch_coastal_context(
        self,
        vdatum_grid: Optional[np.ndarray] = None,
    ) -> Optional[CoastalContext]:
        d2c_m = self._fetch_dist2coast_m()
        if d2c_m is None:
            return None

        valid_vdatum = np.isfinite(vdatum_grid) if vdatum_grid is not None else None
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
                "    [Coastline] Effective water mask includes %d VDatum cells "
                "beyond native water.",
                extension_count,
            )

        return context

    def fetch_global_chain(
        self,
        datum_name: str,
        model: str = "fes2014",
    ) -> Tuple[np.ndarray, str]:
        """Build shift: global tidal reference -> WGS84-native ellipsoid."""
        datum_name = datum_name.split(":")[-1] if ":" in datum_name else datum_name
        tidal_shift = np.zeros((self.ny, self.nx), dtype=np.float32)
        desc: list[str] = []

        try:
            mss_grid = self._get_grid("transformez.dtu", "mss25")
            if np.isfinite(mss_grid).any():
                desc.append("DTU25_MSS")
        except Exception:
            return np.zeros((self.ny, self.nx), dtype=np.float32), "Global Chain Failed"

        if datum_name in ("lat", "hat"):
            try:
                lat_grid = self._get_grid("seanoe", "lat")
                if np.nanmean(lat_grid) > 0:
                    lat_grid *= -1.0
                tidal_shift += lat_grid if datum_name == "lat" else lat_grid * -1.0
                desc.append(f"Global({datum_name.upper()})")
            except Exception:
                pass

        # Intentionally do not fill global-model NaNs here. Missing global coverage
        # remains missing until the coastal compositor decides how it may be used.
        return mss_grid + tidal_shift, " + ".join(desc)

    def _vdatum_registry(self) -> dict[str, str]:
        return parse_vdatum_registry(self.cache_dir / "vdatum" / "tidal_area.inf")

    @staticmethod
    def _coverage_metadata(grid_path: Path) -> dict[str, str]:
        """Read metadata belonging to one extracted VDatum coverage package."""
        for met_path in sorted(grid_path.parent.glob("*.met")):
            metadata = parse_vdatum_registry(met_path)
            if metadata:
                return metadata
        return {}

    def _load_single_grid(self, path: Path) -> np.ndarray:
        return GridEngine.load_and_interpolate(
            [path],
            self.region,
            self.nx,
            self.ny,
        )

    def _fetch_vdatum_entries(
        self,
        datatype: str,
    ) -> list[dict[str, Any]]:
        """Run Fetchez VDatum directly and preserve result metadata."""

        module = VDatum(
            src_region=self.region,
            outdir=str(self.cache_dir),
            datatype=datatype,
        )

        module.run()

        if not module.results:
            return []

        results = run_fetchez(
            [module],
            threads=2,
            ignore_failures=False,
        )

        entries: list[dict[str, Any]] = []

        for _owner, entry in results or []:
            if entry.get("status", 0) != 0:
                continue

            logger.debug(
                "Fetchez entry: %r",
                entry,
            )
            dst_fn = entry.get("dst_fn")
            if not dst_fn:
                continue

            entries.append(entry)

        return entries

    def _fetch_vdatum_model_grid(
        self,
        model_name: str,
    ) -> np.ndarray:
        entries = self._fetch_vdatum_entries(model_name)

        if not entries:
            raise MissingGridError(f"VDatum model '{model_name}' is unavailable.")

        grid_paths: list[Path] = []

        for entry in entries:
            archive_path = Path(entry["dst_fn"])

            archive_member = entry.get("archive_member")
            if not archive_member:
                archive_member = entry.get("metadata", {}).get("archive_member")

            logger.debug(
                "VDatum model %s entry: archive=%s member=%s",
                model_name,
                archive_path,
                archive_member,
            )

            if archive_path.suffix.casefold() == ".zip":
                if not archive_member:
                    logger.warning(
                        "VDatum model %s returned no archive member for %s.",
                        model_name,
                        archive_path.name,
                    )
                    continue

                try:
                    with zipfile.ZipFile(archive_path, "r") as archive:
                        members = archive.namelist()

                        # Normalize separators because NOAA metadata may use
                        # Windows-style paths while ZIP members use '/'.
                        wanted = archive_member.replace("\\", "/").casefold()

                        matched_member = next(
                            (
                                member
                                for member in members
                                if member.replace("\\", "/").casefold() == wanted
                            ),
                            None,
                        )

                        # Be tolerant if Fetchez stores the path relative to an
                        # internal VDatum root instead of the ZIP root.
                        if matched_member is None:
                            matched_member = next(
                                (
                                    member
                                    for member in members
                                    if member.replace("\\", "/")
                                    .casefold()
                                    .endswith(wanted)
                                ),
                                None,
                            )

                        if matched_member is None:
                            logger.warning(
                                "VDatum model %s archive member not found: %s",
                                model_name,
                                archive_member,
                            )
                            continue

                        archive.extract(
                            matched_member,
                            path=self.cache_dir,
                        )

                        grid_path = self.cache_dir / matched_member

                        if grid_path.exists() and grid_path.suffix.casefold() == ".gtx":
                            grid_paths.append(grid_path)

                            logger.debug(
                                "Extracted VDatum model %s component: %s",
                                model_name,
                                grid_path,
                            )

                except zipfile.BadZipFile as exc:
                    raise MissingGridError(
                        f"VDatum model archive is corrupt: {archive_path}"
                    ) from exc

            elif archive_path.suffix.casefold() == ".gtx":
                grid_paths.append(archive_path)

        if not grid_paths:
            raise MissingGridError(
                f"VDatum model '{model_name}' produced no usable GTX grids."
            )

        return GridEngine.load_and_interpolate(
            grid_paths,
            self.region,
            self.nx,
            self.ny,
        )

    def _fetch_vdatum_coverage_paths(
        self,
        datum_name: str,
    ) -> list[tuple[Path | None, Path]]:
        """Return coherent tidal/TSS pairs from the same VDatum packages.

        A tidal-datum query already selects the regional VDatum packages that
        intersect the requested region. Extract the requested tidal grid and
        ``tss.gtx`` from those *same archives* rather than performing an
        independent TSS search and trying to join the two result sets later.
        This preserves package-level provenance across VDatum generations.
        """
        registry = self._vdatum_registry()

        if datum_name in {"msl", "lmsl", "5714"}:
            files = self.fetch_grid(
                "vdatum",
                datatype="tss",
                query="tss",
                extract_names=["tss", ".met", ".inf"],
            )

            tss_files = [path for path in files if vdatum_grid_datum(path) == "tss"]
            pairs: list[tuple[Path | None, Path]] = [(None, path) for path in tss_files]

        else:
            files = self.fetch_grid(
                "vdatum",
                datatype=datum_name,
                query=datum_name,
                extract_names=[datum_name, "tss", ".met", ".inf"],
            )

            tidal_by_coverage: dict[str, Path] = {}
            tss_by_coverage: dict[str, Path] = {}

            for path in files:
                if path.suffix.casefold() != ".gtx":
                    continue

                coverage_id = path.parent.name
                grid_datum = vdatum_grid_datum(path)

                if grid_datum == datum_name.casefold():
                    tidal_by_coverage[coverage_id] = path
                elif grid_datum == "tss":
                    tss_by_coverage[coverage_id] = path

            coverage_ids = sorted(set(tidal_by_coverage) | set(tss_by_coverage))

            pairs = []
            for coverage_id in coverage_ids:
                tidal_path = tidal_by_coverage.get(coverage_id)
                tss_path = tss_by_coverage.get(coverage_id)

                if tidal_path is None or tss_path is None:
                    logger.warning(
                        "VDatum coverage %s is incomplete for %s "
                        "(tidal=%s, tss=%s); skipping.",
                        coverage_id,
                        datum_name,
                        tidal_path is not None,
                        tss_path is not None,
                    )
                    continue

                pairs.append((tidal_path, tss_path))

        def pair_priority(pair: tuple[Path | None, Path]):
            tidal_path, tss_path = pair
            priority_path = tidal_path or tss_path
            priority_name = datum_name if tidal_path is not None else "tss"
            return vdatum_priority(priority_path, priority_name, registry)

        pairs.sort(key=pair_priority, reverse=True)

        for index, (tidal_path, tss_path) in enumerate(pairs, start=1):
            priority_path = tidal_path or tss_path
            release, neg_area, _ = pair_priority((tidal_path, tss_path))
            logger.debug(
                "VDatum %s coverage priority %d: %s (release=%s, area=%s)",
                datum_name,
                index,
                priority_path.parent.name,
                release.date() if getattr(release, "year", 1) > 1 else "unknown",
                -neg_area if np.isfinite(neg_area) else "unknown",
            )

        return pairs

    def _frame_shift_to_target(
        self,
        source_frame: str,
        target_frame: str,
        epoch_in: str | None = None,
        epoch_out: str | None = None,
    ) -> np.ndarray:
        """Generate an HTDP ellipsoidal shift between two bound native frames."""
        if source_frame.casefold() == target_frame.casefold():
            return np.zeros((self.ny, self.nx), dtype=np.float32)

        source = HTDP_FRAME_BINDINGS.get(source_frame)
        target = HTDP_FRAME_BINDINGS.get(target_frame)

        if source is None or target is None:
            raise MissingGridError(
                "Missing HTDP frame binding for VDatum normalization: "
                f"{source_frame} -> {target_frame}"
            )

        return self.htdp_tool.run_grid(
            region=self.region,
            nx=self.nx,
            ny=self.ny,
            frame_id_in=source.htdp_id,
            frame_id_out=target.htdp_id,
            epoch_in=epoch_in or str(source.reference_epoch),
            epoch_out=epoch_out or str(target.reference_epoch),
        )

    def _fetch_bound_reference_grid(self, reference_id: str) -> tuple[np.ndarray, str]:
        """Fetch a model grid using its operation binding."""
        binding = OPERATION_BINDINGS.get(reference_id.casefold())
        if binding is None:
            raise MissingGridError(
                f"No operation binding exists for VDatum reference '{reference_id}'."
            )
        if not binding.provider_datum:
            raise MissingGridError(
                f"VDatum reference '{reference_id}' has no provider datum."
            )

        grid = self._get_grid(binding.provider, binding.provider_datum)
        return grid, binding.provider_datum

    def _normalize_vdatum_coverage(
        self,
        datum_name: str,
        tidal_path: Path | None,
        tss_path: Path,
        canonical_geoid: np.ndarray,
        canonical_frame: str,
    ) -> tuple[np.ndarray, str]:
        """Normalize one coherent VDatum coverage to the common NAVD88-like hub.

        The returned array is the tidal/LMSL shift expressed relative to the
        canonical orthometric working surface associated with ``canonical_geoid``.
        All VDatum generations are therefore comparable before mosaicing.
        """
        tss = self._load_single_grid(tss_path)
        if np.isnan(tss).all() or (tss == 0).all():
            return np.full((self.ny, self.nx), np.nan, dtype=np.float32), "TSS Empty"

        if tidal_path is None:
            tidal_to_tss = -tss
        else:
            tidal = self._load_single_grid(tidal_path)
            if np.isnan(tidal).all() or (tidal == 0).all():
                return (
                    np.full((self.ny, self.nx), np.nan, dtype=np.float32),
                    "Tidal Empty",
                )
            tidal_to_tss = tidal - tss

        metadata = self._coverage_metadata(tss_path)
        horz = metadata.get("horz", "NAD83").strip().upper()

        try:
            tss_ref = tss_reference({"horz": horz})
        except Exception as exc:
            raise MissingGridError(
                f"Unsupported VDatum TSS roadmap for coverage "
                f"'{tss_path.parent.name}' (horz={horz!r})."
            ) from exc

        # Legacy VDatum TSS is already LMSL -> NAVD88, which is exactly the
        # canonical hydro working surface expected by the coastal compositor.
        if tss_ref.casefold() in {"epsg:5703", "vdatum:navd88"}:
            return tidal_to_tss, f"{tss_path.parent.name}:NAVD88"

        # Modern VDatum TSS points to an xGEOID reference. Complete the package's
        # own chain to its native ellipsoid first.
        xgeoid_binding = OPERATION_BINDINGS.get(tss_ref.casefold())
        if xgeoid_binding is None:
            raise MissingGridError(
                f"No operation binding exists for TSS reference '{tss_ref}'."
            )
        if not xgeoid_binding.native_frame:
            raise MissingGridError(
                f"TSS reference '{tss_ref}' has no native ellipsoidal frame."
            )

        xgeoid_grid, xgeoid_model = self._fetch_bound_reference_grid(tss_ref)
        ellipsoid_shift = tidal_to_tss + xgeoid_grid

        # Normalize the coverage's ellipsoidal frame to the common Transformez
        # VDatum hub (currently NAD83(2011) for tidal bindings).
        frame_shift = self._frame_shift_to_target(
            xgeoid_binding.native_frame,
            canonical_frame,
        )
        ellipsoid_shift += frame_shift

        # Convert the common-frame ellipsoidal shift back to the canonical
        # orthometric working surface. This makes modern xGEOID and legacy
        # NAVD88 TSS coverages directly comparable before mosaicing.
        normalized_hydro = ellipsoid_shift - canonical_geoid

        return (
            normalized_hydro,
            f"{tss_path.parent.name}:{tss_ref.split(':')[-1]}"
            f"->{xgeoid_binding.native_frame}->{canonical_frame}"
            f"[{xgeoid_model}]",
        )

    def _build_vdatum_hydro_mosaic(
        self,
        datum_name: str,
        canonical_geoid: np.ndarray,
        canonical_frame: str,
    ) -> tuple[np.ndarray, list[str]]:
        """Build a priority mosaic from complete, normalized VDatum coverages."""
        pairs = self._fetch_vdatum_coverage_paths(datum_name)
        if not pairs:
            raise MissingGridError(
                f"No coherent VDatum coverage packages found for '{datum_name}'."
            )

        mosaic = np.full((self.ny, self.nx), np.nan, dtype=np.float32)
        descriptions: list[str] = []

        for index, (tidal_path, tss_path) in enumerate(pairs):
            coverage_grid, coverage_desc = self._normalize_vdatum_coverage(
                datum_name,
                tidal_path,
                tss_path,
                canonical_geoid,
                canonical_frame,
            )

            valid = np.isfinite(coverage_grid)
            write_mask = valid & ~np.isfinite(mosaic)
            contribution = np.count_nonzero(write_mask)

            # Always accept the highest-priority coverage.
            # Lower-priority coverages must contribute a meaningful number
            # of cells before they are allowed to fill gaps.
            if index > 0 and contribution < MIN_VDATUM_FALLBACK_CELLS:
                logger.debug(
                    "VDatum coverage %s skipped: only %d fallback cells.",
                    tss_path.parent.name,
                    contribution,
                )
                continue

            mosaic[write_mask] = coverage_grid[write_mask]

            if contribution:
                descriptions.append(coverage_desc)
                logger.debug(
                    "VDatum coverage %s contributed %d cells.",
                    tss_path.parent.name,
                    contribution,
                )

        return mosaic, descriptions

    def fetch_vdatum_chain(
        self,
        datum_name: str,
        requested_geoid_name: Optional[str],
    ) -> Tuple[Optional[np.ndarray], str]:
        """Build a VDatum tidal shift normalized to the binding's native frame."""
        datum_name = datum_name.split(":")[-1] if ":" in datum_name else datum_name
        datum_name = datum_name.casefold()
        desc: list[str] = []

        tidal_binding = OPERATION_BINDINGS.get(f"vdatum:{datum_name}")
        if tidal_binding is None:
            raise MissingGridError(
                f"No operation binding exists for 'vdatum:{datum_name}'."
            )
        if not tidal_binding.native_frame:
            raise MissingGridError(
                f"VDatum binding 'vdatum:{datum_name}' has no native frame."
            )

        canonical_frame = tidal_binding.native_frame
        default_geoid = tidal_binding.default_model or "geoid:g2018"
        actual_geoid = requested_geoid_name or default_geoid

        try:
            geoid_grid, used_geoid = self.fetch_geoid(actual_geoid)
        except MissingGridError:
            return None, "Geoid Missing"

        try:
            hydro_shift, coverage_desc = self._build_vdatum_hydro_mosaic(
                datum_name,
                geoid_grid,
                canonical_frame,
            )
        except MissingGridError as exc:
            logger.error("Failed to build VDatum coverage mosaic: %s", exc)
            return None, str(exc)

        if coverage_desc:
            desc.append("VDatum[" + ", ".join(coverage_desc) + "]")
        desc.append(f"Geoid({used_geoid}->{canonical_frame})")

        # Coastal/global fallback operates on the normalized hydro surface, so
        # every VDatum generation now has identical semantics at this point.
        if np.isnan(hydro_shift).any():
            coastal_context = self._fetch_coastal_context(hydro_shift)

            proxy_id = tidal_binding.global_proxy
            proxy_datum = proxy_id.split(":", 1)[1] if proxy_id else None
            global_shift: Optional[np.ndarray] = None

            if self.use_stations:
                rbf_grid = GridGen.from_stations(
                    self.region,
                    self.nx,
                    self.ny,
                    datum_in=datum_name,
                    datum_out="msl",
                )
                if rbf_grid is not None:
                    global_shift, _ = self.fetch_global_chain("mss", model="fes2014")
                    if global_shift is not None and np.isfinite(global_shift).any():
                        global_binding = OPERATION_BINDINGS.get("global:mss")
                        global_frame = (
                            global_binding.native_frame
                            if global_binding and global_binding.native_frame
                            else "EPSG:7662"
                        )
                        frame_shift = self._frame_shift_to_target(
                            global_frame,
                            canonical_frame,
                            epoch_in=str(self.epoch_in),
                            epoch_out="2010.0",
                        )
                        global_native = global_shift + frame_shift
                        combined_shift = rbf_grid + (global_native - geoid_grid)
                        missing = np.isnan(hydro_shift)
                        hydro_shift[missing] = combined_shift[missing]
                        hydro_shift = GridEngine.fill_nans(
                            hydro_shift,
                            decay_pixels=self.decay_pixels,
                            buffer_pixels=10,
                            coastal_context=coastal_context,
                            decay_distance_m=self.decay_distance_m,
                            buffer_distance_m=self.buffer_distance_m,
                            extrapolate_inland=self.extrapolate_inland,
                        )
                        desc.append("Station RBF + Global MSS + Inland Decay")

            elif proxy_datum:
                global_shift, _ = self.fetch_global_chain(
                    proxy_datum,
                    model="fes2014",
                )
                if (
                    global_shift is not None
                    and np.isfinite(global_shift).any()
                    and proxy_id is not None
                ):
                    global_binding = OPERATION_BINDINGS.get(proxy_id)
                    global_frame = (
                        global_binding.native_frame
                        if global_binding and global_binding.native_frame
                        else "EPSG:7662"
                    )
                    frame_shift = self._frame_shift_to_target(
                        global_frame,
                        canonical_frame,
                        epoch_in=str(self.epoch_in),
                        epoch_out="2010.0",
                    )
                    global_native = global_shift + frame_shift

                    hydro_shift = GridEngine.coastal_aware_composite(
                        vdatum_grid=hydro_shift,
                        global_grid=global_native - geoid_grid,
                        nx=self.nx,
                        ny=self.ny,
                        coastal_context=coastal_context,
                        decay_pixels=self.decay_pixels,
                        buffer_pixels=10,
                        decay_distance_m=self.decay_distance_m,
                        buffer_distance_m=self.buffer_distance_m,
                    )
                    desc.append(f"Blended w/ Global({proxy_datum.upper()})")

            if (
                not proxy_datum
                or global_shift is None
                or not np.isfinite(global_shift).any()
            ):
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
