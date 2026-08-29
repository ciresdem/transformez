# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [ UNRELEASED ]

### Added
- Coastal Context dataclass to hold context values
- test script to validate refactor
- grid_engine.build_coastal_context function to build the coastal context dataclass.

### Changed
- Updated CLI options to use new dist2coast km decay and blend options
- Process blends and decays using the km field from dist2coast instead of edt.

### Fixed
- Refactor dist2coast usage to fix a bug that would burn the dist2coast edges onto the raster result. This was due to performing an edt distance transform from the low-res dist2coast raster, treating it as a mask instead of a distance field. Update allows setting the distance by km instead of number of pixels and smooths the 'zero' field to get proper transitions.
- Since dist2coast sets it's nodata value to zero, we were incorrectly masking the dist2coast raster by ignoring the zero values (coastline), we now have an option to ignore the nodata value in grid_engine.

## [0.6.0] - 2026-08-27

### Added

- PointTransformer api class/functionality to be able to transform point clouds directly.
- Comprehensive validation suite (`tests/validation/`) comparing Transformez output against NOAA CO-OPS tide gauges, the VDatum Java CLI, international FES2014 altimetry, and NGS HTDP tectonics.
- Automated Markdown report generation for validation results.
- Pytest configuration for CI/CD integration with `slow` and `accuracy` markers.
- Detailed methodology documentation covering the Hub-and-Spoke model, sign conventions, coastal blending, and inland tidal decay.
- `transformez prefetch` CLI command for offline field use.
- Support for DTU25 MSS baseline alongside FES2014.

### Changed

- **Breaking:** Simplified `VerticalTransform._vertical_transform()` API — removed redundant `epsg_in`/`epsg_out` arguments; the method now uses instance state exclusively. All call sites in `api.py` and `srs.py` updated accordingly.
- Improved error handling in `vdatum.py`: structured Java availability checks, graceful degradation when JAR is missing.
- Refined `RasterQuery` in `utils.py` to handle longitude normalization (`[-180, 180]`) more robustly.
- Consolidated `GridGen` class into `grid_engine.py`; `gridgen.py` is now a deprecated stub.
- Standardized docstrings (Args/Returns format) across all public methods.
- Expanded type hint coverage to 100% of public APIs across all modules.
- Updated documentation index to highlight the Continuous DEMs Project.
- Dynamic blur distance in `GridEngine.fill_nans()` — blur sigma now scales with `decay_pixels` instead of using a hardcoded value.

### Fixed

- Fixed file extension matching in `hooks.py` (`.las` → `".laz", ".las"`).
- Fixed circular import risk in `srs.py` by deferring `VerticalTransform` import to method level.
- Fixed None-safety crashes in `transform.py` when EPSG codes or `SURFACES` entries are missing.
- Removed duplicate `fetch_grid_()` method from `transform.py`.
- Removed deprecated `_get_global_chain_depreciated()` method.
- Pruned all commented-out dead code across the codebase.
- Fixed `vdatum.py` `run_cmd` calls that previously suppressed stderr.
- Fixed HTDP `run_cmd` error handling to catch `CalledProcessError` specifically.

### Removed

- Duplicate `GridGen` class definition (top-level in `grid_engine.py`).
- Dead/deprecated code blocks in `grid_engine.py`, `transform.py`, and `htdp.py`.

## [0.4.4] - 2026-06-25

### Added
- support for projected input rasters in the raster command
- add 'save_shift' to transform_raster api/cli

### CHANGED
- rety failed downloads, such as FES

## [0.4.3] - 2026-05-04

### Added
- new logo
- force htdp 3.5.0

## [0.3.5] - 2026-04-08

### Added

- RTD documentation
- Validation scripts and docs

### Changed

- Vdatum grid ordering (small->large)
- FES -> navd88 when merging with vdatum

## [0.3.4] - 2026-04-06

### Added

- HAT as proxy for mhw (symmetry method)
- Unit conversions in api/cli

### Changed

- Split cli 'run' command into 'grid' and 'raster'

## [0.3.2] - 2026-03-27

### Added
- support for FES2014
- Coastal blend where vdatum cuts off
- decay extrapolation to 0 inland from tidal datums
- Add API

### Changed
- cli now uses click

<...missed...>

## [0.1.0] - 2026-02-10
### Added

### Changed
- Now uses raserio
- Renamed project to `transformez`.
- Refactored and decoupled from old cudem.vdatums
