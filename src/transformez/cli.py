#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.cli
~~~~~~~~~~~~~~~

The command-line interface for Transformez.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import sys
import click
from pathlib import Path
from typing import Optional, Any

from fetchez.utils import FetchezMainGroup, FetchezMainCommand
from fetchez.cli import setup_logging

from transformez import api

TRANSFORMEZ_COMMANDS = {
    "Execution": ["build", "shift"],
    "Discovery": ["list", "list-reference", "prefetch", "plan"],
    "External": ["htdp", "vdatum"],
}


class TransformezMainGroup(FetchezMainGroup):
    """A custom Click Group that handles deprecated aliases."""

    def get_command(self, ctx, cmd_name):
        if cmd_name == "grid":
            click.secho(
                " DEPRECATION WARNING: 'transformez grid' is deprecated and will be removed in a future release.\n"
                "Please use 'transformez build'..",
                fg="yellow",
                err=True,
            )
            return click.Group.get_command(self, ctx, "build")

        elif cmd_name == "raster":
            click.secho(
                " DEPRECATION WARNING: 'transformez raster' is deprecated and will be removed in a future release.\n"
                "Please use 'transformez shift'...",
                fg="yellow",
                err=True,
            )
            return click.Group.get_command(self, ctx, "shift")

        return click.Group.get_command(self, ctx, cmd_name)


@click.group(
    name="transform",
    cls=TransformezMainGroup,
    fetchez_commands=TRANSFORMEZ_COMMANDS,
)
@click.version_option(package_name="transformez")
@click.option("--verbose", is_flag=True, help="Enable verbose debug logging.")
@click.option("--quiet", is_flag=True, help="Suppress non-error output.")
def transformez_cli(verbose: bool, quiet: bool) -> None:
    """Build vertical datum shift grids and transform elevation rasters."""

    setup_logging(name="transformez", quiet=quiet, verbose=verbose)
    pass


# =====================================================================
# GENERATE SHIFT GRID
# =====================================================================
@transformez_cli.command("build", cls=FetchezMainCommand)
@click.option("-R", "--region", required=True, help="Bounding box or location string.")
@click.option("-E", "--increment", required=True, help="Resolution (e.g., 1s, 30m).")
@click.option(
    "-I", "--input-datum", required=True, help="Source Datum (e.g., 'mllw', '5703')."
)
@click.option(
    "-O",
    "--output-datum",
    required=True,
    help="Target Datum (e.g., '4979', '5703:g2012b').",
)
@click.option("--out", "-o", help="Output filename (default: auto-named).")
@click.option(
    "--decay-pixels",
    type=int,
    default=100,
    help="DEPRECATED: Pixel-based inland decay distance; use --decay-distance.",
)
@click.option(
    "--decay-distance",
    type=click.FloatRange(min=0.0),
    default=None,
    metavar="METERS",
    help="Distance over which tidal shifts decay to zero inland.",
)
@click.option(
    "--buffer-distance",
    type=click.FloatRange(min=0.0),
    default=None,
    metavar="METERS",
    help="Distance inland to preserve the full coastal shift before decay begins.",
)
@click.option(
    "--max-vdatum-extension",
    type=click.FloatRange(min=0.0),
    default=None,
    metavar="METERS",
    help="Maximum inland extension of valid VDatum coverage beyond the shoreline.",
)
@click.option(
    "--no-inland-decay",
    "extrapolate_inland",
    is_flag=True,
    help="Disable inland decay of tidal shifts. Use with caution: tidal transformations may then extend far inland.",
)
@click.option(
    "--use-stations",
    is_flag=True,
    help="Use tide-station interpolation for tidal transformations when available.",
)
@click.option(
    "--preview", is_flag=True, help="Display a preview of the generated shift grid."
)
def transform_grid(
    region: str,
    increment: str,
    input_datum: str,
    output_datum: str,
    out: Optional[str],
    decay_pixels: int,
    decay_distance: Optional[float],
    buffer_distance: Optional[float],
    max_vdatum_extension: Optional[float],
    extrapolate_inland: bool,
    use_stations: bool,
    preview: bool,
) -> None:
    """Build a vertical datum shift grid for a region."""

    click.secho(
        f"Generating vertical shift grid for region: {region}...",
        fg="cyan",
        bold=True,
    )
    click.echo(f"   Shift: {input_datum} ➔ {output_datum} @ {increment}")

    out_fn = out or f"shift_{input_datum}_to_{output_datum.replace(':', '_')}.tif"

    result = api.generate_grid(
        region=region,
        increment=increment,
        datum_in=input_datum,
        datum_out=output_datum,
        decay_pixels=decay_pixels,
        decay_distance_m=decay_distance,
        buffer_distance_m=buffer_distance,
        max_vdatum_extension_m=max_vdatum_extension,
        extrapolate_inland=extrapolate_inland,
        out_fn=out_fn,
        use_stations=use_stations,
        verbose=True,
    )

    if preview and result is not None:
        api.plot_grid(result, region)

    if result is not None:
        click.secho(
            f"Successfully generated shift grid: {out_fn}", fg="green", bold=True
        )
    else:
        click.secho("Failed to generate shift grid.", fg="red")
        sys.exit(1)


# =====================================================================
# TRANSFORM EXISTING RASTER (DEM)
# =====================================================================
@transformez_cli.command("shift", cls=FetchezMainCommand)
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option("-I", "--input-datum", required=True, help="Source datum (e.g., 'mllw').")
@click.option(
    "-O", "--output-datum", required=True, help="Target datum (e.g., '5703:g2012b')."
)
@click.option(
    "--in-units",
    default="auto",
    type=click.Choice(["auto", "m", "ft", "us-ft"]),
    help="Vertical units of the input raster.",
)
@click.option(
    "--out-units",
    default="auto",
    type=click.Choice(["auto", "m", "ft", "us-ft"]),
    help="Vertical units of the output raster.",
)
@click.option("--out", "-o", help="Output filename (default: auto-named).")
@click.option(
    "--decay-pixels",
    type=int,
    default=100,
    help="DEPRECATED: Pixel-based inland decay distance; use --decay-distance.",
)
@click.option(
    "--decay-distance",
    type=click.FloatRange(min=0.0),
    default=None,
    metavar="METERS",
    help="Distance over which tidal shifts decay to zero inland.",
)
@click.option(
    "--buffer-distance",
    type=click.FloatRange(min=0.0),
    default=None,
    metavar="METERS",
    help="Distance inland to preserve the full coastal shift before decay begins.",
)
@click.option(
    "--max-vdatum-extension",
    type=click.FloatRange(min=0.0),
    default=None,
    metavar="METERS",
    help="Maximum inland extension of valid VDatum coverage beyond the shoreline.",
)
@click.option(
    "--no-inland-decay",
    "extrapolate_inland",
    is_flag=True,
    help="Disable inland decay of tidal shifts. Use with caution: tidal transformations may then extend far inland.",
)
@click.option(
    "--use-stations",
    is_flag=True,
    help="Use tide-station interpolation for tidal transformations when available.",
)
@click.option(
    "--save-shift",
    is_flag=True,
    help="Save the aligned vertical shift grid to disk alongside the output DEM.",
)
def transform_raster(
    input_file: Path,
    input_datum: str,
    output_datum: str,
    in_units: str,
    out_units: str,
    out: Optional[str],
    decay_pixels: int,
    decay_distance: Optional[float],
    buffer_distance: Optional[float],
    max_vdatum_extension: Optional[float],
    extrapolate_inland: bool,
    use_stations: bool,
    save_shift: bool,
) -> None:
    """Transform an elevation raster between vertical datums."""

    click.secho(f"Transforming raster: {input_file}", fg="cyan", bold=True)
    click.echo(f"   Shift: {input_datum} ➔ {output_datum}")

    result = api.transform_raster(
        input_raster=input_file,
        datum_in=input_datum,
        datum_out=output_datum,
        decay_pixels=decay_pixels,
        decay_distance_m=decay_distance,
        buffer_distance_m=buffer_distance,
        max_vdatum_extension_m=max_vdatum_extension,
        extrapolate_inland=extrapolate_inland,
        output_raster=out,
        z_unit_in=in_units,
        z_unit_out=out_units,
        use_stations=use_stations,
        save_shift=save_shift,
        verbose=True,
    )

    if result:
        click.secho(f"Successfully transformed raster: {result}", fg="green", bold=True)
    else:
        click.secho("Failed to transform raster.", fg="red")
        sys.exit(1)


@transformez_cli.command("plan", cls=FetchezMainCommand)
@click.option(
    "-I", "--input-datum", required=True, help="Source Datum (e.g., 'mllw', '5703')."
)
@click.option(
    "-O",
    "--output-datum",
    required=True,
    help="Target Datum (e.g., '4979', '5703:g2012b').",
)
@click.option(
    "--epoch-in", default="2010.0", help="Source coordinate epoch (default: 2010.0)."
)
@click.option(
    "--epoch-out", default="2010.0", help="Target coordinate epoch (default: 2010.0)."
)
def transform_plan(
    input_datum: str,
    output_datum: str,
    epoch_in: str,
    epoch_out: str,
) -> None:
    """Preview the geodetic transformation steps without executing them."""

    from transformez.reference.parser import parse_reference
    from transformez.reference.resolver import resolve_reference
    from transformez.reference.planner import (
        TransformationPlanner,
        GridOperation,
        FrameOperation,
    )

    try:
        src_parsed = parse_reference(input_datum)
        dst_parsed = parse_reference(output_datum)

        src_resolved = resolve_reference(src_parsed, default_epoch=float(epoch_in))
        dst_resolved = resolve_reference(dst_parsed, default_epoch=float(epoch_out))

        plan = TransformationPlanner.build_plan(src_resolved, dst_resolved)

    except Exception as e:
        click.secho(f"Failed to build plan: {e}", fg="red")
        sys.exit(1)

    click.secho(
        f"\n🗺️  Transformation Plan: {input_datum} ➔ {output_datum}",
        fg="cyan",
        bold=True,
    )

    src_name = (
        plan.source.vertical.reference.name if plan.source.vertical else "Unknown"
    )
    dst_name = (
        plan.target.vertical.reference.name if plan.target.vertical else "Unknown"
    )

    click.echo(f"  Source: {src_name} (@ {plan.source.coordinate_epoch})")
    click.echo(f"  Target: {dst_name} (@ {plan.target.coordinate_epoch})\n")

    if plan.horizontal_transform:
        click.secho("  [Horizontal Operation]", fg="yellow")
        click.echo("  • Reprojecting horizontal coordinates.\n")

    if not plan.steps:
        click.secho(
            "  ✓ Identity Transformation (No vertical steps required).", fg="green"
        )
        return

    click.secho("  [Vertical Operations]", fg="yellow")
    for i, step in enumerate(plan.steps, start=1):
        if isinstance(step, GridOperation):
            # Parse Grid Operations
            direction_str = (
                "Extract from" if step.direction == "from_native" else "Step to"
            )
            engine_str = step.binding.engine.replace("_", " ").title()
            model_str = f" via {step.reference.model}" if step.reference.model else ""

            click.echo(
                f"  {i}. Grid Shift [{engine_str}]: "
                f"{direction_str} Native Hub ({step.native_frame.name}){model_str}"
            )

        elif isinstance(step, FrameOperation):
            # Parse HTDP/Frame Operations
            click.echo(
                f"  {i}. Frame Shift [HTDP]: "
                f"ID {step.source_id} (@ {step.epoch_in}) ➔ ID {step.target_id} (@ {step.epoch_out})"
            )

    click.echo()


# --- LIST DATUMS, ETC. ---
@transformez_cli.command("list-reference", cls=FetchezMainCommand)
def transform_list_reference() -> None:
    """List all supported vertical datums, EPSG codes, and geoids."""

    from transformez.reference.bindings import (
        CUSTOM_VERTICAL_REFERENCES,
        OPERATION_BINDINGS,
        HTDP_FRAME_BINDINGS,
    )
    from transformez.reference.types import VerticalKind

    tidal_surfaces = []
    global_models = []

    for ref_id, ref_obj in CUSTOM_VERTICAL_REFERENCES.items():
        if ref_obj.kind == VerticalKind.TIDAL_HEIGHT:
            tidal_surfaces.append((ref_id, ref_obj.name))
        elif ref_obj.kind == VerticalKind.MODEL_SURFACE:
            global_models.append((ref_id, ref_obj.name))

    geoid_epsgs = []
    for ref_id, binding in OPERATION_BINDINGS.items():
        if ref_id.startswith("epsg:") and binding.engine == "proj":
            ref_vert_obj = CUSTOM_VERTICAL_REFERENCES.get(ref_id)
            name = ref_vert_obj.name if ref_vert_obj else "Unknown"
            geoid_epsgs.append(
                (ref_id.replace("epsg:", ""), name, binding.default_model)
            )

    click.secho("\n🌊 Supported Tidal Surfaces (NOAA VDatum):", fg="cyan", bold=True)
    for ref_id, name in sorted(tidal_surfaces):
        click.echo(f"  {ref_id:<12} : {name:<30}")

    click.secho("\n🛰️  Global Ocean Proxies (FES2014 / DTU25):", fg="cyan", bold=True)
    for ref_id, name in sorted(global_models):
        click.echo(f"  {ref_id:<12} : {name:<30}")

    click.secho("\n🌐 Ellipsoidal / Frame Datums (HTDP Hubs):", fg="cyan", bold=True)
    for epsg_str, htdp_binding in HTDP_FRAME_BINDINGS.items():
        epsg_code = epsg_str.split(":")[1]
        click.echo(
            f"  {epsg_code:<12} : {htdp_binding.name:<30} (Epoch: {htdp_binding.reference_epoch})"
        )

    click.secho("\n🏔️  Orthometric / Geoid-Based (EPSG):", fg="cyan", bold=True)
    for epsg_code, name, default_geoid in sorted(geoid_epsgs):
        geoid_str = default_geoid.replace("geoid:", "") if default_geoid else "None"
        click.echo(f"  {epsg_code:<12} : {name:<30} (Default Geoid: {geoid_str})")

    click.secho("\n🌍 Available Geoids (via PROJ):", fg="cyan", bold=True)
    click.echo("  g2018, g2012b, geoid09")

    # ---> HIERARCHY DOCUMENTATION <---
    click.secho(
        "\n🔄 Dynamic Fallback Hierarchy (Coastal/Tidal):", fg="magenta", bold=True
    )
    click.echo("  1. NOAA VDatum       : High-res regional hydrodynamics (USA Base).")
    click.echo(
        "  2. FES2014 / Global  : Satellite altimetry proxy for offshore/international."
    )
    click.echo(
        "  3. Tide Station RBF  : Live CO-OPS splines (Activated via --use-stations)."
    )
    click.echo(
        "  4. Constant Offset   : Safety fallback for sparse coverage (< 3 stations)."
    )
    click.echo("  5. Inland Decay      : Coast-aware physical distance tidal decay.")


@transformez_cli.command("list", cls=FetchezMainCommand)
def transform_list() -> None:
    """List all supported vertical datums, EPSG codes, and geoids."""

    from transformez.definitions import Datums

    click.secho("\n🌊 Supported Tidal Surfaces:", fg="cyan", bold=True)
    for key, v in Datums.SURFACES.items():
        region_str = v.get("region", "global").upper()
        click.echo(f"  {key:<12} : {v.get('name', key):<30} [{region_str}]")

    click.secho("\n🌐 Ellipsoidal / Frame Datums (EPSG):", fg="cyan", bold=True)
    click.echo(f"  {'4979':<12} : WGS84 - World Geodetic System 1984")
    click.echo(f"  {'6319':<12} : NAD83 - North American Datum 1983")

    click.secho("\n🏔️  Orthometric / Geoid-Based (EPSG):", fg="cyan", bold=True)
    for epsg_key, v in Datums.CDN.items():
        epsg_code = v.get("epsg", epsg_key)
        geoid_str = v.get("default_geoid", "None")
        click.echo(
            f"  {str(epsg_code):<12} : {v.get('name', 'Unknown'):<30} (Default Geoid: {geoid_str})"
        )

    click.secho("\n🌍 Available Geoids:", fg="cyan", bold=True)
    click.echo(f"  {', '.join(Datums.GEOIDS.keys())}")

    # ---> HIERARCHY DOCUMENTATION <---
    click.secho(
        "\n🔄 Dynamic Fallback Hierarchy (Coastal/Tidal):", fg="magenta", bold=True
    )
    click.echo("  1. NOAA VDatum       : High-res regional hydrodynamics (USA Base).")
    click.echo(
        "  2. FES2014 / Global  : Satellite altimetry proxy for offshore/international."
    )
    click.echo(
        "  3. Tide Station RBF  : Live CO-OPS splines (Activated via --use-stations)."
    )
    click.echo(
        "  4. Constant Offset   : Safety fallback for sparse coverage (< 3 stations)."
    )
    click.echo(
        "  5. Inland Decay      : Coast-aware physical or pixel-based tidal decay."
    )

    click.echo(
        """
        Datum syntax:
          Specify a geoid with DATUM:GEOID, e.g. 5703:g2012b.\n
        """
    )


# --- HTDP CLI GROUP ---
@transformez_cli.group(
    cls=FetchezMainGroup, name="htdp", fetchez_commands=["install", "run"]
)
def htdp_group() -> None:
    """Manage the NGS HTDP transformation engine."""

    pass


@htdp_group.command("install", cls=FetchezMainCommand)
@click.option(
    "--version",
    default="3.5.0",
    help="HTDP version to install (e.g., 3.3.0, 3.5.0, 3.6.0)",
)
def install_htdp(version: str) -> None:
    """Download and install the NGS HTDP executable."""

    from transformez.htdp import install_htdp_binary

    install_htdp_binary(version=version)


@htdp_group.command("run", cls=FetchezMainCommand)
@click.option("--control", help="input control file, if omitted, run interactively")
def run_htpd(control: Optional[Any]) -> None:
    """Run the installed NGS HTDP executable."""

    from transformez.htdp import HTDP

    HTDP().run_cmd(control)


# --- VDATUM CLI GROUP ---
@transformez_cli.group(
    cls=FetchezMainGroup, name="vdatum", fetchez_commands=["install", "run", "list"]
)
def vdatum_group() -> None:
    """Manage the NOAA VDatum transformation engine."""

    pass


@vdatum_group.command("install")
def install_vdatum() -> None:
    """Download and install the NOAA VDatum software."""

    from transformez.vdatum import install_vdatum_jar

    install_vdatum_jar()


@vdatum_group.command("run", cls=FetchezMainCommand)
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.argument("output_file", type=click.Path(path_type=Path))
@click.option(
    "-I", "--in-datum", required=True, help="VDatum input datum string (e.g., 'navd88')"
)
@click.option(
    "-O",
    "--out-datum",
    required=True,
    help="VDatum output datum string (e.g., 'nad83_2011')",
)
@click.option("--in-unit", default="m", help="Input units (m, ft, us-ft)")
@click.option("--out-unit", default="m", help="Output units (m, ft, us-ft)")
@click.option("--region", default="4", help="VDatum region grid")
def run_vdatum_cli(
    input_file: str,
    output_file: str,
    in_datum: str,
    out_datum: str,
    in_unit: str,
    out_unit: str,
    region: str,
) -> None:
    """Transform an XYZ file using the local NOAA VDatum engine."""

    from transformez.vdatum import Vdatum

    Vdatum(
        ivert=f"{in_datum}:{in_unit}:height",
        overt=f"{out_datum}:{out_unit}:height",
        region=region,
    ).run_vdatum(input_file)


@vdatum_group.command("list", cls=FetchezMainCommand)
def vdatum_list() -> None:
    """Show information reported by the installed VDatum engine."""

    from transformez.vdatum import Vdatum

    vd = Vdatum().vdatum_help()
    click.echo(vd)


# --- PREFETCH CLI GROUP ---
@transformez_cli.command("prefetch", cls=FetchezMainCommand)
@click.option("-R", "--region", required=True, help="Bounding box or location string.")
@click.option(
    "-I",
    "--input-datum",
    help="Source Datum (Optional: limits fetch to specific chain).",
)
@click.option(
    "-O",
    "--output-datum",
    help="Target Datum (Optional: limits fetch to specific chain).",
)
@click.option(
    "--all",
    "fetch_all",
    is_flag=True,
    help="Download all available transformation datasets for the region.",
)
def transform_prefetch(
    region: str,
    input_datum: Optional[str],
    output_datum: Optional[str],
    fetch_all: bool,
) -> None:
    """Download transformation data for offline use.

    Examples:\n
      Prefetch a specific conversion : transformez prefetch -R loc:"Newport, OR" -I mllw -O 5703
      Prefetch EVERYTHING for a region: transformez prefetch -R loc:"Miami, FL" --all
      Prefetch the entire planet      : transformez prefetch -R -180/180/-90/90 --all
    """

    click.secho(
        f"Populating offline cache for region: {region}...", fg="cyan", bold=True
    )

    result = api.prefetch_region(
        region=region,
        datum_in=input_datum,
        datum_out=output_datum,
        fetch_all=fetch_all,
        verbose=True,
    )

    if result:
        click.secho(
            f"Offline cache populated for {region}.",
            fg="green",
            bold=True,
        )
    else:
        click.secho("Prefetch encountered errors. Check logs for details.", fg="red")
        sys.exit(1)


if __name__ == "__main__":
    transformez_cli()
