<p align="center">
	<a href="https://github.com/continuous-dems">
		<img src="https://raw.githubusercontent.com/continuous-dems/transformez/refs/heads/main/docs/source/_static/transformez-logo.svg" height="80" alt="Continuous DEMs Logo">
	</a>
</p>
<h1 align="center">Transformez</h1>
<p align="center"><strong>Global vertical datum transformations, simplified.</strong></p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.12+-yellow.svg" alt="Python"></a>
  <a href="https://badge.fury.io/py/transformez"><img src="https://badge.fury.io/py/transformez.svg" alt="PyPI version"></a>
  <a href="https://anaconda.org/conda-forge/transformez"><img src="https://img.shields.io/conda/vn/conda-forge/transformez.svg" alt="Conda Version"></a>
  <a href="https://cudem.zulip.org"><img src="https://img.shields.io/badge/zulip-join_chat-brightgreen.svg" alt="Project Chat"></a>
  <a href="https://doi.org/10.5281/zenodo.22131424"><img src="https://zenodo.org/badge/DOI/10.5281/zenodo.22131423.svg" alt="DOI"></a>
</p>

**Transformez** is a standalone Python engine for converting geospatial data between vertical datums (e.g., `MLLW` ↔ `NAVD88` ↔ `Ellipsoid`).

Transformez is part of the [Continuous DEMs Project](https://continuous-dems.readthedocs.io/), an ecosystem of tools for modern, continuous digital elevation model generation. Originally incubated within CUDEM, the engine has evolved into a standalone datum transformation suite.

---

## 📦 Installation

**Install Transformez**
Install the transformez python package:

```bash
pip install transformez
```

**Install HTDP**
The NGS Horizontal Time-Dependent Positioning (HTDP) software is required to perform highly accurate plate tectonic and frame transformations, you can install it with transformez!:

```bash
transformez htdp install
```

## 🐄 Quickstart

**Generate a vertical shift grid for anywhere on Earth.**

```bash
# Transform MLLW to WGS84 Ellipsoid in Norton Sound, AK

transformez grid -R -166/-164/63/64 -E 1s -I mllw -O 4979
```

**Transform a raster directly.** Transformez reads the bounds/resolution from the file.

```bash
transformez raster my_dem.tif -I mllw -O 5703
```

**Integrate directly into your fetchez pipeline.**

```bash
# Generate vertical datum shift grids on-demand.
fetchez transformez --src_datum mllw --dst_datum 4979 --increment 1s
```
---

## 📚 Documentation
Would you like to know more? Check out our [Official Documentation](https://transformez.readthedocs.io) to learn about:

* **The Python API:** Build custom, memory-safe transformations directly into your applications.
* **Offline Field Ops:** Pre-fetch global FES models, VDatum grids, and NASA coastlines for offline execution (`transformez prefetch`).
* **Live CO-OPS Data:** Dynamically interpolate geodetic surfaces using live tide station offsets (`--use-stations`).
* **Data Provenance:** Learn how Transformez embeds automated metadata tags into output GeoTIFFs for strict scientific traceability.

---

## ⚖ License

This project is licensed under the MIT License - see the [LICENSE](https://github.com/ciresdem/transformez/blob/main/LICENSE) file for details.

Copyright (c) 2010-2026 Regents of the University of Colorado
