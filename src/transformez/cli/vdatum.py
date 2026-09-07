#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.cli.vdatum
~~~~~~~~~~~~~~~

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import click
from pathlib import Path

from fetchez.utils import FetchezMainGroup, FetchezMainCommand
from transformez.engines.vdatum import install_vdatum_jar, Vdatum


# --- VDATUM CLI GROUP ---
@click.group(
    cls=FetchezMainGroup, name="vdatum", fetchez_commands=["install", "run", "list"]
)
def vdatum_group() -> None:
    """Manage the NOAA VDatum transformation engine."""

    pass


@vdatum_group.command("install")
def install_vdatum() -> None:
    """Download and install the NOAA VDatum software."""

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

    Vdatum(
        ivert=f"{in_datum}:{in_unit}:height",
        overt=f"{out_datum}:{out_unit}:height",
        region=region,
    ).run_vdatum(input_file)


@vdatum_group.command("list", cls=FetchezMainCommand)
def vdatum_list() -> None:
    """Show information reported by the installed VDatum engine."""

    vd = Vdatum().vdatum_help()
    click.echo(vd)
