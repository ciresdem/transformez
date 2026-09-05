#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.cli
~~~~~~~~~~~~~~~

The command-line interface for Transformez.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import click

from fetchez.cli import setup_logging
from fetchez.utils import FetchezMainGroup

from .build import build
from .shift import transform_raster
from .list import list_group

# from .info import info
from .plan import plan
from .prefetch import prefetch
from .htdp import htdp_group
from .vdatum import vdatum_group


TRANSFORMEZ_COMMANDS = {
    "Execution": ["build", "shift", "prefetch"],
    "Discovery": ["list", "info", "plan"],
    "External": ["htdp", "vdatum"],
}


class TransformezMainGroup(FetchezMainGroup):
    """Transformez top-level command group."""

    def get_command(self, ctx, cmd_name):
        if cmd_name == "grid":
            click.secho(
                "DEPRECATION WARNING: 'transformez grid' is deprecated; "
                "use 'transformez build'.",
                fg="yellow",
                err=True,
            )
            cmd_name = "build"

        elif cmd_name == "raster":
            click.secho(
                "DEPRECATION WARNING: 'transformez raster' is deprecated; "
                "use 'transformez shift'.",
                fg="yellow",
                err=True,
            )
            cmd_name = "shift"

        return super().get_command(ctx, cmd_name)


@click.group(
    cls=TransformezMainGroup,
    fetchez_commands=TRANSFORMEZ_COMMANDS,
)
@click.version_option(package_name="transformez")
@click.option("--verbose", is_flag=True, help="Enable verbose debug logging.")
@click.option("--quiet", is_flag=True, help="Suppress non-error output.")
def transformez_cli(verbose: bool, quiet: bool) -> None:
    """Build vertical datum shift grids and transform elevation data."""

    setup_logging(name="transformez", quiet=quiet, verbose=verbose)


transformez_cli.add_command(build)
transformez_cli.add_command(transform_raster, name="shift")
transformez_cli.add_command(list_group, name="list")
# transformez_cli.add_command(info)
transformez_cli.add_command(plan)
transformez_cli.add_command(prefetch)
transformez_cli.add_command(htdp_group, name="htdp")
transformez_cli.add_command(vdatum_group, name="vdatum")
