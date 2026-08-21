# 📐 Geodetic Methodology & Architecture
To provide vertical transformations across varied geographic extents, `transformez` relies on a dynamic, rigorous architecture.
The `transformez`engine computes optimal geodetic pathways on the fly.

Here is a look under the hood at how `transformez` handles dynamic vertical transformations.

```mermaid
flowchart TD
    %% Define Styles
    classDef hub fill:#1f77b4,stroke:#fff,stroke-width:2px,color:#fff,font-weight:bold
    classDef tidal fill:#2ca02c,stroke:#fff,stroke-width:2px,color:#fff
    classDef ortho fill:#ff7f0e,stroke:#fff,stroke-width:2px,color:#fff
    classDef global fill:#9467bd,stroke:#fff,stroke-width:2px,color:#fff

    subgraph "Regional Surfaces (USA/CAN)"
        A[Local Tidal<br>MLLW, MHW, MSL]:::tidal <-->|VDatum Grids| B(LMSL -> TSS):::tidal
        B <-->|Topography of Sea Surface| C[Regional Orthometric<br>NAVD88, PRVD02, CGVD2013]:::ortho
    end

    subgraph "Global Surfaces"
		direction LR
        D[Global Tidal<br>LAT, HAT, MSS]:::global
        G[Global Orthometric<br>EGM2008, EGM96]:::ortho
    end

    subgraph "Geodetic Hubs (Ellipsoids)"
        direction LR
        C <-->|Regional Geoids<br>g2018, g2012b, CGG2013| E(NAD83<br>Native Hub):::hub
        D <-->|DTU25 + FES2014<br>via /vsicurl/| F(WGS84<br>Global Hub):::hub
        G <-->|Global Geoid Models| F
        E <-->|HTDP Engine<br>Epoch / Tectonic Shifts| F
    end
```

## The Dynamic Hub-and-Spoke Model
`transformez` routes complex, multi-step vertical conversions (e.g., moving from a local tidal datum directly to a global geoid) by using an autonomous **"Hub-and-Spoke"** system

* **Native Ellipsoid Hubs:** Every transformation is mathematically routed through a central geodetic frame (the "Hub").

* **Intelligent Routing:** The engine evaluates the requested input and output datums and automatically selects the safest hub.
For example, if both datums belong to the North American Datum family, the engine routes strictly through the NAD83 ellipsoid hub to avoid introducing unnecessary global transformation errors. If the request crosses international or global boundaries, it scales up to the WGS84 hub.

## The Datum Shift (Sign Conventions)
A common point of confusion in vertical geodesy is the sign convention of shift grids and what to do with them. It is easy to assume that shifting "up" to a higher surface should result in positive shift values, but physically, the opposite is true.

* **The Stick in the Bay:** Imagine standing in the water of a bay holding a measuring stick with a "zero" line maked Mean Low Water. If you move your "zero" mark to a higher datum (e.g., moving from Mean Low Water up to Mean Higher High Water), the water level on your stick will read as a lower number.

* **The Rule of Addition:** Because of this, shifting to a higher reference surface actually requires a negative shift value. `transformez` automatically handles these complex sign inversions internally so you don't have to overthink it. You always simply **ADD** the generated shift grid to your raster (i.e., `New_DEM = Old_DEM + Shift_Grid`). The grid's native positive and negative values automatically ensure the math reflects physical reality.

## Continuous Coastal Blending
Official tidal models (like NOAA's VDatum) only provide data close to the coast. However, modern hydrodynamic modeling requires continuous grids that extend far into the deep ocean or miles inland.

* **Offshore Extrapolation:** When a requested bounding box extends beyond native VDatum coverage, `transformez` automatically fetches global satellite altimetry (like DTU25 or FES2014) as a proxy.

* **Smart Blending:** To prevent harsh steps between the two models, the engine applies a dynamic spatial crossfade, isolating the Mean Dynamic Topography (MDT) and smoothly blending the VDatum boundary into the global satellite frame.

## Inland Tidal Decay
Water levels (and their associated tidal datums) do not physically exist on dry land. However, coastal DEMs require inland datum extrapolation to allow storm surges to properly push water uphill during flood simulations.

* **Voronoi Ridges:** To extrapolate tidal datums inland without introducing artificial slopes, `transformez` generates nearest-neighbor Voronoi ridges from the coastline.

* **Gaussian Blurring & Easing:** These ridges are then heavily blurred and crossfaded with the raw coastal data to ensure continuity (a smooth surface with no sharp corners) deep inland.

* **Hermite S-Curve:** Users can dictate how far tidal influences push inland using the `--decay-pixels` parameter. Instead of a harsh linear drop-off, the engine applies a Hermite S-Curve polynomial. This ensures the tidal datum smoothly flattens out into the geodetic baseline as defined by the user.

## Autonomous Self-Healing
`transformez` is designed to survive infrastructure failures automatically:

* **Geoid Fallbacks:** If a requested geoid (like g2018) lacks physical coverage in a remote area (e.g., parts of Alaska), the engine automatically scans its registry and downgrades to the newest compatible model (like g2012b or geoid09) to keep the pipeline alive.

* **Tectonic Fallbacks:** When querying the NGS HTDP (Horizontal Time-Dependent Positioning) engine for complex plate tectonic shifts, requests crossing certain temporal epochs can fail. `transformez` catches these failures and seamlessly falls back to a static datum shift at the target epoch.
