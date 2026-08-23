# 🗺️ Supported Datums & Vertical Reference
Transformez categorizes elevations into three distinct physical models.

## 🌊 Tidal Datums (The Dynamic Ocean)
Tidal datums are defined by observing water levels at coastal tide gauges over a 19-year National Tidal Datum Epoch (NTDE). Since **the ocean is not flat**, due to coastal funneling, bathymetric friction, Coriolis effects, etc., a tidal surface like Mean Lower Low Water (MLLW) curves and changes drastically as you move from the open ocean into a shallow estuary. Therefore, tidal datums are inherently spatial and should not generally be represented by a single, constant conversion number, especially over wide areas.

**Supported Tidal Surfaces:**

| EPSG | NAME       | DESC     |
|------|------------|----------|
| 1089 | mllw       | [USA]    |
| 5866 | mllw       | [USA]    |
| 1091 | mlw        | [USA]    |
| 5869 | mhhw       | [USA]    |
| 5868 | mhw        | [USA]    |
| 5714 | msl        | [USA]    |
| 5713 | mtl        | [USA]    |
| 0    | crd        | [USA]    |
| 5609 | IGLD85     | [USA]    |
| 9000 | LWD_IGLD85 | [USA]    |
| 5702 | NGVD29     | [GLOBAL] |
| 9001 | lat        | [GLOBAL] |
| 9002 | hat        | [GLOBAL] |
| 9003 | mss        | [GLOBAL] |

## 🌐 Ellipsoidal Datums (The Math Model)
Ellipsoidal heights represent distance from a perfectly smooth, mathematical oval (an ellipsoid) wrapped around the earth. GPS satellites natively calculate elevations relative to this smooth mathematical surface. Crucially, tectonic plates move over time. A global frame like WGS84 treats the Earth as a whole, while a plate-fixed frame like NAD83 moves with the North American plate. Because of this tectonic drift, *epochs (time)* matter heavily when transforming between ellipsoids.

**Supported Ellipsoidal / Frame Datums:**

| EPSG | NAME  | DESC                       |
|------|-------|----------------------------|
| 4979 | WGS84 | World Geodetic System 1984 |
| 6319 | NAD83 | North American Datum 1983  |

## 🏔️ Orthometric Datums (The Gravity Field)
Orthometric heights are what we commonly think of as **"Height Above Sea Level,"** but they are actually tied to a **Geoid** (a complex, bumpy mathematical model representing global gravity anomalies). Because the Earth's density varies (mountains are dense, deep ocean trenches are not), gravity pulls harder in some places than others, meaning a "level" surface is not a perfect geometric shape.

**Supported Orthometric / Geoid-Based Datums:**

| EPSG | NAME                 | DESC                     |
|------|----------------------|--------------------------|
| 5703 | NAVD88 height        | (Default Geoid: g2018)   |
| 6360 | NAVD88 height (usFt) | (Default Geoid: g2018)   |
| 8228 | NAVD88 height (Ft)   | (Default Geoid: g2018)   |
| 6641 | PRVD02 height        | (Default Geoid: g2018)   |
| 6642 | VIVD09 height        | (Default Geoid: g2018)   |
| 6647 | CGVD2013(CGG2013)    | (Default Geoid: CGG2013) |
| 3855 | EGM2008 height       | (Default Geoid: egm2008) |
| 5773 | EGM96 height         | (Default Geoid: egm96)   |

### 🌍 Available Geoids:

  g2018, g2012b, geoid09, xgeoid20b, xgeoid19b, egm2008, egm96, CGG2013
