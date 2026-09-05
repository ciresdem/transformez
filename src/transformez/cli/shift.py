#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.cli.shift
~~~~~~~~~~~~~~~

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import sys
import click
from pathlib import Path

from fetchez.utils import FetchezMainCommand

from transformez import api


# =====================================================================
# TRANSFORM EXISTING RASTER (DEM)
# =====================================================================
@click.command("shift", cls=FetchezMainCommand)
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "-I", "--input-datum", required=False, help="Source datum (e.g., 'mllw')."
)
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
    out: str | None,
    decay_pixels: int,
    decay_distance: float | None,
    buffer_distance: float | None,
    max_vdatum_extension: float | None,
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
