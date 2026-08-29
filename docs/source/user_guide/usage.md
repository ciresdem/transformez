# 🐄 Usage

## Command Line Interface:

**Generate a vertical shift grid for anywhere on Earth.**

```bash
# Transform MLLW to WGS84 Ellipsoid in Norton Sound, AK

transformez grid -R -166/-164/63/64 -E 1s -I mllw -O 4979
```

**Transform a raster directly.** Transformez reads the bounds/resolution from the file.

```bash
transformez raster my_dem.tif \
    -I 5703 -O mhw \
    --decay-distance 5000 \
    --buffer-distance 250
```

**Integrate directly into your fetchez pipeline.**

```bash
# Download GEBCO and shift EGM96 to WGS84 on the fly
fetchez gebco ... --hook transformez:datum_in=5773,datum_out=4979
```

> ⚠️ `--decay-pixels` is retained for backward compatibility. New workflows should use `--decay-distance`, which defines the inland transition in physical meters and is independent of raster resolution.

## Python API:

Transformez provides a high-level API for embedding transformations directly into your Python scripts, Jupyter Notebooks, or automated pipelines.

```python
import transformez

# ---------------------------------------------------------
# Generate a Shift Grid
# ---------------------------------------------------------
# Returns a 2D numpy array. Optionally saves to a file.
# Requesting "mllw" in India triggers the Global Fallback (FES2014) automatically.

shift_array = transformez.generate_grid(
    region=[80, 85, 10, 15],  # [West, East, South, North]
    increment="3s",           # Grid resolution
    datum_in="mllw",
    datum_out="4979",         # WGS84 Ellipsoid
    out_fn="india_shift.tif"  # Optional: Save to disk
)

# ---------------------------------------------------------
# Transform an Existing Raster
# ---------------------------------------------------------
# Applies the datum shift directly to a DEM and saves the result.

out_file = transformez.transform_raster(
    input_raster="my_dem_mllw.tif",
    datum_in="mllw",
    datum_out="5703:g2012b",  # NAVD88 using specific GEOID12B
    extrapolate_inland=False,           # For infinite inland extrapolation (Modeling)
    output_raster="my_dem_navd88.tif"
)
```


## Hydrodynamic & Tsunami Modeling

By default, Transformez applies a 100-pixel decay to tidal transformations to smoothly transition coastal datums (like `mhw` or `mllw`) back to the terrestrial geodetic frame (like `5703`) inland.

If you are modeling tsunamis, storm surge, or sea-level rise, you often need your "water level zero" to remain mathematically constant infinitely inland to accurately calculate runup over high terrain.

To disable the inland decay and force continuous extrapolation of the coastal shift, set `--decay-pixels 0`:

```bash
# Transform a high-res coastal DEM for Tsunami runup modeling (infinite inland extrapolation)
transformez raster my_coastal_dem.tif -I 5703 -O mhw --decay-pixels 0
```
