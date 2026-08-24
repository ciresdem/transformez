#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.utils
~~~~~~~~~~~~~

This holds various utility functions.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import subprocess
import logging
import shlex
from typing import Tuple, Optional, Union, List

import numpy as np
import rasterio
import shutil

logger = logging.getLogger(__name__)


def cmd_exists(x: str) -> bool:
    """Check if a command exists in the system PATH.

    Args:
        x: Command name.

    Returns:
        True if command is executable, False otherwise.
    """

    return any(
        os.access(os.path.join(path, x), os.X_OK)
        for path in os.environ["PATH"].split(os.pathsep)
    )


def run_cmd(args: Union[str, List[str], Tuple[str, ...]]) -> Tuple[str, int]:
    """Standalone replacement for utils.run_cmd using subprocess.

    Securely handles strings, lists, and single-item tuples by
    tokenizing them before execution.
    """

    if isinstance(args, (tuple, list)) and len(args) == 1 and isinstance(args[0], str):
        args = args[0]

    if isinstance(args, str):
        cmd_list = shlex.split(args)
    else:
        cmd_list = list(args)

    logger.debug(f"Running: {' '.join(cmd_list)}")

    result = subprocess.run(
        cmd_list,
        shell=False,
        capture_output=True,
        text=True,
    )
    return (result.stdout, result.returncode)


def cmd_check(cmd_str: str, cmd_vers_str: str) -> bytes:
    """Check system for availability of command.

    Args:
        cmd_str: Command to check.
        cmd_vers_str: Version check command.

    Returns:
        Version string or b"0" if not found.
    """

    if cmd_exists(cmd_str):
        cmd_vers, status = run_cmd((cmd_vers_str,))
        return (
            cmd_vers.rstrip().encode()
            if isinstance(cmd_vers, str)
            else cmd_vers.rstrip()
        )
    return b"0"


class RasterQuery:
    """Raster query for point clouds.

    Pre-loads raster data and inverse transform to rapidly query (X, Y) arrays.
    """

    def __init__(self, filename: str, default_nodata: float = 0.0):
        """Initialize RasterQuery.

        Args:
            filename: Path to raster file.
            default_nodata: Value to use for nodata pixels.

        Raises:
            FileNotFoundError: If file doesn't exist.
        """

        if not filename or not os.path.exists(filename):
            raise FileNotFoundError(f"Raster not found: {filename}")

        self.default_nodata = default_nodata

        with rasterio.open(filename) as src:
            self.data = src.read(1)
            self.transform = src.transform
            self.inv_transform = ~src.transform
            self.bounds = src.bounds
            self.width = src.width
            self.height = src.height

            if src.nodata is not None:
                self.data[self.data == src.nodata] = self.default_nodata
            self.data = np.nan_to_num(self.data, nan=self.default_nodata)

    def query(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        """Query the raster at given X, Y numpy arrays.

        Argxs:
            x: X coordinates.
            y: Y coordinates.

        Returns:
            Array of values at queried locations.
        """

        q_x = np.asarray(x).copy()
        q_y = np.asarray(y)

        if self.bounds.left < 0 and np.any(q_x > 180):
            q_x = np.where(q_x > 180, q_x - 360, q_x)
        elif self.bounds.left >= 0 and np.any(q_x < 0):
            q_x = np.where(q_x < 0, q_x + 360, q_x)

        cols_f, rows_f = self.inv_transform * (q_x, q_y)

        cols = np.floor(cols_f).astype(int)
        rows = np.floor(rows_f).astype(int)

        valid = (rows >= 0) & (rows < self.height) & (cols >= 0) & (cols < self.width)

        results = np.full_like(q_x, self.default_nodata, dtype=self.data.dtype)
        if np.any(valid):
            results[valid] = self.data[rows[valid], cols[valid]]

        return results


def export_cache(
    cache_dir: Optional[str] = None, output_name: str = "transformez_offline_cache"
) -> Optional[str]:
    """Pack the local transformez cache into a ZIP file.

    Args:
        cache_dir: Path to cache directory. Defaults to ./transformez_cache.
        output_name: Name for the output ZIP file.

    Returns:
        Path to created ZIP file, or None if failed.
    """

    if cache_dir is None:
        cache_dir = os.path.join(os.getcwd(), "transformez_cache")

    if not os.path.exists(cache_dir):
        logger.error(f"[EXPORT FATAL] Cache directory not found at: {cache_dir}")
        logger.error("Run a transformation to populate the cache before exporting.")
        return None

    out_path = os.path.abspath(output_name)

    logger.info("-" * 60)
    logger.info(f"Packing offline cache bundle from: {cache_dir}")
    logger.info(
        "This may take a minute depending on the size of your downloaded grids..."
    )

    try:
        zip_path = shutil.make_archive(out_path, "zip", cache_dir)
        size_mb = os.path.getsize(zip_path) / (1024 * 1024)

        logger.info(
            f"Successfully exported offline cache bundle: {zip_path} ({size_mb:.1f} MB)"
        )
        logger.info("-" * 60)
        return zip_path

    except Exception as e:
        logger.error(f"[EXPORT FATAL] Failed to export cache: {e}")
        return None
