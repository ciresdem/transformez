#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez
~~~~~~~~~~~~~

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

__version__ = "0.1.0"
__author__ = "Matthew Love"
__credits__ = "CIRES"

import os
import glob

def _find_proj_lib():
    """Locate the best available PROJ_LIB path."""
    
    try:
        import rasterio
        r_path = os.path.join(os.path.dirname(rasterio.__file__), 'proj_data')
        if os.path.exists(os.path.join(r_path, 'proj.db')):
            return r_path
            
        parent = os.path.dirname(os.path.dirname(rasterio.__file__))
        libs = glob.glob(os.path.join(parent, 'rasterio.libs*'))
        if libs:
            for root, _, files in os.walk(libs[0]):
                if 'proj.db' in files:
                    return root
    except ImportError:
        pass

    try:
        import pyproj
        p_path = pyproj.datadir.get_data_dir()
        if os.path.exists(os.path.join(p_path, 'proj.db')):
            return p_path
    except ImportError:
        pass
        
    return None

target_proj_lib = _find_proj_lib()

if 'PROJ_LIB' in os.environ:
    del os.environ['PROJ_LIB']

if target_proj_lib:
    os.environ['PROJ_LIB'] = target_proj_lib
    # print(f"DEBUG: PROJ_LIB set to {target_proj_lib}")

from .hooks import TransformezHook
from fetchez.hooks.registry import HookRegistry

def setup_fetchez(registry_cls):
    """Called by fetchez when loading plugins.
    Registers modules, hooks, and presets.
    """

    HookRegistry.register_hook(TransformezHook)
    
    from fetchez.presets import register_global_preset    
    
    register_global_preset(
        name="make-shift-grid",
        help_text="Download datum grids and composite them into a single shift grid.",
        hooks=[
            {"name": "transformez", "args": {}} 
        ]
    )


    # "transform-pipeline": {
    #     "help_text": "Generate shift grid based on region, then apply it to files.",
    #     "hooks": [
    #         {
    #             "name": "transformez", 
    #             "args": {"stage": "pre", "datum_in": "5703", "output_grid": "/tmp/shift.gtx"}
    #         },
    #         {
    #             "name": "transformez", 
    #             "args": {"stage": "file", "apply": "True", "output_grid": "/tmp/shift.gtx"}
    #         },
    #         {
    #              "name": "audit" 
    #         }
    #     ]
    # }
