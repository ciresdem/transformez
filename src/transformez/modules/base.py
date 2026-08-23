#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.modules.base
~~~~~~~~~~~~~

Base FetchezModule for use in transformez for subsetting rasters using vsicurl

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import logging
from typing import Any
from contextlib import contextmanager
from pathlib import Path
import rasterio
from rasterio.windows import from_bounds
from rasterio.transform import Affine
from fetchez.modules.base import FetchModule
from fetchez.core import DEFAULT_USER_AGENT

logger = logging.getLogger(__name__)


@contextmanager
def silence_c_spam():
    """Temporarily redirects OS-level stderr to /dev/null to silence HDF5 C-library spam."""

    stderr_fd = 2  # Standard error file descriptor
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    old_stderr = os.dup(stderr_fd)
    try:
        os.dup2(devnull_fd, stderr_fd)
        yield
    finally:
        os.dup2(old_stderr, stderr_fd)
        os.close(devnull_fd)
        os.close(old_stderr)


class TransformezModule(FetchModule):
    """Base module for Transformez plugins that extract spatial subsets
    from remote HTTP NetCDF or GeoTIFF files using GDAL /vsicurl/.
    """

    def fetch_entry(
        self,
        entry: Any,
        check_size: bool = True,
        retries: int = 5,
        verbose: bool = True,
    ) -> int:
        """Standardized /vsicurl/ windowed subset fetcher."""

        dst_fn = Path(entry["dst_fn"])

        if dst_fn.exists() and dst_fn.stat().st_size > 0:
            logger.debug(f"[{self.name}] Subset already cached: {dst_fn.name}")
            return 0

        dst_fn.parent.mkdir(parents=True, exist_ok=True)

        url = entry["url"]
        fmt = entry.get("format", "geotiff").lower()
        var_name = entry.get("var_name")
        buffer_deg = entry.get("buffer", 0.1)
        grid_bounds = entry.get("grid_bounds", (-180.0, -90.0, 180.0, 90.0))

        try:
            if fmt in ["netcdf", "nc"]:
                vsi_url = (
                    f"netcdf:/vsicurl/{url}:{var_name}"
                    if var_name
                    else f"/vsicurl/{url}"
                )
            else:
                vsi_url = f"/vsicurl/{url}"

            logger.info(f"[{self.name}] Streaming metadata and extracting subset...")

            env_kwargs = {
                "GDAL_HTTP_USERAGENT": DEFAULT_USER_AGENT,
                "CPL_VSIL_CURL_USE_HEAD": "NO",
                "GDAL_DISABLE_READDIR_ON_OPEN": "YES",
                "HDF5_USE_FILE_LOCKING": "FALSE",
            }

            with rasterio.Env(**env_kwargs):
                with silence_c_spam():
                    with rasterio.open(vsi_url) as src:
                        w, e, s, n = self.wgs_region

                        transform = src.transform
                        if transform.is_identity:
                            logger.debug(
                                f"[{self.name}] Generating missing geotransform..."
                            )
                            gx_min, gy_min, gx_max, gy_max = grid_bounds
                            res_x = (gx_max - gx_min) / src.width
                            res_y = (gy_min - gy_max) / src.height
                            transform = Affine.translation(
                                gx_min, gy_max
                            ) * Affine.scale(res_x, res_y)

                        gx_min = grid_bounds[0]
                        if gx_min >= 0 and w < 0:
                            w += 360.0
                            e += 360.0

                        window = (
                            from_bounds(
                                w - buffer_deg,
                                s - buffer_deg,
                                e + buffer_deg,
                                n + buffer_deg,
                                transform=transform,
                            )
                            .round_lengths()
                            .round_offsets()
                        )

                        # desc_str = f"[{self.name}] Streaming {window.width}x{window.height} subset"
                        # with tqdm(total=1, desc=desc_str, bar_format="{l_bar}{bar}| [{elapsed}]") as pbar:
                        data_chunk = src.read(1, window=window)
                        #    pbar.update(1)

                        chunk_transform = rasterio.windows.transform(window, transform)

                        profile = src.profile.copy()
                        profile.pop("blockxsize", None)
                        profile.pop("blockysize", None)
                        profile.pop("tiled", None)

                        profile.update(
                            {
                                "driver": "GTiff",
                                "height": window.height,
                                "width": window.width,
                                "transform": chunk_transform,
                                "compress": "deflate",
                            }
                        )

                        with rasterio.open(dst_fn, "w", **profile) as dst:
                            dst.write(data_chunk, 1)

            logger.info(
                f"[{self.name}] Successfully cached remote subset to {dst_fn.name}"
            )
            return 0

        except Exception as e:
            logger.error(f"[{self.name}] Remote subset failed: {e}")
            return -1
