# -*- coding: utf-8 -*-

__version__ = "0.1.0"
__author__ = "Matthew Love"
__credits__ = "CIRES"

# Import everything except the individual modules.
#from . import utils
#from . import definitions
#from . import transform
#from . import htdp
#from . import vdatum
#from . import cli

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
