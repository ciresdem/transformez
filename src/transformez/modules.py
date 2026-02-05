from fetchez import core, cli
from fetchez.modules.proj import PROJ
from fetchez.modules.vdatum import VDatum

from .definitions import Datums

@cli.cli_opts(
    help_text="Fetch vertical datum grids (Geoids/Tidal) needed for transformation.",
    in_datum="Input Datum (EPSG or Name)",
    out_datum="Output Datum (EPSG or Name)"
)
class DatumGridFetcher(core.FetchModule):
    """Identifies and fetches the specific VDatum/GEOID tiles needed 
    to transform between two datums in the given region.
    """
    
    name = 'datum_grids'
    
    def __init__(self, in_datum='5703', out_datum='6319', **kwargs):
        super().__init__(name=name, **kwargs)
        self.in_datum = in_datum
        self.out_datum = out_datum

        
    def run(self):
        # 1. Logic from your old 'fetch_vdatum'
        # Determine which grids (mllw, geoid12b, etc.) are needed
        required_grids = self._identify_grids(self.in_datum, self.out_datum)
        
        # 2. Query the NOAA/PROJ APIs (just to get URLs)
        # Instead of downloading now, we populate self.results
        for grid_type in required_grids:
             # (Reuse your logic to find the URLs for this region)
             # This effectively "Plans" the download.
             
             # Example:
             self.add_entry_to_results(
                 url="https://cdn.proj.org/us_noaa_g2018u0.tif",
                 dst_fn=f"g2018/{grid_type}.tif",
                 data_type="grid_part",
                 grid_role=grid_type # Store metadata for the hook later!
             )

             
    def _identify_grids(self, source, target):
        # ... logic from VerticalTransform that decides we need 'mllw' and 'g2018' ...
        
        return ['mllw', 'geoid18']
