#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.srs
~~~~~~~~~~~~~

Depreciated. Use api.get_components when possible.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

from .api import build_components


class SRSParser:
    """Deprecated compatibility wrapper."""

    def __init__(self, src_srs, dst_srs, region=None, vert_grid=None, **kwargs):
        self.vert_grid = vert_grid
        self._components = build_components(
            src_srs,
            dst_srs,
            region=region,
            **kwargs,
        )

    def get_components(self):
        vertical_path = (
            self._components.vertical.write()
            if self._components.vertical is not None
            else None
        )

        return self._components.horizontal, vertical_path
