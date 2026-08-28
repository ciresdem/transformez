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
from typing import Optional, Any

from fetchez.utils import FetchezMainGroup, FetchezMainCommand
from fetchez.cli import setup_logging

from transformez import api

TRANSFORMEZ_COMMANDS = {
    "Execution": ["grid", "raster"],
    "Discovery": ["list", "prefetch"],
    "External": ["htdp", "vdatum"],
}


class TransformezMainGroup(FetchezMainGroup):
    """A custom Click Group that handles deprecated aliases."""


@click.group(
    name="transform",
    cls=TransformezMainGroup,
    fetchez_commands=TRANSFORMEZ_COMMANDS,
)
@click.version_option(package_name="transformez")
@click.option("--verbose", is_flag=True, help="Enable verbose debug logging.")
@click.option("--quiet", is_flag=True, help="Suppress non-error output.")
def transformez_cli(verbose: bool, quiet: bool) -> None:
    """Apply vertical datum transformations and generate shift grids."""

    setup_logging(name="transformez", quiet=quiet, verbose=verbose)
    pass


@transformez_cli.command("run", cls=FetchezMainCommand)
@click.argument("input_file", required=False)
@click.option(
    "-R", "--region", help="Bounding box or location string (if no input file)."
)
@click.option(
    "-E", "--increment", help="Resolution (e.g., 1s, 30m) (if no input file)."
)
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
    help="Number of pixels to decay tidal shifts inland.",
)
@click.option(
    "--decay-distance",
    type=click.FloatRange(min=0.0),
    default=None,
    metavar="METERS",
    help=(
        "Decay tidal shifts inland over this physical distance in meters. "
        "When provided, overrides --decay-pixels."
    ),
)
@click.option(
    "--buffer-distance",
    type=click.FloatRange(min=0.0),
    default=None,
    metavar="METERS",
    help="Preserve the full coastal shift this far inland before decay begins.",
)
@click.option(
    "--max-vdatum-extension",
    type=click.FloatRange(min=0.0),
    default=None,
    metavar="METERS",
    help=(
        "Maximum inland distance where VDatum coverage may extend the "
        "effective water domain."
    ),
)
@click.option(
    "--no-inland-decay",
    "extrapolate_inland",
    is_flag=True,
    help=(
        "Extrapolate tidal shifts inland without attenuation. "
        "Use with caution; tidal transformations may be applied far inland."
    ),
)
@click.option(
    "--use-stations",
    is_flag=True,
    help="Force RBF interpolation using live tide stations instead of global satellite models.",
)
@click.option("--preview", is_flag=True, help="Preview the transformation output.")
def transform_run(
    input_file: Optional[str],
    region: Optional[str],
    increment: Optional[str],
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
    """Transform a raster's vertical datum or generate a standalone shift grid.

    If an INPUT_FILE is provided, that specific raster is transformed in place.
    If no INPUT_FILE is provided, -R and -E must be used to generate a shift grid.

    Examples:\n
      Transform a DEM : transformez run my_dem.tif -I mllw -O 5703
      Generate a Grid : transformez run -R loc:"Miami" -E 1s -I mllw -O 4979
    """

    if input_file:
        click.secho(f"Transforming raster: {input_file}", fg="cyan", bold=True)
        click.echo(f"   Shift: {input_datum} ➔ {output_datum}")

        raster_result = api.transform_raster(
            input_raster=input_file,
            datum_in=input_datum,
            datum_out=output_datum,
            decay_pixels=decay_pixels,
            decay_distance_m=decay_distance,
            buffer_distance_m=buffer_distance,
            max_vdatum_extension_m=max_vdatum_extension,
            extrapolate_inland=extrapolate_inland,
            output_raster=out,
            use_stations=use_stations,
            verbose=True,
        )

        if raster_result:
            click.secho(
                f"Successfully transformed raster: {raster_result}",
                fg="green",
                bold=True,
            )
        else:
            click.secho("Failed to transform raster.", fg="red")
            sys.exit(1)

    elif region and increment:
        click.secho(
            f"Generating vertical shift grid for region: {region}...",
            fg="cyan",
            bold=True,
        )
        click.echo(f"   Shift: {input_datum} ➔ {output_datum} @ {increment}")

        out_fn = out or f"shift_{input_datum}_to_{output_datum.replace(':', '_')}.tif"

        grid_result = api.generate_grid(
            region=region,
            increment=increment,
            datum_in=input_datum,
            datum_out=output_datum,
            decay_pixels=decay_pixels,
            decay_distance_m=decay_distance,
            buffer_distance_m=buffer_distance,
            max_vdatum_extension_m=max_vdatum_extension,
            out_fn=out_fn,
            verbose=True,
        )

        if preview and grid_result is not None:
            api.plot_grid(grid_result, region)

        if grid_result is not None:
            click.secho(
                f"Successfully generated shift grid: {out_fn}", fg="green", bold=True
            )
        else:
            click.secho("Failed to generate shift grid.", fg="red")
            sys.exit(1)

    else:
        click.secho(
            "Error: You must provide either an INPUT_FILE or both --region and --increment.",
            fg="red",
        )
        sys.exit(1)


# =====================================================================
# GENERATE SHIFT GRID
# =====================================================================
@transformez_cli.command("grid", cls=FetchezMainCommand)
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
    "--decay-pixels", type=int, default=100, help="Pixels to decay tidal shifts inland."
)
@click.option(
    "--decay-distance",
    type=click.FloatRange(min=0.0),
    default=None,
    metavar="METERS",
    help=(
        "Decay tidal shifts inland over this physical distance in meters. "
        "When provided, overrides --decay-pixels."
    ),
)
@click.option(
    "--buffer-distance",
    type=click.FloatRange(min=0.0),
    default=None,
    metavar="METERS",
    help=(
        "Preserve the full coastal shift for this distance inland before decay begins."
    ),
)
@click.option(
    "--max-vdatum-extension",
    type=click.FloatRange(min=0.0),
    default=None,
    metavar="METERS",
    help=(
        "Maximum inland distance from the Dist2Coast shoreline where valid "
        "VDatum coverage may extend the effective water domain."
    ),
)
@click.option(
    "--no-inland-decay",
    "extrapolate_inland",
    is_flag=True,
    help=(
        "Extrapolate tidal shifts inland without attenuation. "
        "Use with caution; tidal transformations may be applied far inland."
    ),
)
@click.option(
    "--use-stations",
    is_flag=True,
    help="Force RBF interpolation using live tide stations instead of global satellite models.",
)
@click.option(
    "--preview", is_flag=True, help="Show matplotlib preview instead of saving."
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
    """Generate a standalone vertical shift grid for a specified region."""

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
@transformez_cli.command("raster", cls=FetchezMainCommand)
@click.argument("input_file", type=click.Path(exists=True))
@click.option("-I", "--input-datum", required=True, help="Source Datum (e.g., 'mllw').")
@click.option(
    "-O", "--output-datum", required=True, help="Target Datum (e.g., '5703:g2012b')."
)
@click.option(
    "--in-units",
    default="auto",
    type=click.Choice(["auto", "m", "ft", "us-ft"]),
    help="Z-units of the input DEM.",
)
@click.option(
    "--out-units",
    default="auto",
    type=click.Choice(["auto", "m", "ft", "us-ft"]),
    help="Desired Z-units for the output DEM.",
)
@click.option("--out", "-o", help="Output filename (default: auto-named).")
@click.option(
    "--decay-pixels", type=int, default=100, help="Pixels to decay tidal shifts inland."
)
@click.option(
    "--decay-distance",
    type=click.FloatRange(min=0.0),
    default=None,
    metavar="METERS",
    help=(
        "Decay tidal shifts inland over this physical distance in meters. "
        "When provided, overrides --decay-pixels."
    ),
)
@click.option(
    "--buffer-distance",
    type=click.FloatRange(min=0.0),
    default=None,
    metavar="METERS",
    help=(
        "Preserve the full coastal shift for this distance inland before decay begins."
    ),
)
@click.option(
    "--max-vdatum-extension",
    type=click.FloatRange(min=0.0),
    default=None,
    metavar="METERS",
    help=(
        "Maximum inland distance from the Dist2Coast shoreline where valid "
        "VDatum coverage may extend the effective water domain."
    ),
)
@click.option(
    "--no-inland-decay",
    "extrapolate_inland",
    is_flag=True,
    help=(
        "Extrapolate tidal shifts inland without attenuation. "
        "Use with caution; tidal transformations may be applied far inland."
    ),
)
@click.option(
    "--use-stations",
    is_flag=True,
    help="Force RBF interpolation using live tide stations instead of global satellite models.",
)
@click.option(
    "--save-shift",
    is_flag=True,
    help="Save the aligned vertical shift grid to disk alongside the output DEM.",
)
def transform_raster(
    input_file: str,
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
    """Apply a vertical datum shift to an existing DEM."""

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


# --- LIST DATUMS, ETC. ---
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

    click.secho("\n💡 Pro-Tip:", fg="yellow", bold=True, nl=False)
    click.echo(
        " Combine an EPSG and a specific Geoid using a colon (e.g., -O 5703:g2012b)\n"
    )


# --- HTDP CLI GROUP ---
@transformez_cli.group(
    cls=FetchezMainGroup, name="htdp", fetchez_commands=["install", "run"]
)
def htdp_group() -> None:
    """Manage and run NGS HTDP (Horizontal Time-Dependent Positioning)."""

    pass


@htdp_group.command("install", cls=FetchezMainCommand)
@click.option(
    "--version",
    default="3.5.0",
    help="HTDP version to install (e.g., 3.3.0, 3.5.0, 3.6.0)",
)
def install_htdp(version: str) -> None:
    """Downloads and compiles the HTDP executable from github."""

    from transformez.htdp import install_htdp_binary

    install_htdp_binary(version=version)


@htdp_group.command("run", cls=FetchezMainCommand)
@click.option("--control", help="input control file, if omitted, run interactively")
def run_htpd(control: Optional[Any]) -> None:
    """Run HTDP from transformez"""

    from transformez.htdp import HTDP

    HTDP().run_cmd(control)


# --- VDATUM CLI GROUP ---
@transformez_cli.group(
    cls=FetchezMainGroup, name="vdatum", fetchez_commands=["install"]
)
def vdatum_group() -> None:
    """Manage and run the NOAA VDatum Java engine."""

    pass


@vdatum_group.command("install")
def install_vdatum() -> None:
    """Downloads and extracts the local VDatum software."""

    from transformez.vdatum import install_vdatum_jar

    install_vdatum_jar()


@vdatum_group.command("run", cls=FetchezMainCommand)
@click.argument("input_file", type=click.Path(exists=True))
@click.argument("output_file", type=click.Path())
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
    """Process an XYZ text file through the local VDatum Java engine."""

    from transformez.vdatum import Vdatum

    Vdatum(
        ivert=f"{in_datum}:{in_unit}:height",
        overt=f"{out_datum}:{out_unit}:height",
        region=region,
    ).run_vdatum(input_file)


@vdatum_group.command("list", cls=FetchezMainCommand)
def vdatum_list() -> None:
    """List the supported vdatum grids"""

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
    help="Fetch ALL available geoids, tidal models, and coastlines for this region.",
)
def transform_prefetch(
    region: str,
    input_datum: Optional[str],
    output_datum: Optional[str],
    fetch_all: bool,
) -> None:
    """Pre-download transformation grids and reference data for offline field use.

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
            f"Successfully pre-cached all assets for {region}. Ready for offline use!",
            fg="green",
            bold=True,
        )
    else:
        click.secho("Prefetch encountered errors. Check logs for details.", fg="red")
        sys.exit(1)


if __name__ == "__main__":
    transformez_cli()
