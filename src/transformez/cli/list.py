#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.cli.list
~~~~~~~~~~~~~~~

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import click

from typing import Any

from fetchez.utils import FetchezMainGroup, FetchezMainCommand

from transformez.reference.parser import parse_reference
from transformez.reference.bindings import (
    CUSTOM_VERTICAL_REFERENCES,
    OPERATION_BINDINGS,
    HTDP_FRAME_BINDINGS,
)
from transformez.reference.types import VerticalKind


@click.group(
    cls=FetchezMainGroup,
    name="list",
    fetchez_commands=["references", "bindings", "frames", "geoids", "providers"],
)
def list_group() -> None:
    """List supported references and transformation resources."""

    pass


@list_group.command("references", cls=FetchezMainCommand)
def references() -> None:
    """List Transformez-specific vertical references."""

    for kind in VerticalKind:
        refs = [
            (ref_id, ref)
            for ref_id, ref in CUSTOM_VERTICAL_REFERENCES.items()
            if ref.kind == kind
        ]

        if not refs:
            continue

        click.secho(
            f"\n{kind.value.replace('_', ' ').title()}:",
            fg="cyan",
            bold=True,
        )

        for ref_id, ref in sorted(refs):
            click.echo(f"  {ref_id:<16} {ref.name}")


@list_group.command("bindings", cls=FetchezMainCommand)
def bindings() -> None:
    """List registered transformation bindings."""

    bindings = []
    for ref_id, binding in OPERATION_BINDINGS.items():
        bindings.append((ref_id, binding))

    header = (
        "  REFERENCE        ENGINE          PROVIDER       NATIVE FRAME   DEFAULT MODEL"
    )
    click.secho(f"\n {header}", fg="cyan", bold=True)
    click.echo("-" * len(header))
    for ref_id, binding in sorted(bindings):
        click.echo(
            f"  {ref_id:<16} {binding.engine:<16} {binding.provider:<16} {binding.native_frame:<16} {binding.default_model or '-'}"
        )


@list_group.command("frames", cls=FetchezMainCommand)
def frames() -> None:
    """List reference frames available to HTDP."""

    bindings = []
    for ref_id, binding in OPERATION_BINDINGS.items():
        ref_vert_obj = parse_reference(ref_id).vertical
        name = ref_vert_obj.name if ref_vert_obj else "Unknown"
        bindings.append((ref_id, name, binding))

    header = "  CRS         HTDP ID   NAME                        REFERENCE EPOCH"
    click.secho(f"\n {header}", fg="cyan", bold=True)
    click.echo("-" * len(header))
    for epsg_str, htdp_binding in HTDP_FRAME_BINDINGS.items():
        epsg_code = epsg_str.split(":")[1]
        click.echo(
            f"  {epsg_code:<12} {htdp_binding.htdp_id:<8} {htdp_binding.name:<30} {htdp_binding.reference_epoch}"
        )


@list_group.command("geoids", cls=FetchezMainCommand)
def geoids() -> None:
    """List geoid models used by registered bindings."""

    geoids: dict[Any, Any] = {}
    for ref_id, binding in OPERATION_BINDINGS.items():
        if ref_id.startswith("epsg:") and binding.engine == "proj":
            geoids.setdefault(
                binding.default_model,
                {"provider": set(), "notes": []},
            )
            providers[binding.provider]["engines"].add(binding.provider)
            providers[binding.provider]["references"].append(str(ref_id))

    header = "  MODEL           PROVIDER     DEFAULT FOR"
    click.secho(f"\n {header}", fg="cyan", bold=True)
    click.echo("-" * len(header))

    for key in geoids:
        click.echo(
            f"  {key:<16} {geoids[key]['provider']:<12} {','.join(geoids[key]['notes'])}"
        )


@list_group.command("providers", cls=FetchezMainCommand)
def providers() -> None:
    """List transformation data/model providers."""

    providers: dict[Any, Any] = {}
    for ref_id, binding in OPERATION_BINDINGS.items():
        providers.setdefault(
            binding.provider,
            {"engines": set(), "references": []},
        )
        providers[binding.provider]["engines"].add(binding.engine)
        providers[binding.provider]["references"].append(str(ref_id))

    header = "  PROVIDER           ENGINE TYPES     USED BY"
    click.secho(f"\n {header}", fg="cyan", bold=True)
    click.echo("-" * len(header))

    for key in providers:
        engines = list(set(providers[key].get("engine", [])))
        notes: list = providers[key]["references"]
        click.echo(f"  {key:<18} {','.join(engines):<16} {','.join(notes)}")
