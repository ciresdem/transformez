#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.cli.build
~~~~~~~~~~~~~~~

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import sys
import click

from fetchez.utils import FetchezMainCommand

from transformez import api


# =====================================================================
# GENERATE SHIFT GRID
# =====================================================================
@click.command("build", cls=FetchezMainCommand)
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
def build(
    region: str,
    increment: str,
    input_datum: str,
    output_datum: str,
    out: str | None,
    decay_pixels: int,
    decay_distance: float | None,
    buffer_distance: float | None,
    max_vdatum_extension: float | None,
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
