#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.modules
~~~~~~~~~~~~~

Some modules for `fetchez`

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

from pathlib import Path
import logging

from fetchez import cli
from fetchez.modules import FetchModule
from transformez.grid.shift import build_shift_grid

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
        epoch_in="2010.0",
        epoch_out="2010.0",
        decay_pixels=100,
        decay_distance_m=None,
        buffer_distance_m=None,
        max_vdatum_extension_m=None,
        extrapolate_inland=False,
        use_stations=False,
        **kwargs,
    ):
        super().__init__(name="transformez", **kwargs)
        self.src_datum = src_datum
        self.dst_datum = dst_datum
        self.increment = increment
        self.output_name = output_name
        self.epoch_in = epoch_in
        self.epoch_out = epoch_out
        self.decay_pixels = decay_pixels
        self.decay_distance_m = decay_distance_m
        self.buffer_distance_m = buffer_distance_m
        self.max_vdatum_extension_m = max_vdatum_extension_m
        self.extrapolate_inland = extrapolate_inland
        self.use_stations = use_stations

        s_name = str(self.src_datum).replace(":", "_")
        d_name = str(self.dst_datum).replace(":", "_")
        w, e, s, n = self.region
        self.dst_fn = Path(self._outdir) / f"shift_{s_name}_to_{d_name}_{w}_{s}.tif"

    def run(self):

        shift_grid = build_shift_grid(
            self.region,
            self.increment,
            self.src_datum,
            self.dst_datum,
            self.epoch_in,
            self.epoch_out,
            self.decay_pixels,
            self.decay_distance_m,
            self.buffer_distance_m or 0.0,
            self.max_vdatum_extension_m,
            self.extrapolate_inland,
            self._outdir,
            self.use_stations,
        )
        shift_grid.write(self.dst_fn)

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
