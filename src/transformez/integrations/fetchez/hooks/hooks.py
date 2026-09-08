#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.hooks
~~~~~~~~~~~~~

Some hooks for `fetchez`

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

from pathlib import Path
import logging

from fetchez.hooks import FetchHook
from fetchez import utils

from transformez.grid.shift import build_shift_grid

logger = logging.getLogger(__name__)


class TransformezHook(FetchHook):
    """Vertical Transformation Hook.

    - Stage 'pre': Generates the master shift grid using module.region.
    - Stage 'file': Applies the shift grid to each downloaded file. *in progress*

    Usage:
      fetchez copernicus --hook transformez:datum_in=5703,datum_out=6319,stage=pre
      fetchez copernicus --hook transformez:apply=True
    """

    name = "transformez"
    stage = "pre"
    desc = "Generate a vertical transformation shift grid."

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
        keep_grid=True,
        apply=False,
        **kwargs,
    ):
        super().__init__(name="transformez", **kwargs)
        self.src_datum = src_datum
        self.dst_datum = dst_datum
        self.increment = increment
        self.output_name = output_name
        self.epoch_in = epoch_in
        self.epcoh_out = epoch_out
        self.decay_pixels = decay_pixels
        self.decay_distance_m = decay_distance_m
        self.buffer_distance_m = buffer_distance_m
        self.max_vdatum_extension_m = max_vdatum_extension_m
        self.extrapolate_inland = extrapolate_inland
        self.use_stations = use_stations
        self.keep_grid = utils.str2bool(keep_grid)
        self.apply = utils.str2bool(apply)

        s_name = str(self.src_datum).replace(":", "_")
        d_name = str(self.dst_datum).replace(":", "_")
        w, e, s, n = self.region
        self.dst_fn = Path(self._outdir) / f"shift_{s_name}_to_{d_name}_{w}_{s}.tif"

    def run(self, entries):
        for mod, entry in entries:
            region = getattr(mod, "region", None)
            if not region:
                logger.warning(
                    "Module has no region defined. Cannot generate shift grid in PRE stage."
                )
                continue

            logger.info(f"Generating vertical shift grid for region: {region}")
            shift_grid = build_shift_grid(
                self.region,
                self.increment,
                self.src_datum,
                self.out_datum,
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

            entry["shift_grid_path"] = self.dst_fn
            entry["vdatum_in"] = self.datum_in
            entry["vdatum_out"] = self.datum_out
            entry["transformed"] = False

        return entries
