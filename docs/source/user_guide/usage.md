# 🐄 Usage

## Command Line Interface:

**Generate a vertical shift grid for anywhere on Earth.**

```bash
# Transform MLLW to WGS84 Ellipsoid in Norton Sound, AK

transformez build -R -166/-164/63/64 -E 1s -I vdatum:mllw -O epsg:4979
```

**Transform a raster directly.** Transformez reads the bounds/resolution from the file.

```bash
transformez shift my_dem.tif \
    -I epsg:5703 -O vdatum:mhw \
    --decay-distance 5000 \
    --buffer-distance 250
```

> ⚠️ `--decay-pixels` is retained for backward compatibility. New workflows should use `--decay-distance`, which defines the inland transition in physical meters and is independent of raster resolution.


## Reference Inputs

Transformez accepts standard EPSG coordinate reference identifiers as well as namespaced references for tidal and model-based vertical surfaces.

Common examples include:

```text
EPSG:5703        # NAVD88 height
EPSG:4979        # WGS 84 ellipsoidal height
vdatum:mllw      # NOAA VDatum Mean Lower Low Water
vdatum:mhw       # NOAA VDatum Mean High Water
global:lat       # Global Lowest Astronomical Tide proxy
global:mss       # Global Mean Sea Surface
```

For backward compatibility, common shorthand names remain supported:

```text
mllw
mlw
mhw
mhhw
msl
lat
hat
mss
```

These shorthand forms are normalized internally to their corresponding namespaced references.

Compound horizontal and vertical references may also be supplied where supported, for example:

```text
EPSG:4326+5703
```

Legacy Transformez/CUDEM geoid-qualified strings remain supported during the reference-system transition:

```text
EPSG:4326+5703+geoid:g2012b
```

> ⚠️ For new workflows, use explicit namespaced or authority-qualified references.
>Legacy shorthand remains accepted for compatibility but may emit deprecation warnings.
>For new code, prefer explicit EPSG and namespaced reference identifiers where practical.


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
    datum_in="vdatum:mllw",   # VDatums mllw realization
    datum_out="4979",         # WGS84 Ellipsoid
    out_fn="india_shift.tif"  # Optional: Save to disk
)

# ---------------------------------------------------------
# Transform an Existing Raster
# ---------------------------------------------------------
# Applies the datum shift directly to a DEM and saves the result.

out_file = transformez.transform_raster(
    input_raster="my_dem_lat.tif",
    datum_in="global:lat",
    datum_out="5703:g2012b",            # NAVD88 using specific GEOID12B
    extrapolate_inland=False,           # For infinite inland extrapolation (Modeling)
    output_raster="my_dem_navd88.tif"
)
```

### Building a `ShiftGrid` or an shift array

`transformez.generate_grid(...)`

is a convenient array-oriented API, whereas:

`build_shift_grid(...)`

is a richer object-oriented API.

`ShiftGrid` carries the array, region, CRS, affine transform, source and target references, epochs, provenance, generation key, uncertainty, and cache information, and can write/reproject itself.

> Use `generate_grid()` when you only need shift values.
> Use `build_shift_grid()` when you need a georeferenced, inspectable transformation product.

```python
grid = build_shift_grid(...)

grid.array
grid.crs
grid.transform
grid.source_reference
grid.target_reference
grid.provenance

grid.write(...)
grid.reproject(...)
```

### Building Transformation Components
`build_components()` parses complete source/destination references and returns a horizontal transformer plus a vertical `ShiftGrid`.

```python
components = transformez.build_components(
    "EPSG:4326+5703",
    "EPSG:32610+4979",
    region=region,
)

components.horizontal
components.vertical
```

## Hydrodynamic & Tsunami Modeling

By default, Transformez decays tidal transformations inland using physical distance from the coastline. New workflows should use `--decay-distance` and `--buffer-distance`, which produce consistent behavior regardless of raster resolution.

Some tsunami, storm-surge, and inundation workflows instead require the coastal transformation to continue across all terrain that may become wetted during the simulation. For those cases, disable inland decay with:

```bash
transformez shift my_coastal_dem.tif \
    -I epsg:5703 -O vdatum:mhw \
    --extrapolate-inland
```

`--decay-pixels` remains available for backward compatibility but is deprecated for new workflows.
