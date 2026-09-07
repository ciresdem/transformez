# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [ UNRELEASED ]

### Added
- Coastal Context dataclass to hold context values
- test script to validate refactor
- grid_engine.build_coastal_context function to build the coastal context dataclass.
- Added the new transformez.reference foundation for typed coordinate-reference handling, including VerticalReference, ParsedReference, and ResolvedReference models.
- Added reference.parser for centralized parsing and decomposition of EPSG, compound, horizontal, vertical, and custom namespaced references.
- Added custom reference bindings for NOAA VDatum tidal surfaces and global tidal/model surfaces.
- Added reference.adapter as a temporary compatibility bridge between the new typed reference system and the existing definitions-driven transformation engine.
- Added compatibility handling for legacy Transformez/CUDEM geoid syntax such as EPSG:4326+5703+geoid:g2012b.
- Added a new typed reference parsing and binding layer for horizontal and vertical reference systems, including namespaced custom references and legacy aliases.
- Added build_shift_grid() as the canonical vertical grid generation interface and introduced the ShiftGrid object for working with generated transformations.
- Added planner.py as the canonical transformation planner. This maps out the transformation plan based on the resolved references.
- Added resolver.py which resolves a parsed reference to obtain the full context of the transformation.
- Added fetcher.py, ported from transform.py, to allow the use of existing fethcing/compositing for use in transformations.
- Added CLI commands the help track the progress of porting references from definitions.
- Added `engine` module.
- Added `grid` module.

### Changed
- Updated CLI options to use new dist2coast km decay and blend options
- Process blends and decays using the km field from dist2coast instead of edt.
- Updated srs.py to use the new coastal context and expose their options.
- Updated api.py to resolve datum inputs through the new reference parser and legacy adapter rather than parsing datum identifiers directly through definitions.py.
- Updated generate_grid(), transform_raster(), and prefetch_region() operations to consume normalized reference metadata from the adapter.
- Vertical CRS units are now derived from typed reference metadata when automatic unit detection is requested.
- Moved generic vertical unit conversion definitions out of definitions.py and into utils.py, separating unit conversion from datum-registry metadata.
- Legacy tidal datum names such as mllw, mlw, mhw, mhhw, msl, lat, hat, and mss now resolve through explicit namespaced reference aliases.
- ShiftGrid now carries its CRS, extent, transform, references, epochs, provenance, uncertainty, and cache identity, and can be reprojected or written directly.
- Simplified the high-level Python API so everything uses generation.py
- Improved generated-grid cache identity to account for transformation references, epochs, region, resolution, decay settings, and other generation options.
- Moved vertical unit metadata out of the legacy datum registry and into the typed reference model.
- Refactored to adhere to ruff PTH rules.
- Moved htdp and vdatum to /engines
- Moved fetchez modules and hooks to /fetchez/...
- Moved GridWriter into new /grid/io module

### Fixed
- Refactor dist2coast usage to fix a bug that would burn the dist2coast edges onto the raster result. This was due to performing an edt distance transform from the low-res dist2coast raster, treating it as a mask instead of a distance field. Update allows setting the distance by km instead of number of pixels and smooths the 'zero' field to get proper transitions.
- Since dist2coast sets it's nodata value to zero, we were incorrectly masking the dist2coast raster by ignoring the zero values (coastline), we now have an option to ignore the nodata value in grid_engine.
- Improved validation of datum/reference inputs by resolving standard EPSG identifiers through PROJ before adapting them to the legacy transformation engine.
- Improved support of legacy reference sytax in parser.py by parsing non-standard epsg+ syntax.

### Deprecated
- The legacy SRSParser interface remains available for compatibility but now delegates to the new API.
- Legacy datum/reference aliases remain supported, but explicit EPSG and namespaced reference identifiers are preferred for new code.

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
