# 🗺️ Supported Datums & Vertical Reference
Transformez categorizes elevations into three distinct physical models.

## 🌊 Tidal Datums (The Dynamic Ocean)
Tidal datums are defined by observing water levels at coastal tide gauges over a 19-year National Tidal Datum Epoch (NTDE). Since **the ocean is not flat**, due to coastal funneling, bathymetric friction, Coriolis effects, etc., a tidal surface like Mean Lower Low Water (MLLW) curves and changes drastically as you move from the open ocean into a shallow estuary. Therefore, tidal datums are inherently spatial and should not generally be represented by a single, constant conversion number, especially over wide areas.

**🌊 Supported Tidal Surfaces (NOAA VDatum):**

| ID          | Description                        |
|-------------|------------------------------------|
| vdatum:mhhw | NOAA VDatum Mean Higher High Water |
| vdatum:mhw  | NOAA VDatum Mean High Water        |
| vdatum:mllw | NOAA VDatum Mean Lower Low Water   |
| vdatum:mlw  | NOAA VDatum Mean Low Water         |
| vdatum:msl  | NOAA VDatum Mean Sea Level         |

**🛰️  Global Ocean Proxies (FES2014 / DTU25):**
| ID         | Description                              |
| global:hat | Highest Astronomical Tide (Global Proxy) |
| global:lat | Lowest Astronomical Tide (Global Proxy)  |
| global:mss | Mean Sea Surface (Global Proxy)          |

## 🌐 Ellipsoidal Datums (The Math Model)
Ellipsoidal heights represent distance from a perfectly smooth, mathematical oval (an ellipsoid) wrapped around the earth. GPS satellites natively calculate elevations relative to this smooth mathematical surface. Crucially, tectonic plates move over time. A global frame like WGS84 treats the Earth as a whole, while a plate-fixed frame like NAD83 moves with the North American plate. Because of this tectonic drift, *epochs (time)* matter heavily when transforming between ellipsoids.

**🌐 Supported Ellipsoidal / Frame Datums:**

| EPSG | NAME                     | Default Epoch |
|------|--------------------------|---------------|
| 6319 | NAD_83(2011/CORS96/2007) | 1997.0        |
| 7663 | WGS_84(G1674)            | 2000.0        |
| 4979 | WGS_84(G2139)            | 2020.0        |
| 6321 | NAD_83(PA11/PACP00)      | 1997.0        |


## 🏔️ Orthometric Datums (The Gravity Field)
Orthometric heights are what we commonly think of as **"Height Above Sea Level,"** but they are actually tied to a **Geoid** (a complex, bumpy mathematical model representing global gravity anomalies). Because the Earth's density varies (mountains are dense, deep ocean trenches are not), gravity pulls harder in some places than others, meaning a "level" surface is not a perfect geometric shape.

**🏔️ Supported Orthometric / Geoid-Based Datums:**

| EPSG | NAME                    | Default GEOID |
|------|-------------------------|---------------|
| 3855 | EGM2008 height          | egm2008       |
| 5703 | NAVD88 height           | g2018         |
| 5773 | EGM96 height            | egm96         |
| 6641 | PRVD02 height           | g2018         |
| 6642 | VIVD09 height           | g2018         |
| 6643 | ASVD02 height           | g2012bs0      |
| 6647 | CGVD2013 height         | CGG2013       |
| 8228 | NAVD88 height (us-feet) | g2012b        |

### 🌍 Available Geoids:

  g2018, g2012b, geoid09, xgeoid20b, xgeoid19b, egm2008, egm96, CGG2013
