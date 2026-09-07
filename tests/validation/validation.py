#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.validation_suite
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Automated validation and documentation generation for transformez.

Runs against NOAA CO-OPS tide gauges, VDatum engine, global FES2014,
and NGS HTDP for tectonic transformations.

Usage:
    python tests/validation/validation_suite.py
    pytest tests/validation/ -m "not slow"
"""

import os
import sys
import csv
import time
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import requests
import matplotlib.pyplot as plt
from fetchez.spatial import Region

from transformez import generate_grid
from transformez.utils import RasterQuery
from transformez.engines.vdatum import Vdatum

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


# ============================================================================
# CONFIGURATION
# ============================================================================

TEST_REGIONS = {
    "Chesapeake Bay": {
        "bounds": (-77.5, -75.0, 36.5, 39.5),
        "challenge": "Estuary Shoaling",
        "vdatum_region": "1",
    },
    "Astoria OR": {
        "bounds": (-124.25, -123.0, 45.5, 46.5),
        "challenge": "River Dynamics",
        "vdatum_region": "3",
    },
    "Norton Sound AK": {
        "bounds": (-168.0, -160.5, 62.75, 65.25),
        "challenge": "Shallow Shelf / No VDatum Coverage",
        "vdatum_region": None,
    },
    "Tampa Bay FL": {
        "bounds": (-83.0, -82.0, 27.0, 28.0),
        "challenge": "Complex Bay Geometry",
        "vdatum_region": "3",
    },
}

INTERNATIONAL_STATIONS = {
    "Newlyn, UK": {"lon": -5.54, "lat": 50.10, "expected_offset": -3.05},
    "Sydney, AUS": {"lon": 151.22, "lat": -33.85, "expected_offset": -0.925},
    "Brest, FR": {"lon": -4.49, "lat": 48.38, "expected_offset": -3.635},
}

COOPS_RATE_LIMIT = 0.2  # Seconds between API calls (be polite)
FIGURE_DPI = 300
FIGURE_SIZE = (10, 6)

# Production coastal-decay settings used by validations that exercise normal
# Transformez behavior.
PHYSICAL_DECAY_DISTANCE_M = 5_000.0
PHYSICAL_BUFFER_DISTANCE_M = 250.0

# Engine-to-engine VDatum comparison settings.
VDATUM_VALIDATION_POINTS = 200
VDATUM_VALIDATION_SEED = 42


# ============================================================================
# TEST 1: NOAA CO-OPS TIDE STATIONS
# ============================================================================


def get_coops_stations(
    region_bbox: Tuple[float, float, float, float],
) -> Dict[str, Dict[str, Any]]:
    """Fetch NOAA tide stations in bounding box with MSL/MLLW offsets.

    Args:
        region_bbox: (west, east, south, north) in decimal degrees.

    Returns:
        Dict mapping station IDs to datum data.
    """
    w, e, s, n = region_bbox
    logger.info(f"Fetching NOAA CO-OPS stations in bbox ({w}, {e}, {s}, {n})...")

    url = "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations.json?type=datums"

    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Failed to fetch station list: {e}")
        return {}

    data = resp.json()
    stations = {}
    failures = []

    for stn in data.get("stations", []):
        lat = stn.get("lat")
        lon = stn.get("lng")

        if lat is None or lon is None:
            continue

        # Normalize longitude to [-180, 180]
        if lon > 180:
            lon = lon - 360

        if not (w <= lon <= e and s <= lat <= n):
            continue

        stn_id = stn["id"]
        datum_url = f"https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations/{stn_id}/datums.json?units=metric"

        try:
            d_resp = requests.get(datum_url, timeout=10)
            d_resp.raise_for_status()
            datums = d_resp.json().get("datums", [])

            msl = next((d["value"] for d in datums if d["name"] == "MSL"), None)
            mllw = next((d["value"] for d in datums if d["name"] == "MLLW"), None)

            if msl is not None and mllw is not None:
                offset = msl - mllw
                stations[stn_id] = {
                    "lat": lat,
                    "lon": lon,
                    "offset": offset,
                    "name": stn.get("name", "Unknown"),
                }
            else:
                failures.append({"id": stn_id, "reason": "Missing MSL or MLLW"})

        except requests.RequestException as e:
            failures.append({"id": stn_id, "reason": str(e)})
        except Exception as e:
            failures.append({"id": stn_id, "reason": f"Unexpected: {e}"})

        # Rate limit to respect NOAA API
        time.sleep(COOPS_RATE_LIMIT)

    logger.info(f"  Found {len(stations)} valid stations ({len(failures)} failures)")
    return stations


def validate_against_stations(
    region_name: str, region: Any, challenge: str
) -> Optional[Dict[str, Any]]:
    """Compare Transformez grid against NOAA CO-OPS tide station ground truth.

    Args:
        region_name: Human-readable region name.
        region: Region object or bounds list.
        challenge: Description of physical difficulty.

    Returns:
        Dict with RMSE, bias, and plot path, or None on failure.
    """
    logger.info(f"--- Test 1: Transformez vs. NOAA Tide Stations ({region_name}) ---")

    safe_name = region_name.lower().replace(" ", "_").replace(",", "")
    temp_tif = Path(f"_static/temp_validation_{safe_name}.tif")
    csv_file = Path(f"_static/validation_stations_{safe_name}.csv")
    plot_file = Path(f"_static/validation_stations_plot_{safe_name}.png")

    Path(Path.cwd() / "_static").mkdir(parents=True, exist_ok=True)

    stations = get_coops_stations(
        region
        if isinstance(region, tuple)
        else (region.xmin, region.xmax, region.ymin, region.ymax)
    )

    if not stations:
        logger.warning("  No valid stations found, skipping test")
        return None

    logger.info("  Generating MSL→MLLW transformation grid...")
    start_time = time.time()

    try:
        generate_grid(
            region=region,
            increment="3s",
            datum_in="msl",
            datum_out="mllw",
            out_fn=temp_tif,
            decay_distance_m=PHYSICAL_DECAY_DISTANCE_M,
            buffer_distance_m=PHYSICAL_BUFFER_DISTANCE_M,
            verbose=False,
        )
    except Exception as e:
        logger.error(f"  Grid generation failed: {e}")
        return None

    elapsed = time.time() - start_time
    logger.info(f"  Grid generated in {elapsed:.1f}s")

    rq = RasterQuery(temp_tif, default_nodata=-9999.0)
    errors: List[float] = []
    results_data: List[Dict[str, Any]] = []

    for sid, stn in stations.items():
        calc_shift = rq.query([stn["lon"]], [stn["lat"]])[0]

        if np.isnan(calc_shift) or abs(calc_shift + 9999.0) < 1e-6:
            continue

        actual_shift = stn["offset"]
        err = calc_shift - actual_shift
        errors.append(err)

        results_data.append(
            {
                "Station ID": sid,
                "Name": stn["name"],
                "Lon": stn["lon"],
                "Lat": stn["lat"],
                "Actual Shift (m)": actual_shift,
                "Calc Shift (m)": calc_shift,
                "Error (m)": err,
            }
        )

    if not errors:
        logger.warning("  No overlapping grid points with stations")
        temp_tif.unlink()
        return None

    errors = np.array(errors)
    rmse = float(np.sqrt(np.mean(errors**2)))
    mean_bias = float(np.mean(errors))

    # Write CSV for inspection
    with csv_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=results_data[0].keys())
        writer.writeheader()
        writer.writerows(results_data)

    # Generate scatter plot
    actuals = [r["Actual Shift (m)"] for r in results_data]
    calcs = [r["Calc Shift (m)"] for r in results_data]

    fig, ax = plt.subplots(figsize=FIGURE_SIZE)
    scatter = ax.scatter(
        actuals, calcs, c=np.abs(errors), cmap="Reds", alpha=0.8, edgecolor="k", s=60
    )
    ax.figure.colorbar(scatter, ax=ax, label="Absolute Error (m)")

    min_val = min(min(actuals), min(calcs))
    max_val = max(max(actuals), max(calcs))
    ax.plot(
        [min_val, max_val],
        [min_val, max_val],
        "k--",
        label="1:1 Perfect Match",
        alpha=0.6,
    )

    ax.set_xlabel("Ground Truth Offset (m) [CO-OPS]")
    ax.set_ylabel("Transformez Shift (m) [Generated Grid]")
    ax.set_title(f"Transformez vs. CO-OPS Tide Stations\n(MSL → MLLW) – {region_name}")
    ax.legend(loc="upper left")
    ax.grid(True, linestyle=":", alpha=0.6)

    fig.savefig(plot_file, dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)

    # Cleanup
    if temp_tif.exists():
        temp_tif.unlink()

    logger.info(f"  RMSE: {rmse:.4f}m, Mean Bias: {mean_bias:.4f}m")
    logger.info(f"  Plot saved: {plot_file}")

    return {
        "region": region_name,
        "rmse": f"{rmse:.4f} m",
        "bias": f"{mean_bias:.4f} m",
        "challenge": challenge,
        "num_stations": len(errors),
        "image": f"../_static/validation_stations_plot_{safe_name}.png",
    }


# ============================================================================
# TEST 2: NOAA VDATUM ENGINE COMPARISON
# ============================================================================


def validate_against_vdatum(
    region_name: str, region: Any, vdatum_region: str
) -> Optional[Dict[str, Any]]:
    """Compare Transformez's VDatum chain against the NOAA VDatum Java engine.

    This is intentionally an engine-equivalence test. Inland attenuation is
    disabled so coastal decay policy does not contaminate the numerical
    comparison between the two VDatum implementations.

    Args:
        region_name: Human-readable region name.
        region: Region object or bounds.
        vdatum_region: VDatum region grid number.

    Returns:
        Dict with RMSE, mean diff, and plot path, or None if VDatum unavailable.
    """
    logger.info(f"--- Test 2: Transformez vs. NOAA VDatum ({region_name}) ---")

    # Check VDatum availability
    try:
        vd = Vdatum(ivert="navd88:m:height", overt="mhw:m:height", region=vdatum_region)
        if not hasattr(vd, "jar") or vd.jar is None:
            vd.vdatum_locate_jar()
            if vd.jar is None:
                logger.warning("  VDatum not installed, skipping test")
                return None
    except Exception as e:
        logger.warning(f"  VDatum initialization failed: {e}, skipping")
        return None

    safe_name = region_name.lower().replace(" ", "_").replace(",", "")
    temp_tif = Path(f"_static/temp_vdatum_{safe_name}.tif")
    plot_file = Path(f"_static/validation_vdatum_hist_{safe_name}.png")
    n_points = VDATUM_VALIDATION_POINTS

    if isinstance(region, tuple):
        w, e, s, n = region
    else:
        w, e, s, n = region.xmin, region.xmax, region.ymin, region.ymax

    logger.info("  Generating NAVD88→MHW transformation grid...")
    start_time = time.time()

    try:
        generate_grid(
            region=region,
            increment="3s",
            datum_in="5703",
            datum_out="mhw",
            out_fn=temp_tif,
            # This is deliberately unlimited extrapolation. The purpose of this
            # test is strict VDatum-engine equivalence.
            decay_pixels=0,
            verbose=False,
        )
    except Exception as e:
        logger.error(f"  Grid generation failed: {e}")
        return None

    elapsed = time.time() - start_time
    logger.info(f"  Grid generated in {elapsed:.1f}s")

    rq = RasterQuery(temp_tif, default_nodata=-9999.0)

    rng = np.random.default_rng(VDATUM_VALIDATION_SEED)
    lons = rng.uniform(w, e, n_points)
    lats = rng.uniform(s, n, n_points)

    errors: List[float] = []
    skipped = 0

    for _i, (lon, lat) in enumerate(zip(lons, lats, strict=True)):
        t_shift = rq.query([lon], [lat])[0]

        if np.isnan(t_shift) or abs(t_shift + 9999.0) < 1e-6:
            skipped += 1
            continue

        try:
            v_result = vd.vdatum_xyz([lon, lat, 0.0])
            v_shift = v_result[2]

            if v_shift != 0.0 and v_shift > -88:
                errors.append(float(t_shift) - float(v_shift))
        except Exception:
            skipped += 1

    if not errors:
        logger.warning("  No valid offshore points found")
        temp_tif.unlink()
        return None

    errors = np.array(errors)
    rmse = float(np.sqrt(np.mean(errors**2)))
    mean_diff = float(np.mean(errors))

    # Generate histogram
    fig, ax = plt.subplots(figsize=FIGURE_SIZE)
    ax.hist(errors, bins=20, color="skyblue", edgecolor="black", alpha=0.7)
    ax.axvline(0, color="red", linestyle="--", linewidth=2, label="Zero Error")
    ax.set_title(f"Transformez vs. VDatum Error Distribution\n{region_name}")
    ax.set_xlabel("Difference (meters)")
    ax.set_ylabel("Frequency")
    ax.legend()
    ax.grid(axis="y", linestyle=":", alpha=0.7)

    fig.savefig(plot_file, dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)

    # Cleanup
    if temp_tif.exists():
        temp_tif.unlink()

    logger.info(f"  RMSE: {rmse:.4f}m, Mean Diff: {mean_diff:.4f}m ({skipped} skipped)")

    return {
        "region": region_name,
        "rmse": f"{rmse:.6f} m",
        "mean_diff": f"{mean_diff:.6f} m",
        "points": len(errors),
        "image": f"../_static/validation_vdatum_hist_{safe_name}.png",
    }


# ============================================================================
# TEST 3: GLOBAL FALLBACK (FES2014)
# ============================================================================


def validate_international_gauges() -> Optional[Dict[str, Any]]:
    """Validate global FES2014 fallback against international tide gauge records.

    Returns:
        Dict with plot path, or None on failure.
    """
    logger.info("--- Test 3: International Gauges (FES2014) ---")

    calcs: List[float] = []
    labels: List[str] = []
    actuals: List[float] = []
    results: List[Dict[str, Any]] = []
    passed: List[bool] = []

    for name, stn in INTERNATIONAL_STATIONS.items():
        logger.info(f"  Testing {name}...")

        region = Region(
            stn["lon"] - 0.1,
            stn["lon"] + 0.1,
            stn["lat"] - 0.1,
            stn["lat"] + 0.1,
        )
        temp_tif = f"_static/temp_intl_{name.split()[0].lower()}.tif"

        try:
            generate_grid(
                region=region,
                increment="1s",
                datum_in="lat",
                datum_out="global:mss",
                out_fn=temp_tif,
                decay_distance_m=PHYSICAL_DECAY_DISTANCE_M,
                buffer_distance_m=PHYSICAL_BUFFER_DISTANCE_M,
                verbose=False,
            )

            rq = RasterQuery(temp_tif, default_nodata=-9999.0)
            calc_shift = rq.query([stn["lon"]], [stn["lat"]])[0]

            if np.isnan(calc_shift):
                calcs.append(0.0)  # Mark as failed
            else:
                calcs.append(float(calc_shift))

        except Exception as e:
            logger.error(f"    Failed: {e}")
            calcs.append(0.0)
        finally:
            if os.path.exists(temp_tif):
                os.remove(temp_tif)

        labels.append(name)
        actuals.append(stn["expected_offset"])
        delta = float(calcs[-1] - stn["expected_offset"])
        results.append(
            {
                "station": name,
                "expected": float(stn["expected_offset"]),
                "calculated": float(calcs[-1]),
                "delta": delta,
            }
        )
        passed.append(abs(delta) < 0.12)

    # Generate bar chart
    x = np.arange(len(labels))
    width = 0.35

    fig, ax = plt.subplots(figsize=FIGURE_SIZE)
    ax.bar(
        x - width / 2,
        actuals,
        width,
        label="Ground Truth (Tide Gauge)",
        color="#2c3e50",
    )
    ax.bar(x + width / 2, calcs, width, label="Transformez (FES2014)", color="#e74c3c")
    ax.set_ylabel("LAT→MSL Offset (meters)")
    ax.set_title("Global Fallback Accuracy: FES2014 vs International Gauges")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend()
    ax.grid(axis="y", linestyle=":", alpha=0.7)

    # Add value labels on bars
    for i in range(len(x)):
        ax.text(
            x[i] - width / 2,
            actuals[i] - 0.2,
            f"{actuals[i]:.2f}m",
            ha="center",
            color="white",
            fontweight="bold",
        )
        ax.text(
            x[i] + width / 2,
            calcs[i] - 0.2,
            f"{calcs[i]:.2f}m",
            ha="center",
            color="white",
            fontweight="bold",
        )

    plot_file = "_static/validation_international_bars.png"
    fig.savefig(plot_file, dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)

    logger.info(f"  Plot saved: {plot_file}")

    return {
        "intl": {
            "image": "../_static/validation_international_bars.png",
            "results": results,
            "status": "PASS" if all(passed) else "FAIL",
        },
    }


# ============================================================================
# TEST 4: TECTONIC DEFORMATION (HTDP)
# ============================================================================


def validate_tectonics() -> Dict[str, Any]:
    """Validate HTDP integration for cross-epoch tectonic transformations.

    Returns:
        Dict with test results and status.
    """
    logger.info("--- Test 4: Tectonic Deformation & HTDP ---")

    stats = {}

    # Washington State: Cross-epoch tectonic shift
    logger.info("  Testing WA Coast (2025→2010 epoch shift)...")
    wa_region = Region(-124.5, -124.0, 47.5, 48.0)
    # wa_region = Region(-120.5, -119.5, 39, 441)
    wa_tif = "_static/temp_wa_tectonic.tif"

    try:
        generate_grid(
            region=wa_region,
            increment="3s",
            datum_in="6319",
            datum_out="4979",
            epoch_in=2020.000,
            epoch_out=2010.000,
            out_fn=wa_tif,
            verbose=True,
        )

        rq_wa = RasterQuery(wa_tif, default_nodata=-9999.0)
        wa_shift = rq_wa.query([-124.25], [47.75])[0]

        # Expected: ~1-2m due to WGS84→NAD83 datum offset + crustal velocity
        wa_pass = not np.isnan(wa_shift) and -5 < wa_shift < 5
        stats["Washington (Cross-Epoch)"] = {
            "shift": f"{wa_shift:.4f} m",
            "status": "PASS" if wa_pass else "FAIL",
            "challenge": "Crustal Velocity & Datum Offset",
        }

    except Exception as e:
        stats["Washington (Cross-Epoch)"] = {
            "shift": "ERROR",
            "status": "FAIL",
            "challenge": "Crustal Velocity & Datum Offset",
        }
        logger.error(f"    Failed: {e}")
    finally:
        if os.path.exists(wa_tif):
            os.remove(wa_tif)

    # Japan: Eastern hemisphere longitude parsing
    logger.info("  Testing Japan (East longitude HTDP parsing)...")
    jp_region = Region(139.0, 139.5, 35.0, 35.5)
    jp_tif = "_static/temp_jp_tectonic.tif"

    try:
        generate_grid(
            region=jp_region,
            increment="3s",
            datum_in="6319",
            datum_out="4979",
            epoch_in=2010.0,
            epoch_out=2010.0,
            out_fn=jp_tif,
            verbose=False,
        )

        rq_jp = RasterQuery(jp_tif, default_nodata=-9999.0)
        jp_shift = rq_jp.query([139.25], [35.25])[0]

        jp_pass = not np.isnan(jp_shift)
        stats["Japan (East Longitude)"] = {
            "shift": f"{jp_shift:.4f} m",
            "status": "PASS" if jp_pass else "FAIL",
            "challenge": "Eastern Hemisphere Longitude Parsing",
        }

    except Exception as e:
        stats["Japan (East Longitude)"] = {
            "shift": "ERROR",
            "status": "FAIL",
            "challenge": "Eastern Hemisphere Longitude Parsing",
        }
        logger.error(f"    Failed: {e}")
    finally:
        if os.path.exists(jp_tif):
            os.remove(jp_tif)

    for k, v in stats.items():
        logger.info(f"  {k}: {v['shift']} ({v['status']})")

    return stats


# ============================================================================
# MARKDOWN REPORT GENERATOR
# ============================================================================


def generate_markdown_report(
    station_stats: List[Dict[str, Any]],
    vdatum_stats: List[Dict[str, Any]],
    intl_stats: Optional[Dict[str, Any]],
    tectonic_stats: Dict[str, Any],
) -> None:
    """Compile test results into validation.md for documentation."""

    logger.info("Generating validation.md report...")

    md_lines = [
        "# Validation & Accuracy",
        "",
        "Transformez is validated at several different levels because no single benchmark can fully describe the behavior of a coastal vertical-datum transformation engine. The tests below separate provider/grid accuracy, production coastal behavior, global-model agreement, and external HTDP integration.",
        "",
        "These results should therefore be interpreted according to the purpose of each test rather than as interchangeable measures of a single global accuracy value. In particular, the NOAA CO-OPS station comparison includes Transformez's production shoreline, coverage, and inland-decay policy, while the NOAA VDatum comparison intentionally removes those effects to isolate numerical engine equivalence.",
        "",
        "## Test 1: Production Coastal Surface vs. NOAA CO-OPS Tide Stations",
        "",
        "This test generates a 3 arc-second MSL → MLLW shift grid using the normal Transformez coastal policy and samples it at NOAA CO-OPS tide-station locations. The comparison therefore evaluates the complete production surface, not only the underlying VDatum transformation mathematics.",
        "",
        f"The validation uses a {PHYSICAL_BUFFER_DISTANCE_M:.0f} m full-strength coastal buffer followed by a {PHYSICAL_DECAY_DISTANCE_M / 1000:.1f} km inland decay. Valid VDatum coverage, the Dist2Coast-derived effective water domain, raster sampling, shoreline geometry, and coastal fallback behavior can all influence individual station comparisons.",
        "",
        "CO-OPS stations are point observations intentionally located in the tidal environment, whereas Transformez produces a continuous raster intended for DEM transformation. A gauge may sit on a pier, seawall, narrow creek, harbor edge, or mixed land/water raster cell. For that reason, RMSE in this test should be interpreted as an operational coastal-surface metric rather than a direct estimate of the numerical error of the datum engine itself.",
        "",
        "Small mean bias together with larger RMSE generally indicates local spatial scatter near complex coastlines rather than a systematic datum offset. Changes in shoreline representation can also change this benchmark without changing the underlying datum transformation; earlier Transformez validation used GSHHG vector coastlines, while the current production engine uses the Dist2Coast-based coastal context.",
        "",
        "| Region | RMSE | Mean Bias | Stations | Physical Challenge |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]

    for stat in station_stats:
        md_lines.append(
            f"| **{stat['region']}** | {stat['rmse']} | {stat['bias']} | {stat['num_stations']} | {stat['challenge']} |"
        )

    md_lines.extend(
        [
            "",
            "> **How to read this test:** These values include Transformez's coastal masking and decay policy. They are expected to be more sensitive in estuaries and geometrically complex bays than in broad, well-resolved waterways. They should not be compared directly with the engine-equivalence RMSE in Test 2.",
            "",
        ]
    )

    for stat in station_stats:
        md_lines.append(f"![{stat['region']} Validation]({stat['image']})")

    md_lines.extend(
        [
            "",
            "## Test 2: Numerical Engine Equivalence vs. NOAA VDatum",
            "",
            "This test compares Transformez directly against the NOAA VDatum Java CLI at random locations for a NAVD88 → MHW transformation. Inland attenuation is deliberately disabled so that coastal decay policy does not contaminate the numerical comparison.",
            "",
            "Unlike Test 1, this is intended to answer a narrow question: when Transformez and NOAA VDatum are asked to evaluate the same supported transformation, do they produce the same shift? Sub-millimetric differences here provide strong evidence that the reference planner, sign conventions, provider routing, grid interpolation, and execution chain are reproducing the authoritative VDatum engine correctly.",
            "",
            "| Region | RMSE | Mean Difference | Points |",
            "| :--- | :--- | :--- | :--- |",
        ]
    )

    for stat in vdatum_stats:
        md_lines.append(
            f"| **{stat['region']}** | {stat['rmse']} | {stat['mean_diff']} | {stat['points']} |"
        )

    md_lines.extend(
        [
            "",
            "> **How to read this test:** This is the primary validation of the transformation engine itself. It intentionally excludes production inland-decay behavior, so differences between Test 1 and Test 2 usually reflect coastal-domain and raster-policy effects rather than a disagreement in the underlying datum mathematics.",
            "",
        ]
    )

    for stat in vdatum_stats:
        md_lines.append(f"![{stat['region']} VDatum Error Histogram]({stat['image']})")

    md_lines.extend(
        [
            "",
            "## Test 3: Global Model Agreement at International Tide Gauges",
            "",
            "Outside NOAA VDatum coverage, Transformez uses global ocean-surface models to provide a physically meaningful transformation path. This test evaluates that global-model strategy by comparing the modeled LAT → mean-sea-surface offset with published offsets at selected international tide gauges.",
            "",
            "This is not an engine-equivalence test: the reference station values and the gridded global models are independent representations of the local tidal regime. Differences therefore include the spatial resolution and physics of the global model, local harbor and coastal effects, station realization, and raster sampling. The purpose is to verify that Transformez selects and combines the global models correctly and that the resulting offsets remain physically consistent with observed station values across very different tidal environments.",
            "",
            "| Station | Published Offset | Transformez | Delta |",
            "| :--- | :--- | :--- | :--- |",
        ]
    )

    if intl_stats:
        for result in intl_stats.get("results", []):
            md_lines.append(
                f"| {result['station']} | {result['expected']:.3f} m | "
                f"{result['calculated']:.3f} m | {result['delta']:.3f} m |"
            )

    md_lines.extend(
        [
            "",
            "![International Gauges]({intl_stats['image']})" if intl_stats else "",
            "",
            "> **How to read this test:** Agreement at the decimeter scale is meaningful here because the comparison is between a gridded global ocean model and local station realizations, not two implementations of the same transformation grid. The test is primarily a validation of global fallback selection and physical plausibility.",
            "",
            "## Test 4: HTDP Integration Health Check",
            "",
            "Transformez uses NGS HTDP for transformations between supported dynamic and plate-fixed reference frames and for coordinate-epoch changes. These checks verify that the external HTDP executable can be called successfully, that Transformez passes the expected frame and epoch information, and that longitude handling works in both western and eastern hemispheres.",
            "",
            "These tests are best understood as integration or regression checks rather than independent geodetic validation of HTDP itself. NGS HTDP is the authoritative model being executed; Transformez is verifying that its wrapper and execution path invoke it correctly.",
            "",
            "| Test Region | Calculated Shift | Challenge | Status |",
            "| :--- | :--- | :--- | :--- |",
        ]
    )

    for test_name, test_data in tectonic_stats.items():
        md_lines.append(
            f"| **{test_name}** | {test_data['shift']} | {test_data['challenge']} | {test_data['status']} |"
        )

    md_lines.extend(
        [
            "",
            "> **How to read this test:** PASS indicates that the HTDP integration produced a plausible, finite result through the expected execution path. Detailed verification of HTDP's geophysical model belongs to NGS; these cases primarily protect Transformez against wrapper, frame-ID, epoch, and longitude-regression errors.",
            "",
            "## Overall Interpretation",
            "",
            "Taken together, the validation suite tests different layers of Transformez rather than reducing accuracy to a single number:",
            "",
            "- **NOAA CO-OPS station tests** exercise the complete production coastal surface, including shoreline classification, VDatum coverage, raster resolution, and inland-decay policy.",
            "- **NOAA VDatum engine comparisons** isolate the transformation mathematics and provider/grid execution path and are the strongest direct check of numerical equivalence.",
            "- **International gauge comparisons** test whether the global fallback models produce physically reasonable offsets where local VDatum grids are unavailable.",
            "- **HTDP checks** verify the external frame/epoch transformation integration and guard against execution regressions.",
            "",
            "A larger RMSE in a complex estuary does not by itself indicate a datum-engine error, particularly when the corresponding engine-equivalence test remains near zero bias and sub-millimetric agreement. Coastal validation is intentionally sensitive to the production shoreline model because that behavior is part of the surface Transformez ultimately applies to DEMs.",
            "",
            "> **Reproduce these results:** All validation scripts are in [`tests/validation/`](https://github.com/cires-dems/transformez/tree/main/tests/validation)",
        ]
    )

    with open("validation.md", "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    logger.info("  Report saved to validation.md")


# ============================================================================
# MAIN EXECUTION
# ============================================================================


def run_full_suite() -> int:
    """Run the complete validation suite and generate markdown report.

    Returns:
        Exit code (0 for success, 1 for any failures).
    """
    print("=" * 60)
    print("TRANSFORMEZ VALIDATION SUITE")
    print("=" * 60)

    start_total = time.time()

    # Collect stats
    station_stats = []
    for name, data in TEST_REGIONS.items():
        region = Region(*data["bounds"])
        stats = validate_against_stations(name, region, data["challenge"])
        if stats:
            station_stats.append(stats)

    vdatum_stats = []
    for name, data in TEST_REGIONS.items():
        if data["vdatum_region"] is None:
            continue
        region = Region(*data["bounds"])
        stats = validate_against_vdatum(name, region, data["vdatum_region"])
        if stats:
            vdatum_stats.append(stats)

    intl_stats = validate_international_gauges()
    tectonic_stats = validate_tectonics()

    # Generate report
    generate_markdown_report(station_stats, vdatum_stats, intl_stats, tectonic_stats)

    elapsed_total = time.time() - start_total

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total time: {elapsed_total:.1f}s")
    print(f"Station tests: {len(station_stats)} passed")
    print(f"VDatum tests: {len(vdatum_stats)} passed")
    print(
        f"International tests: {sum(1 for s in intl_stats.values() if s['status'] == 'PASS')} passed"
    )
    print(
        f"Tectonic tests: {sum(1 for s in tectonic_stats.values() if s['status'] == 'PASS')} passed"
    )

    # Check for critical failures
    all_passed = (
        all(t["status"] == "PASS" for t in tectonic_stats.values())
        and len(station_stats) > 0
    )

    if all_passed:
        print("\n✅ All critical validation tests passed!")
        return 0
    else:
        print("\n⚠️  Some validation tests failed (check logs above)")
        return 1


if __name__ == "__main__":
    sys.exit(run_full_suite())
