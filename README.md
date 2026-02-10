# fetchez-transformez

**The Vertical Transformation Extension for Fetchez.**

> ⚠️ **BETA STATUS:** This project is in active development.

**Transformez** provides robust vertical datum transformations for geospatial data. It acts as a bridge between the messy reality of vertical datums (Tidal, Orthometric, Ellipsoidal) and your data processing pipeline.

It works in two modes:
1.  **Standalone CLI:** Generate shift grids (GTX) for any region.
2.  **Fetchez Plugin:** Automatically transform data as it is downloaded.

## 🌎 Features

* **Tidal Transformations:** Wraps NOAA's **VDatum** to transform between tidal surfaces (MLLW, MHHW) and geometric datums.
* **Geoid Grids:** Seamlessly applies PROJ-CDN geoids (GEOID18, GEOID12B, EGM2008).
* **Time-Dependent Shifts:** Integrates **HTDP** to handle crustal velocities and epoch transformations (e.g., ITRF2014 @ 2020.0 -> NAD83(2011) @ 2010.0).
* **Grid Engine:** Automates the fetching, stitching, and mosaicking of partial VDatum grids into a single continuous shift surface.

---

## 📦 Installation

Requires **Fetchez** (v0.3.3+) and standard geospatial libs.

```bash
# Clone and install
git clone [https://github.com/ciresdem/fetchez-transformez.git](https://github.com/ciresdem/fetchez-transformez.git)
cd fetchez-transformez
pip install -e .
```

Note: For Tidal transformations, you must have Java installed to run the embedded VDatum JAR.

## 🛠 Usage
1. ***As a Fetchez Hook*** (The Pipeline Way)
Automatically transform data immediately after download. This generates a shift grid for the exact region of the downloaded data and applies it.

```bash

# Download SRTM and convert from EGM96 (Default) to Ellipsoidal (WGS84)
fetchez srtm -R -120/-119/33/34 --hook transformez:in=5773,out=4979

# Download Multibeam and convert from MLLW to NAD83(2011) Ellipsoidal
fetchez multibeam -R ... --hook transformez:in=5866,out=6319
```

2. ***As a Standalone CLI***
Use transformez to generate shift grids for use in other software (like PDAL, GDAL, or CARIS).

```bash
# Generate a GTX shift grid from MLLW to NAVD88
transformez -R -95/-94/28/29 -E 1s \
    --vdatum-in "5866" \
    --vdatum-out "6319:g2012b" \
    --output mllw_to_navd88.gtx
```

## 🗺 Supported Datums

Transformez supports a "Compound Datum" string format: EPSG:GEOID.

* Ellipsoidal: 6319 (NAD83 2011), 4979 (WGS84)

* Orthometric: 5703 (NAVD88), 5702 (NGVD29)

* Tidal: 5866 (MLLW), 5869 (MHHW), 5714 (MSL)

* Geoids: g2018, g2012b, xgeoid20b

***Example***: 6319:g2018 represents NAD83(2011) Orthometric height derived via Geoid18.

## 📄 License
MIT
