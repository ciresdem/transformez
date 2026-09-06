#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.cli.info
~~~~~~~~~~~~~~~

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import sys
import click

from pathlib import Path
from importlib.metadata import version, PackageNotFoundError

from fetchez.utils import FetchezMainGroup, FetchezMainCommand

from transformez.reference.parser import parse_reference, InvalidReferenceError
from transformez.reference.resolver import resolve_reference
from transformez.reference.bindings import (
    CUSTOM_VERTICAL_REFERENCES,
    OPERATION_BINDINGS,
    HTDP_FRAME_BINDINGS,
)


@click.group(
    cls=FetchezMainGroup,
    name="info",
    fetchez_commands=["reference", "binding", "frame", "system"],
)
def info_group() -> None:
    """Get information related to supported references and transformation resources."""

    pass


@info_group.command("reference", cls=FetchezMainCommand)
@click.argument("ref_id")
def reference(ref_id) -> None:
    """Inspect a vertical reference."""

    try:
        if Path(ref_id).exists():
            import rasterio
            from pyproj import CRS

            with rasterio.open(ref_id) as src:
                native_crs = src.crs

            native_pyproj_crs = (
                CRS.from_user_input(native_crs) if native_crs is not None else None
            )

            parsed_ref = (
                parse_reference(native_pyproj_crs)
                if native_pyproj_crs is not None
                else None
            )
        else:
            parsed_ref = parse_reference(ref_id)

        if parsed_ref is not None:
            parsed_vertical = parsed_ref.vertical

            click.secho("\n Reference:", fg="cyan", bold=True)
            click.echo("-" * 12)

            click.echo(f"  {'ID:':<18} {parsed_ref.source_text}")

            if parsed_vertical is not None:
                click.echo(f"  {'Name:':<18} {parsed_vertical.name}")
                click.echo(f"  {'Kind:':<18} {parsed_vertical.kind}")
                click.echo(
                    f"  {'Axis Direction:':<18} {parsed_vertical.axis_direction}"
                )
                click.echo(f"  {'Units:':<18} {parsed_vertical.unit_name}")

                resolved_ref = resolve_reference(parsed_ref)
                resolved_vertical = resolved_ref.vertical
                if resolved_vertical is not None:
                    resolved_binding = resolved_vertical.binding
                    if resolved_binding is not None:
                        click.secho("\n Execution:", fg="cyan", bold=True)
                        click.echo("-" * 12)

                        click.echo(f"  {'Engine:':<18} {resolved_binding.engine}")
                        click.echo(f"  {'Provider:':<18} {resolved_binding.provider}")
                        click.echo(
                            f"  {'Provider Datum:':<18} {resolved_binding.provider_datum}"
                        )
                        click.echo(
                            f"  {'Native Frame:':<18} {resolved_binding.native_frame}"
                        )
                        click.echo(
                            f"  {'Default Model:':<18} {resolved_binding.default_model}"
                        )
                        click.echo(
                            f"  {'Global Proxy:':<18} {resolved_binding.global_proxy}"
                        )

                        resolved_frame_binding = resolved_vertical.frame_binding
                        if resolved_frame_binding is not None:
                            click.secho("\n Frame:", fg="cyan", bold=True)
                            click.echo("-" * 12)

                            click.echo(f"  {'Name:':<18} {resolved_frame_binding.name}")
                            click.echo(
                                f"  {'HTDP ID:':<18} {resolved_frame_binding.htdp_id}"
                            )
                            click.echo(
                                f"  {'Reference Epoch:':<18} {resolved_frame_binding.reference_epoch}"
                            )
                        else:
                            click.echo(f"  No frame binding available for {ref_id}")
                    else:
                        click.echo(f"  No operation binding available for {ref_id}")
                else:
                    click.echo(f"  No vertical reference available for {ref_id}")
            else:
                click.echo(f"  No vertical reference available for {ref_id}")
        else:
            click.echo(f"  Could not parse {ref_id}")

    except InvalidReferenceError:
        click.echo(f"  {ref_id} is unsupported by transformez")


@info_group.command("binding", cls=FetchezMainCommand)
@click.argument("ref_id")
def binding(ref_id) -> None:
    """Inspect the operation binding for a vertical reference."""

    try:
        parsed_ref = parse_reference(ref_id)
        parsed_vertical = parsed_ref.vertical
        resolved_ref = resolve_reference(parsed_ref)
        resolved_vertical = resolved_ref.vertical

        if resolved_vertical is not None:
            resolved_binding = resolved_vertical.binding
            if resolved_binding is not None and parsed_vertical is not None:
                click.secho("\n Operation Binding:", fg="cyan", bold=True)
                click.echo("-" * 12)

                click.echo(f"  {'ID:':<18} {parsed_vertical.id}")
                click.echo(f"  {'Engine:':<18} {resolved_binding.engine}")
                click.echo(f"  {'Provider:':<18} {resolved_binding.provider}")
                click.echo(
                    f"  {'Provider Datum:':<18} {resolved_binding.provider_datum}"
                )
                click.echo(f"  {'Native Frame:':<18} {resolved_binding.native_frame}")
                click.echo(f"  {'Default Model:':<18} {resolved_binding.default_model}")
                click.echo(f"  {'Global Proxy:':<18} {resolved_binding.global_proxy}")
            else:
                click.echo(f"  No vertical binding available for {ref_id}")
        else:
            click.echo(f"  No vertical reference available for {ref_id}")

    except InvalidReferenceError:
        click.echo(f"  {ref_id} is unsupported by transformez")


@info_group.command("frame", cls=FetchezMainCommand)
@click.argument("ref_id")
def frame(ref_id) -> None:
    """Inspect the vertical reference frame for a vertical references."""

    try:
        parsed_ref = parse_reference(ref_id)
        parsed_vertical = parsed_ref.vertical
        parsed_horizontal = parsed_ref.horizontal
        resolved_ref = resolve_reference(parsed_ref)
        resolved_vertical = resolved_ref.vertical

        click.secho("\n Frame:", fg="cyan", bold=True)
        click.echo("-" * 12)

        click.echo(f"  {'ID:':<18} {parsed_ref.source_text}")
        if parsed_ref is not None:
            if parsed_vertical is not None and resolved_vertical is not None:
                resolved_frame_binding = resolved_vertical.frame_binding
                if resolved_frame_binding is not None:
                    click.echo(f"  {'Name:':<18} {resolved_frame_binding.name}")
                    click.echo(f"  {'HTDP ID:':<18} {resolved_frame_binding.htdp_id}")
                    click.echo(
                        f"  {'Reference Epoch:':<18} {resolved_frame_binding.reference_epoch}"
                    )
                    click.echo(f"  {'HTDP Support:':<18} Yes")
                else:
                    click.echo(f"  No vertical frame binding available for {ref_id}")
            elif parsed_horizontal is not None:
                click.echo(f"  {'Name:':<18} {parsed_horizontal.name}")
                click.echo(f"  {'HTDP Support:':<18} No")
        else:
            raise InvalidReferenceError

    except InvalidReferenceError:
        click.echo(f"  {ref_id} is unsupported by transformez")


@info_group.command("system", cls=FetchezMainCommand)
def system() -> None:
    """Get information about Transformez"""

    __version__ = version("transformez")

    try:
        pyproj_version = version("pyproj")
    except PackageNotFoundError:
        pyproj_version = "Not installed."

    try:
        rasterio_version = version("rasterio")
    except PackageNotFoundError:
        rasterio_version = "Not installed."

    try:
        fetchez_version = version("fetchez")
    except PackageNotFoundError:
        fetchez_version = "Not installed."

    try:
        from transformez.htdp import resolve_htdp_path

        htdp_bin: Path | str | None = resolve_htdp_path()
        if htdp_bin:
            htdp_version = str(htdp_bin).split("_")[-1]
        else:
            raise ValueError
    except (ImportError, ValueError):
        htdp_version = "Not installed."
        htdp_bin = ""

    try:
        from transformez.vdatum import Vdatum

        vd = Vdatum()
        locations = vd.vdatum_locate_jar()

        if not locations:
            raise ValueError

        vdatum_jar = locations[0]
        vdatum_version = vd.vdatum_get_version()
        if vdatum_jar is None or vdatum_version is None:
            raise ValueError
    except (ImportError, ValueError):
        vdatum_version = "Not installed."
        vdatum_jar = ""

    click.echo(f"\n  Transformez: {__version__}")

    click.secho("\n Dependencies:", fg="cyan", bold=True)
    click.echo(f" {'-' * 13}")
    click.echo(f"  {'Python:':<14} {sys.version}")
    click.echo(f"  {'PROJ:':<14} {pyproj_version}")
    click.echo(f"  {'Rasterio:':<14} {rasterio_version}")
    click.echo(f"  {'Fetchez:':<14} {fetchez_version}")

    click.secho("\n External Engines:", fg="cyan", bold=True)
    click.echo(f" {'-' * 17}")
    click.echo(f"  {'HTDP:':<14} {htdp_version}")
    click.echo(f"                 {str(htdp_bin)}")
    click.echo(f"  {'VDatum:':<14} {vdatum_version}")
    click.echo(f"                 {str(vdatum_jar)}")

    click.secho("\n Cache:", fg="cyan", bold=True)
    click.echo(f" {'-' * 6}")
    cache_dir = Path.cwd() / "transformez_cache"
    click.echo(f"  {'Path:':<14} {cache_dir}")
    click.echo(f"  {'Exists:':<14} {cache_dir.exists()}")
    if cache_dir.exists():
        click.echo(f"  {'Readable:':<14} {os.access(cache_dir, os.R_OK)}")
        click.echo(f"  {'Writable:':<14} {os.access(cache_dir, os.W_OK)}")

    click.secho("\n Reference Registry:", fg="cyan", bold=True)
    click.echo(f" {'-' * 19}")
    click.echo(f"  {'References:':<14} {len(CUSTOM_VERTICAL_REFERENCES.items())}")
    click.echo(f"  {'Bindings:':<14} {len(OPERATION_BINDINGS.items())}")
    click.echo(f"  {'HTDP Frames:':<14} {len(HTDP_FRAME_BINDINGS.items())}")
