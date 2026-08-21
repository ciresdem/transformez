#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.modules
~~~~~~~~~~~~~

Some modules for `fetchez`

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import logging

from fetchez import cli
from fetchez.modules import FetchModule
from transformez.transform import VerticalTransform
from transformez.grid_engine import GridWriter
# from transformez.definitions import Datums

logger = logging.getLogger(__name__)


@cli.cli_opts(
    help_text="Generate a vertical shift grid (e.g. MLLW to NAVD88).",
    src_datum="Source Datum (e.g. 'mllw', '5703', '4979').",
    dst_datum="Destination Datum (e.g. '5703:geoid=g2012b').",
    increment="Grid resolution (default: 3s).",
    output_name="Optional output filename override.",
)
class TransformezMod(FetchModule):
    """A dynamic Fetchez module that generates vertical shift grids on demand.

    Usage:
      ... transformez --src-datum mllw --dst-datum 5703
    """

    name = "transformez"
    meta_desc = "Generate vertical datum shift grids on-demand."
    meta_category = "Tools"
    meta_tags = ["vdatum", "transformation", "shift-grid"]
    meta_resolution = "N/A"
    meta_license = "N/A"

    def __init__(
        self,
        src_datum="5703",
        dst_datum="4979",
        increment="3s",
        output_name=None,
        **kwargs,
    ):
        super().__init__(name="transformez", **kwargs)
        self.src_datum = src_datum
        self.dst_datum = dst_datum
        self.increment = increment
        self.output_name = output_name

        s_name = str(self.src_datum).replace(":", "_")
        d_name = str(self.dst_datum).replace(":", "_")
        w, e, s, n = self.region
        self.dst_fn = os.path.join(
            self._outdir, f"shift_{s_name}_to_{d_name}_{w}_{s}.tif"
        )

    def run(self):
        from fetchez import utils

        try:
            inc_val = utils.str2inc(self.increment)
            nx = int(self.region.width / inc_val)
            ny = int(self.region.height / inc_val)
        except Exception:
            logger.warning(
                f"Invalid increment '{self.increment}', defaulting to 3s (~0.000833)."
            )
            # Default roughly 3 arc-seconds (approx 90m)
            nx = int(self.region.width / 0.00083333333)
            ny = int(self.region.height / 0.00083333333)

        def parse_d(d_str):
            if ":" in str(d_str):
                parts = d_str.split(":")
                geoid = parts[1].split("=")[1] if "geoid=" in parts[1] else parts[1]
                return parts[0], geoid
            return d_str, None

        epsg_in, geoid_in = parse_d(self.src_datum)
        epsg_out, geoid_out = parse_d(self.dst_datum)

        vt = VerticalTransform(
            region=self.region,
            nx=nx,
            ny=ny,
            epsg_in=epsg_in,
            epsg_out=epsg_out,
            geoid_in=geoid_in,
            geoid_out=geoid_out,
        )

        logger.info(f"Generating shift grid: {self.src_datum} -> {self.dst_datum}...")
        shift_array, _ = vt._vertical_transform(vt.epsg_in, vt.epsg_out)

        if shift_array is None:
            logger.error("Transformation failed (No coverage or invalid datums).")
            return

        GridWriter.write(self.dst_fn, shift_array, self.region)

        self.add_entry_to_results(
            url=f"file://{self.dst_fn}",
            dst_fn=self.dst_fn,
            data_type="gtiff",
            meta={
                "src_datum": self.src_datum,
                "dst_datum": self.dst_datum,
                "generator": "transformez",
            },
        )
