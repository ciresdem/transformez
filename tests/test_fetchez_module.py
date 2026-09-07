import numpy as np
import rasterio

from fetchez.spatial import Region
from transformez.fetchez.modules.modules import TransformezMod


def test_generate_identity_grid(tmp_path):
    module = TransformezMod(
        src_region=Region(-67.001, -67.0, 44.9, 44.901),
        src_datum="EPSG:5703",
        dst_datum="EPSG:5703",
        increment="1s",
        epoch_in="2020.0",
        epoch_out="2020.0",
        outdir=str(tmp_path),
    )
    module.run()
    with rasterio.open(module.dst_fn) as dataset:
        np.testing.assert_allclose(dataset.read(1), 0.0, atol=1e-6)
    assert module.results[0]["meta"]["dst_datum"] == "EPSG:5703"
