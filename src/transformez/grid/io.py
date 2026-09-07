#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.grid.io
~~~~~~~~~~~~~~~~~~~~~~~

Grid Writing.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any, Mapping

import numpy as np
import rasterio
from rasterio.transform import from_origin

from fetchez.spatial import Region, parse_region


logger = logging.getLogger(__name__)


class GridWriter:
    @staticmethod
    def write(
        filename: str | Path,
        data: np.ndarray,
        region: Region | str,
        crs: Any = "EPSG:4326",
        tags: Optional[Mapping[str, str] | Dict[str, str]] = None,
        transform: Optional[Any] = None,
        nodata: Optional[float] = None,
    ) -> Path:
        """Write a grid to a GeoTIFF.

        Args:
            filename: Output grid filename.
            data: Two-dimensional array to write.
            region: Region used to derive georeferencing when ``transform`` is omitted.
            crs: Coordinate reference system for the output grid.
            tags: Optional metadata tags to write.
            transform: Optional explicit raster transform.
            nodata: Optional nodata value.

        Returns:
            Path to the written GeoTIFF.
        """
        filename = Path(filename).with_suffix(".tif")
        filename.parent.mkdir(parents=True, exist_ok=True)

        rows, cols = data.shape
        if transform is None:
            if isinstance(region, str):
                regions = parse_region(region)
                if not regions:
                    raise ValueError(f"Could not parse region: {region}")
                region = regions[0]
            if isinstance(region, Region):
                xmin, xmax, ymin, ymax = region
            else:
                raise ValueError(f"Could not parse region: {region}")
            res_x = (xmax - xmin) / cols
            res_y = (ymax - ymin) / rows
            transform = from_origin(xmin, ymax, res_x, res_y)

        raster_crs = crs.to_wkt() if hasattr(crs, "to_wkt") else crs
        with rasterio.open(
            filename,
            "w",
            driver="GTiff",
            height=rows,
            width=cols,
            count=1,
            dtype="float32",
            crs=raster_crs,
            transform=transform,
            nodata=nodata,
            compress="deflate",
            tiled=True,
        ) as dst:
            dst.write(data.astype("float32"), 1)
            if tags:
                dst.update_tags(**tags)
        return filename
