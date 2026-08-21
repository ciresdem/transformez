# 🏛️ Transformez Philosophez

## The Inland Decay Philosophy
Tidal datums (like Mean Higher High Water) physically cease to exist where the ocean meets the land. If a standard GIS user transforms a county-wide DEM to MLLW, they might not want a 2-meter vertical shift applied 50 miles inland on the top of a mountain.

To protect inland topography, transformez uses a default decay_pixels=100 safety buffer. Using Nearest-Neighbor distance transforms and Hermite smoothing, the engine seamlessly decays the tidal shift down to zero as it moves inland, successfully anchoring the deep inland terrain back to the geodetic frame (e.g., NAVD88).

* **The Modeling Exception:**
Hydrodynamic modelers (Tsunami, Storm Surge, Sea Level Rise) are an exception to this rule. To simulate a wave riding up the terrain, the mathematical offset between the geodetic frame and the tidal frame must be preserved infinitely inland. If you are running a hydrodynamic simulation, always pass `--decay-pixels 0` to disable the decay and generate a continuous extrapolation surface.


## The "Constant Conversion" Fallacy (Flat vs. Spatial Shifts)
It can be tempting to make the assumption that vertical datums are simple, flat offsets. Many GIS software and users sometimes prefer to query a single, local tide gauge, find the offset (e.g., "MLLW is exactly -1.2 meters below NAVD88"), and apply that flat, constant value across their entire dataset.

While applying a flat shift is perfectly acceptable for certain circumstances, especially very local uses (such as surveying a single, 100-foot construction pad), it introduces significant vertical errors when applied to modern geospatial data like a 50-mile coastal DEM or a hydrodynamic model.

Since water piles up and moves around and tides push into shallow bays and narrow estuaries, friction and funneling effects can cause the tidal amplitude to stretch. MLLW at the mouth of an estuary might be -1.2 meters, but ten miles up the river, MLLW might be -0.8 meters and 10 miles inland it might be 0. Because of this, tidal transformations should be spatially varying to reflect the physical laws of the ocean.
