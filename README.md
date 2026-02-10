# Transformez

**The Vertical Transformation Tool and Fetchez Extension.**

> ⚠️ **BETA STATUS:** This project is in active development (v0.1.0).

**Transformez** provides vertical datum transformations for geospatial data. It acts as a bridge between the messy reality of vertical datums (Tidal, Orthometric, Ellipsoidal) and your data processing pipeline.

It works in two ways:
1.  **Standalone CLI:** Generate shift grids (TIF) for any region or match an existing DEM.
2.  **Fetchez Plugin:** Automatically transform data as it is downloaded.

![Shift Grid Example](docs/images/mllw2nvd.png)
*(Above: A generated vertical shift grid transforming MLLW to NAVD88)*

## Features

* **Tidal Transformations:** Wraps NOAA's **VDatum** to transform between tidal surfaces (MLLW, MHHW) and geometric datums.
* **Geoid Grids:** Seamlessly applies PROJ-CDN geoids (GEOID18, GEOID12B, EGM2008).
* **Time-Dependent Shifts:** Integrates **HTDP** to handle crustal velocities and epoch transformations.
* **Smart Grid Engine:** Automates the fetching, stitching, and mosaicking of partial VDatum grids into a single continuous shift surface.

---

## Installation

Requires **Fetchez** (v0.3.3+) and standard geospatial libs.

```bash
# Clone and install
git clone https://github.com/ciresdem/transformez.git
cd transformez
pip install -e .
```

## Usage
1. Standalone CLI
Use transformez to generate shift grids for use in other software (PDAL, GDAL, CARIS) or to transform a specific DEM directly.

* Mode A: Region & Resolution
Generate a generic shift grid for a specific bounding box.

```bash
# Generate a shift grid from MLLW (5866) to NAVD88 (5703)
# -R: West/East/South/North
# -E: Grid resolution (e.g., 3 arc-seconds)
transformez -R -95.5/-94.5/28.5/29.5 -E 3s \
    --vdatum-in "5866" \
    --vdatum-out "5703:g2018" \
    --output mllw_to_navd88.tif
```

* Mode B: Match Input DEM
Automatically extract the bounds and resolution from an input DEM and generate a matching transformed output.

```bash
# Transform an existing DEM from Ellipsoidal (6319) to Orthometric (5703)
transformez --dem input_dem.tif \
    --vdatum-in "6319" \
    --vdatum-out "5703" \
    --output output_navd88.tif
```

2. As a Fetchez Hook
Configure fetchez to generate transformation grids automatically for downloaded data regions.

```bash
# Download SRTM and prepare a shift grid from EGM96 to WGS84
fetchez srtm_plus -R -120/-119/33/34 --hook transformez:datum_in=5773,datum_out=4979
```

## Supported Datums

Transformez supports EPSG codes and compound formats (EPSG:GEOID).

Ellipsoidal: 6319 (NAD83 2011), 4979 (WGS84)

Orthometric: 5703 (NAVD88), 5702 (NGVD29), 3855 (EGM2008)

Tidal: 5866 (MLLW), 5869 (MHHW), 5714 (MSL)

Geoids: g2018, g2012b, xgeoid20b, egm2008

## License
MIT
