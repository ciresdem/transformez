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

import sys
import os
import subprocess
import tempfile
import shutil
import logging
import urllib.request
import zipfile
import numpy as np
from typing import Tuple, Optional, Any

from .definitions import Datums  # Required for ID lookups

logger = logging.getLogger(__name__)


def resolve_htdp_path(version: str = "3.5.0") -> Optional[str]:
    """Find the HTDP executable, prioritizing the local cache over system PATH.

    Args:
        version: HTDP version string (e.g., '3.5.0').

    Returns:
        Path to HTDP binary, or None if not found.
    """

    clean_version = version.replace("v", "")
    ae = ".exe" if sys.platform == "win32" else ""

    # Check local transformez_cache/bin/
    cache_bin = os.path.join(
        os.getcwd(), "transformez_cache", "bin", f"htdp_{clean_version}{ae}"
    )
    if os.path.exists(cache_bin):
        return cache_bin

    if shutil.which(f"htdp{ae}"):
        return f"htdp{ae}"

    return None


class HTDP:
    """Wrapper for the NGS HTDP software."""

    def __init__(
        self,
        htdp_bin: Optional[str] = "htdp",
        version: str = "3.5.0",
        verbose: bool = True,
    ):
        self.version = version
        self.verbose = verbose
        self.htdp_bin: Optional[str] = htdp_bin or resolve_htdp_path(self.version)
        self.has_htdp: bool = self.htdp_bin is not None

        if not self.has_htdp:
            logger.error(
                f"HTDP {self.version} is not installed or not in PATH. "
                f"Run 'transformez htdp install --version {self.version}'"
            )

    def run_grid(
        self,
        region: Any,
        nx: int,
        ny: int,
        epsg_in: int,
        epsg_out: int,
        epoch_in: str,
        epoch_out: str,
    ) -> np.ndarray:
        """Main entry point called by transform.py.
        Generates a shift grid between two frames.

        Args:
            region: Geographic region object with xmin/xmax/ymin/ymax.
            nx: Number of pixels along x-axis.
            ny: Number of pixels along y-axis.
            epsg_in: Source EPSG code.
            epsg_out: Target EPSG code.
            epoch_in: Source epoch string.
            epoch_out: Target epoch string.

        Returns:
            2D shift grid (ny, nx). Zeros if HTDP unavailable.
        """

        if not self.has_htdp:
            logger.warning("HTDP missing. Returning zero shift.")
            return np.zeros((ny, nx))

        # Create a coarse (max 50x50) grid for htpd calculations.
        coarse_nx = min(nx, 50)
        coarse_ny = min(ny, 50)

        # Look up HTDP numeric IDs (e.g., NAD83=1, WGS84=10)
        # transform.py passes ints (EPSGs), we need HTDP internal IDs
        def get_id(epsg: int) -> int:
            if epsg in Datums.HTDP:
                return Datums.HTDP[epsg]["htdp_id"]
            # Fallback for common codes if not in dictionary
            if epsg == 6319:
                return 1  # NAD83(2011)
            if epsg == 4979:
                return 10  # WGS84(G1762)
            raise ValueError(f"EPSG {epsg} not defined in HTDP dictionary.")

        try:
            id_in = get_id(epsg_in)
            id_out = get_id(epsg_out)
        except ValueError as e:
            logger.error(e)
            return np.zeros((ny, nx))

        # Create Temporary Workspace
        with tempfile.TemporaryDirectory() as tmpdir:
            in_fn = os.path.join(tmpdir, "htdp_in.txt")
            out_fn = os.path.join(tmpdir, "htdp_out.txt")
            ctl_fn = os.path.join(tmpdir, "htdp.inp")

            # The output Z will be the shift.
            lons = np.linspace(region.xmin, region.xmax, coarse_nx)
            lats = np.linspace(region.ymin, region.ymax, coarse_ny)

            # Write input file
            with open(in_fn, "w") as f:
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
                ctl_fn, out_fn, in_fn, id_in, epoch_in, id_out, epoch_out
            )

            # Run HTDP
            self.run_cmd(ctl_fn)

            # Parse Output & Build Grid
            if not os.path.exists(out_fn):
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
            # grid = self._read_grid(out_fn, (ny, nx))
            # return grid

    def _read_grid(self, filename: str, shape: Tuple[int, int]) -> np.ndarray:
        """Parse HTDP output, mapping PNT_x_y tags to grid indices.

        Args:
            filename: Path to HTDP output file.
            shape: Target grid shape (ny, nx).

        Returns:
            2D numpy array of height values.
        """

        grid = np.zeros(shape)
        with open(filename, "r") as f:
            for line in f:
                if "PNT_" not in line:
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

                except (ValueError, IndexError, StopIteration):
                    continue

        return grid

    def _write_control(
        self,
        control_fn: str,
        out_fn: str,
        in_fn: str,
        id_in: int,
        epoch_in: str,
        id_out: int,
        epoch_out: str,
    ):
        """Write the batch control file.

        4 = Transform Positions
        2 = Input file
        ID_IN
        ID_OUT
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
            id_in: HTDP source frame ID.
            epoch_in: Source epoch (decimal years).
            id_out: HTDP target frame ID.
            epoch_out: Target epoch (decimal years).
        """

        content = (
            f"4\n"
            f"{out_fn}\n"
            f"{id_in}\n"
            f"{id_out}\n"
            f"2\n"
            f"{epoch_in}\n"
            f"2\n"
            f"{epoch_out}\n"
            f"3\n"
            f"{in_fn}\n"
            f"0\n"
            f"0\n"
        )
        with open(control_fn, "w") as f:
            f.write(content)

    def run_cmd(self, control_fn: Optional[Any] = None) -> bool:
        """Execute the HTDP binary.

        Args:
            control_fn: Path to control file. If None, uses interactive mode.

        Returns:
            True if execution succeeded, False otherwise.
        """

        if not self.htdp_bin:
            logger.error("No HTDP binary available.")
            return False

        if control_fn is None:
            control_fn = 0

        try:
            with open(control_fn, "r") as stdin:
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


def download_htdp(target_dir: Optional[str] = None) -> None:
    """Download HTDP from NOAA NGS.

    On Windows, downloads the pre-compiled executable.
    On Linux/Mac, downloads the source and provides compilation instructions.

    Args:
        target_dir: Directory to download into. Defaults to cwd.
    """

    if target_dir is None:
        target_dir = os.getcwd()

    os.makedirs(target_dir, exist_ok=True)

    if sys.platform == "win32":
        # Windows: Download pre-compiled EXE
        url = "https://geodesy.noaa.gov/TOOLS/Htdp/htdp.exe"
        out_path = os.path.join(target_dir, "htdp.exe")
        logger.info("Downloading HTDP executable for Windows from NOAA...")
        try:
            urllib.request.urlretrieve(url, out_path)
            logger.info(f"Success! Downloaded to: {out_path}")
            logger.info(
                "Please ensure this directory is in your system PATH, or move the file to a PATH directory (e.g., C:\\Windows\\System32)."
            )
        except Exception as e:
            logger.error(f"Failed to download HTDP: {e}")

    else:
        # Linux/Mac: Download Fortran Source
        url = "https://geodesy.noaa.gov/TOOLS/Htdp/HTDP-download.zip"
        zip_path = os.path.join(target_dir, "HTDP-download.zip")
        src_dir = os.path.join(target_dir, "htdp_source")

        logger.info("Downloading HTDP source code for Unix from NOAA...")
        try:
            urllib.request.urlretrieve(url, zip_path)

            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(src_dir)

            os.remove(zip_path)

            logger.info(f"Success! Source code extracted to: {src_dir}")
            logger.info(
                "HTDP requires compilation on Linux/macOS. Run the following commands:"
            )
            print("\n" + "=" * 50)
            print(f"cd {src_dir}")
            print("gfortran -o htdp htdp.f")
            print("sudo mv htdp /usr/local/bin/")
            print("=" * 50 + "\n")

        except Exception as e:
            logger.error(f"Failed to download or extract HTDP source: {e}")


def install_htdp_binary(version: str = "3.5.0") -> None:
    """Download and automatically compile a specific HTDP version from GitHub.

    Args:
        version: HTDP version string (e.g., '3.5.0').
    """

    cache_dir = os.path.join(os.getcwd(), "transformez_cache", "bin")
    os.makedirs(cache_dir, exist_ok=True)

    # Format the GitHub Tag (e.g., "v3.5.0")
    v_tag = f"v{version}" if not version.startswith("v") else version
    clean_version = v_tag.replace("v", "")

    logger.info(f"Downloading HTDP reposity ({v_tag})...")
    url = f"https://github.com/noaa-ngs/HTDP/archive/refs/tags/{v_tag}.zip"
    zip_path = os.path.join(cache_dir, f"htdp_{clean_version}.zip")

    try:
        urllib.request.urlretrieve(url, zip_path)

        if sys.platform == "win32":
            with zipfile.ZipFile(zip_path, "r") as z:
                exe_name = next(name for name in z.namelist() if name.endswith(".exe"))
                extracted_path = z.extract(exe_name, cache_dir)
                exe_path = os.path.join(cache_dir, f"htdp_{clean_version}.exe")

                if os.path.exists(exe_path):
                    os.remove(exe_path)
                shutil.move(extracted_path, exe_path)
        else:
            extract_dir = os.path.join(cache_dir, f"htdp_src_{clean_version}")
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(extract_dir)

            # GitHub extracts to a folder named Repository-Tag (e.g., HTDP-3.5.0)
            source_folder = os.path.join(extract_dir, f"HTDP-{clean_version}")
            fortran_file = os.path.join(source_folder, "htdp.f")
            out_bin = os.path.join(cache_dir, f"htdp_{clean_version}")

            logger.info(f"Compiling HTDP {clean_version} with gfortran...")
            subprocess.run(
                ["gfortran", "-o", out_bin, fortran_file],
                check=True,
                capture_output=True,
            )
            logger.info(f"HTDP compiled successfully to: {out_bin}")

            # Clean up the raw source files
            shutil.rmtree(extract_dir)

        os.remove(zip_path)

    except subprocess.CalledProcessError as e:
        logger.error(f"Compilation failed: {e.stderr.decode() if e.stderr else e}")
    except FileNotFoundError:
        logger.error(
            "'gfortran' not found! Install it (e.g., 'sudo apt install gfortran' "
            "or 'brew install gcc')."
        )
    except Exception as e:
        logger.error(f"Failed to install HTDP {clean_version}: {e}")
