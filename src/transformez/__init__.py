# -*- coding: utf-8 -*-

__version__ = "0.1.0"
__author__ = "Matthew Love"
__credits__ = "CIRES"

import os

# --- fix the PROJ_LIB path to work with rasterio/pyproj
def _find_proj_lib():
    """Locate the best available PROJ_LIB path."""
    
    try:
        import rasterio
        # Common path in wheels: site-packages/rasterio/proj_data
        r_path = os.path.join(os.path.dirname(rasterio.__file__), 'proj_data')
        if os.path.exists(os.path.join(r_path, 'proj.db')):
            return r_path
            
        # Linux wheels often put it in .libs adjacent to the package
        # e.g. site-packages/rasterio.libs/proj.db
        parent = os.path.dirname(os.path.dirname(rasterio.__file__))
        libs = glob.glob(os.path.join(parent, 'rasterio.libs*'))
        if libs:
            # Look inside the libs folder
            for root, _, files in os.walk(libs[0]):
                if 'proj.db' in files:
                    return root
    except ImportError:
        pass

    # Try PyProj's bundled data (Fallback)
    try:
        import pyproj
        p_path = pyproj.datadir.get_data_dir()
        if os.path.exists(os.path.join(p_path, 'proj.db')):
            return p_path
    except ImportError:
        pass
        
    return None

target_proj_lib = _find_proj_lib()

# Unset conflicting system/conda vars if we found a better one
if 'PROJ_LIB' in os.environ:
    del os.environ['PROJ_LIB']

if target_proj_lib:
    os.environ['PROJ_LIB'] = target_proj_lib
    # print(f"DEBUG: PROJ_LIB set to {target_proj_lib}")

# # --- PROJ_LIB Fix (Run before any geo-imports) ---
# # This prevents "PROJ: proj_create_from_database: Cannot find proj.db" errors
# # when conflicting Conda/System PROJ installations exist.
# try:
#     # 1. We must import pyproj first to let it find its own bundled data
#     import os
#     import pyproj
    
#     # 2. Get the valid data directory from the wheel
#     proj_lib = pyproj.datadir.get_data_dir()
#     #print(proj_lib)
#     # 3. Force the environment variable to use this valid path
#     #    (Overriding any bad global/Conda defaults)
#     os.environ['PROJ_LIB'] = proj_lib
    
# except ImportError:
#     # If pyproj isn't installed yet (e.g. during pip install), skip this.
#     pass

# --- End PROJ_LIB Fix ---

from .hooks import TransformezHook
#from .modules import DatumGridFetcher
from fetchez.hooks.registry import HookRegistry
# form fetchez.registry import FetchezRegistry # Implicitly handled via setup_fetchez passing cls

def setup_fetchez(registry_cls):
    """Called by fetchez when loading plugins.
    Registers modules, hooks, and presets.
    """

    # module should gather necessary grids to do the transformation
    # Register the Module with Fetchez
    # registry_cls.register_module(
    #     mod_key='datum_grids',
    #     mod_cls=DatumGridFetcher,
    #     metadata={
    #         'desc': 'Fetch NOAA VDatum and PROJ-CDN grids for a region',
    #         'tags': ['vdatum', 'geoid', 'transformation']
    #     }
    # )

    # Register Fetchez Hooks
    HookRegistry.register_hook(TransformezHook)
    
    # Register Global Presets
    from fetchez.presets import register_global_preset    
    
    register_global_preset(
        name="make-shift-grid",
        help_text="Download datum grids and composite them into a single GTX shift grid.",
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
