#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.htdp
~~~~~~~~~~~~~

Wrapper for the NGS HTDP (Horizontal Time-Dependent Positioning) software.
Transforms coordinates between reference frames (e.g. NAD83 <-> WGS84).

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import sys
from pathlib import Path
import subprocess
import tempfile
import shutil
import logging
import urllib.request
import zipfile
import numpy as np
from typing import Tuple, Optional, Any, Literal

from .definitions import Datums  # Required for ID lookups

logger = logging.getLogger(__name__)


InstallScope = Literal["user", "project"]
DEFAULT_HTDP_VERSION = "3.6.0"


class HTDPInstallError(RuntimeError):
    pass


def htdp_install_dir(scope: InstallScope = "user") -> Path:
    if scope == "project":
        return project_htdp_dir()

    return user_htdp_dir()


def project_htdp_dir() -> Path:
    return Path.cwd() / "transformez_cache" / "bin"


def user_htdp_dir() -> Path:
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home()))
        return root / "transformez" / "bin"

    return Path.home() / ".local" / "share" / "transformez" / "bin"


def resolve_htdp_path(version: str = "3.6.0") -> Path | None:
    clean_version = version.removeprefix("v.")
    suffix = ".exe" if sys.platform == "win32" else ""

    candidates = [
        project_htdp_dir() / f"htdp_{clean_version}{suffix}",
        user_htdp_dir() / f"htdp_{clean_version}{suffix}",
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    system = shutil.which(f"htdp{suffix}")
    return Path(system) if system else None


def _htdp_release_tag(version: str) -> str:
    clean_version = version.removeprefix("v.").removeprefix("v")

    special_tags = {
        "3.6.0": "v.3.6.0",
    }

    return special_tags.get(clean_version, f"v{clean_version}")


class HTDP:
    """Wrapper for the NGS HTDP software."""

    def __init__(
        self,
        htdp_bin: Optional[str] = None,
        version: str = DEFAULT_HTDP_VERSION,
        verbose: bool = True,
    ):
        self.version = version
        self.verbose = verbose
        self.htdp_bin = htdp_bin or resolve_htdp_path(self.version)
        self.has_htdp: bool = self.htdp_bin is not None

        if not self.has_htdp:
            logger.debug(
                f"HTDP {self.version} is not installed or not in PATH. "
                f"Run 'transformez htdp install --version {self.version}'"
            )

    def _legacy_htdp_id_from_epsg(self, epsg: int) -> int:
        """Look up HTDP numeric IDs (e.g., NAD83=1, WGS84=10)
        transform.py passes ints (EPSGs), we need HTDP internal IDs
        """

        if epsg in Datums.HTDP:
            return Datums.HTDP[epsg]["htdp_id"]
        # Fallback for common codes if not in dictionary
        if epsg == 6319:
            return 1  # NAD83(2011)
        if epsg == 4979:
            return 10  # WGS84(G1762)
        raise ValueError(f"EPSG {epsg} not defined in HTDP dictionary.")

    def run_grid(
        self,
        region: Any,
        nx: int,
        ny: int,
        frame_id_in: int | None,
        frame_id_out: int | None,
        epoch_in: str,
        epoch_out: str,
        epsg_in: int | None = None,
        epsg_out: int | None = None,
    ) -> np.ndarray:
        """Main entry point called by transform.py.
        Generates a shift grid between two frames.

        Args:
            region: Geographic region object with xmin/xmax/ymin/ymax.
            nx: Number of pixels along x-axis.
            ny: Number of pixels along y-axis.
            frame_id_in: Source HTDP Frame ID.
            frame_id_out: Target HTDP Frame ID.
            epoch_in: Source epoch string.
            epoch_out: Target epoch string.
            epsg_in: Source EPSG code. Depreciated.
            epsg_out: Target EPSG code. Depreciated.

        Returns:
            2D shift grid (ny, nx). Zeros if HTDP unavailable.
        """

        if not self.has_htdp:
            raise RuntimeError(
                "HTDP is required for this transformation. "
                "Run 'transformez htdp install'."
            )

        # Create a coarse (max 50x50) grid for htpd calculations.
        coarse_nx = min(nx, 50)
        coarse_ny = min(ny, 50)

        try:
            if frame_id_in is None:
                if epsg_in is None:
                    raise ValueError("frame_id_in or epsg_in is required.")
                frame_id_in = self._legacy_htdp_id_from_epsg(epsg_in)

            if frame_id_out is None:
                if epsg_out is None:
                    raise ValueError("frame_id_out or epsg_out is required.")
                frame_id_out = self._legacy_htdp_id_from_epsg(epsg_out)
        except ValueError as e:
            logger.error(e)
            return np.zeros((ny, nx))

        # Create Temporary Workspace
        with tempfile.TemporaryDirectory() as tmpdir:
            tempdir = Path(tmpdir)

            in_fn = tempdir / "htdp_in.txt"
            out_fn = tempdir / "htdp_out.txt"
            ctl_fn = tempdir / "htdp.inp"

            # The output Z will be the shift.
            lons = np.linspace(region.xmin, region.xmax, coarse_nx)
            lats = np.linspace(region.ymin, region.ymax, coarse_ny)

            # Write input file
            with in_fn.open("w") as f:
                for y_idx, lat in enumerate(lats):
                    for x_idx, lon in enumerate(lons):
                        # "Lat Lon Height TextID"
                        # Convert to HTDP's west-positive longitude convention
                        if lon < 0:
                            htdp_lon = abs(lon)
                        else:
                            htdp_lon = 360.0 - lon
                        f.write(
                            f'{lat:.9f} {htdp_lon:.9f} 0.000 "PNT_{x_idx}_{y_idx}"\n'
                        )

            # Write Control File
            self._write_control(
                ctl_fn, out_fn, in_fn, frame_id_in, epoch_in, frame_id_out, epoch_out
            )

            # Run HTDP
            if not self.run_cmd(ctl_fn):
                raise RuntimeError("HTDP execution failed.")

            # Parse Output & Build Grid
            if not out_fn.exists():
                logger.error("HTDP produced no output.")
                return np.zeros((ny, nx))

            coarse_grid = self._read_grid(out_fn, (coarse_ny, coarse_nx))

            # If we downsampled, stretch the grid back to the requested size
            if coarse_nx != nx or coarse_ny != ny:
                from scipy.ndimage import zoom

                zoom_y = ny / coarse_ny
                zoom_x = nx / coarse_nx
                final_grid = zoom(coarse_grid, (zoom_y, zoom_x), order=1)  # bilinear
                return final_grid

            return coarse_grid

    def _read_grid(self, filename: Path, shape: Tuple[int, int]) -> np.ndarray:
        """Parse HTDP output, mapping PNT_x_y tags to grid indices.

        Args:
            filename: Path to HTDP output file.
            shape: Target grid shape (ny, nx).

        Returns:
            2D numpy array of height values.
        """

        # grid = np.zeros(shape)
        parsed = 0
        outside = 0
        grid = np.full(shape, np.nan, dtype=np.float32)
        with filename.open("r") as f:
            for line in f:
                if "PNT_" not in line:
                    continue

                if "outside of the modeled region" in line:
                    logger.debug("HTDP point outside modeled region: %s", line.rstrip())
                    outside += 1
                    continue

                try:
                    parts = line.replace('"', " ").split()

                    # HTDP Output Format: Lat, Lon, Height, Text
                    idx_off = 1 if parts[0] == "*" else 0

                    height = float(parts[2 + idx_off])

                    # Parse Tag PNT_x_y
                    tag_part = next(p for p in parts if "PNT_" in p)
                    _, x_str, y_str = tag_part.split("_")
                    x, y = int(x_str), int(y_str)

                    if 0 <= y < shape[0] and 0 <= x < shape[1]:
                        grid[y, x] = height
                        parsed += 1

                except (ValueError, IndexError, StopIteration):
                    continue
        if parsed == 0:
            raise RuntimeError(
                f"HTDP produced no transformed points; "
                f"{outside} points were outside the modeled region."
            )
        return grid

    def _write_control(
        self,
        control_fn: Path,
        out_fn: Path,
        in_fn: Path,
        frame_id_in: int,
        epoch_in: str,
        frame_id_out: int,
        epoch_out: str,
    ):
        """Write the batch control file.

        4 = Transform Positions
        2 = Input file
        FRAME_ID_IN
        FRAME_ID_OUT
        2 = Epoch Format (Decimal Years)
        EPOCH_IN
        2 = Epoch Format
        EPOCH_OUT
        3 = Height (Ellipsoid Height)
        IN_FILENAME
        0 = No Velocities
        0 = Standard Output

        Args:
            control_fn: Path for control file output.
            out_fn: Path for HTDP output.
            in_fn: Path to input coordinates file.
            frame_id_in: HTDP source frame ID.
            epoch_in: Source epoch (decimal years).
            frame_id_out: HTDP target frame ID.
            epoch_out: Target epoch (decimal years).
        """

        content = (
            f"4\n"
            f"{out_fn}\n"
            f"{frame_id_in}\n"
            f"{frame_id_out}\n"
            f"2\n"
            f"{epoch_in}\n"
            f"2\n"
            f"{epoch_out}\n"
            f"3\n"
            f"{in_fn}\n"
            f"0\n"
            f"0\n"
        )

        with control_fn.open("w") as f:
            f.write(content)

    def run_cmd(self, control_fn: Path | None = None) -> bool:
        if not self.htdp_bin:
            logger.error("No HTDP binary available.")
            return False

        try:
            if control_fn is None:
                subprocess.run(
                    [self.htdp_bin],
                    stdin=sys.stdin,
                    check=True,
                )
            else:
                with control_fn.open("r") as stdin:
                    subprocess.run(
                        [self.htdp_bin],
                        stdin=stdin,
                        check=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE,
                    )

            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"HTDP runtime error: {e.stderr.decode() if e.stderr else e}")
            return False
        except Exception as e:
            logger.error(f"HTDP runtime error: {e}")
            return False


def install_htdp_binary(
    version: str = DEFAULT_HTDP_VERSION,
    scope: InstallScope = "user",
) -> Path:
    clean_version = version.removeprefix("v.").removeprefix("v")
    tag = _htdp_release_tag(clean_version)

    target_dir = htdp_install_dir(scope)
    target_dir.mkdir(parents=True, exist_ok=True)

    suffix = ".exe" if sys.platform == "win32" else ""
    target_path = target_dir / f"htdp_{clean_version}{suffix}"

    with tempfile.TemporaryDirectory(prefix="transformez-htdp-") as tmpdir:
        build_dir = Path(tmpdir)
        zip_path = build_dir / "htdp.zip"
        extract_dir = build_dir / "source"

        url = f"https://github.com/noaa-ngs/HTDP/archive/refs/tags/{tag}.zip"

        logger.info("Downloading HTDP %s from %s", clean_version, url)
        urllib.request.urlretrieve(url, zip_path)

        with zipfile.ZipFile(zip_path, "r") as archive:
            roots = {
                Path(name).parts[0] for name in archive.namelist() if Path(name).parts
            }

            if len(roots) != 1:
                raise HTDPInstallError(
                    f"Unexpected HTDP archive layout: {sorted(roots)}"
                )

            source_root = next(iter(roots))
            archive.extractall(extract_dir)

        source_dir = extract_dir / source_root

        if sys.platform == "win32":
            exe = next(source_dir.rglob("*.exe"), None)
            if exe is None:
                raise HTDPInstallError(
                    f"HTDP {clean_version} archive contains no executable."
                )
            shutil.copy2(exe, target_path)

        else:
            if shutil.which("make") is None:
                raise HTDPInstallError("'make' is required to build HTDP.")
            if shutil.which("gfortran") is None:
                raise HTDPInstallError("'gfortran' is required to build HTDP.")

            subprocess.run(
                ["make", "all", "FC=gfortran"],
                cwd=source_dir,
                check=True,
                capture_output=True,
            )

            shutil.copy2(source_dir / "htdp", target_path)
            target_path.chmod(target_path.stat().st_mode | 0o111)

    return target_path
