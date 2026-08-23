#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.modules.dtu
~~~~~~~~~~~~~

The transformez dtu fetchez module that uses vsicurl to fetch subsets.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
from typing import Any

from .base import TransformezModule

logger = logging.getLogger(__name__)


class DTU(TransformezModule):
    """DTU Mean Sea Surface (WGS84) via /vsicurl/."""

    name = "dtu"

    def __init__(self, datatype: str = "mss25", **kwargs: Any):
        super().__init__(name="dtu", **kwargs)
        self.datatype = datatype
        self.dataset_url = "https://api.figshare.com/v2/file/download/55747802"

    def run(self):
        if not self.wgs_region:
            return self

        w, e, s, n = self.wgs_region
        out_name = f"dtu25_mss_{w}_{s}_{e}_{n}.tif"

        self.add_entry_to_results(
            url=self.dataset_url,
            dst_fn=out_name,
            data_type=self.datatype,
            format="netcdf",
            var_name="mss",
            grid_bounds=(0.0, -90.0, 360.0, 90.0),
            title=f"DTU25 MSS Subset ({w},{s} to {e},{n})",
        )
        return self
