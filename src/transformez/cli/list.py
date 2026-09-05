#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.cli.list
~~~~~~~~~~~~~~~

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import click

from fetchez.utils import FetchezMainGroup, FetchezMainCommand

from transformez.reference.parser import parse_reference


@click.group(cls=FetchezMainGroup, name="list", fetchez_commands=["references"])
def list_group() -> None:
    """Manage the NGS HTDP transformation engine."""

    pass


# --- LIST DATUMS, ETC. ---
@list_group.command("references", cls=FetchezMainCommand)
def list_references() -> None:
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
            # ref_vert_obj = CUSTOM_VERTICAL_REFERENCES.get(ref_id)
            ref_vert_obj = parse_reference(ref_id).vertical
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
