#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez
~~~~~~~~~~~~~

Initialize the API and fetchez extension.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

try:
    from transformez._version import __version__
except ImportError:
    import warnings

    warnings.warn(
        "Importing 'transformez' outside a proper installation."
        " It's highly recommended to install the package from a stable release or"
        " in editable mode.",
        stacklevel=2,
    )
    __version__ = "dev"


from .api import generate_grid, transform_raster, build_components
from .generation import build_shift_grid

import os
import glob
# Expose the module for fetchez
# from .modules import TransformezMod


def _find_proj_lib() -> str | None:
    """Locate the best available PROJ_LIB path."""

    try:
        import rasterio

        r_path = os.path.join(os.path.dirname(rasterio.__file__), "proj_data")
        if os.path.exists(os.path.join(r_path, "proj.db")):
            return r_path

        parent = os.path.dirname(os.path.dirname(rasterio.__file__))
        libs = glob.glob(os.path.join(parent, "rasterio.libs*"))
        if libs:
            for root, _, files in os.walk(libs[0]):
                if "proj.db" in files:
                    return root
    except ImportError:
        pass

    try:
        import pyproj

        p_path = pyproj.datadir.get_data_dir()
        if os.path.exists(os.path.join(p_path, "proj.db")):
            return p_path
    except ImportError:
        pass

    return None


target_proj_lib = _find_proj_lib()

if "PROJ_LIB" in os.environ:
    del os.environ["PROJ_LIB"]

if target_proj_lib:
    os.environ["PROJ_LIB"] = target_proj_lib

__all__ = ["generate_grid", "transform_raster", "build_components", "build_shift_grid"]
