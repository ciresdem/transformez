#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.cli.prefetch
~~~~~~~~~~~~~~~

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import sys
import click

from fetchez.utils import FetchezMainCommand

from transformez import api


# --- PREFETCH  ---
@click.command("prefetch", cls=FetchezMainCommand)
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
def prefetch(
    region: str,
    input_datum: str | None,
    output_datum: str | None,
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
