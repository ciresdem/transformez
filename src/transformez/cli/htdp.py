#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.cli.htdp
~~~~~~~~~~~~~~~

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import click
from typing import Optional, Any, Literal

from fetchez.utils import FetchezMainGroup, FetchezMainCommand

from transformez.htdp import DEFAULT_HTDP_VERSION


# --- HTDP CLI GROUP ---
@click.group(cls=FetchezMainGroup, name="htdp", fetchez_commands=["install", "run"])
def htdp_group() -> None:
    """Manage the NGS HTDP transformation engine."""

    pass


@htdp_group.command("install", cls=FetchezMainCommand)
@click.option(
    "--version",
    default=DEFAULT_HTDP_VERSION,
    show_default=True,
    help="HTDP version to install.",
)
@click.option(
    "--project",
    is_flag=True,
    help="Install into this project's transformez_cache instead of the user installation.",
)
def install_htdp(
    version: str,
    project: bool,
) -> None:
    """Download and install the NGS HTDP executable."""

    from transformez.htdp import install_htdp_binary, HTDPInstallError

    scope: Literal["project", "user"] = "project" if project else "user"

    try:
        path = install_htdp_binary(
            version=version,
            scope=scope,
        )
    except HTDPInstallError as exc:
        raise click.ClickException(str(exc)) from exc

    click.secho(
        f"HTDP {version} installed to {path}",
        fg="green",
    )


@htdp_group.command("run", cls=FetchezMainCommand)
@click.option("--control", help="input control file, if omitted, run interactively")
def run_htdp(control: Optional[Any]) -> None:
    """Run the installed NGS HTDP executable."""

    from transformez.htdp import HTDP

    HTDP().run_cmd(control)
