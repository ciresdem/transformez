#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.cli.plan
~~~~~~~~~~~~~~~

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import sys
import click

from fetchez.utils import FetchezMainCommand

from transformez.reference.parser import parse_reference
from transformez.reference.resolver import resolve_reference
from transformez.reference.planner import (
    TransformationPlanner,
    GridOperation,
    FrameOperation,
)


@click.command("plan", cls=FetchezMainCommand)
@click.option(
    "-I", "--input-datum", required=True, help="Source Datum (e.g., 'mllw', '5703')."
)
@click.option(
    "-O",
    "--output-datum",
    required=True,
    help="Target Datum (e.g., '4979', '5703:g2012b').",
)
@click.option(
    "--epoch-in", default="2010.0", help="Source coordinate epoch (default: 2010.0)."
)
@click.option(
    "--epoch-out", default="2010.0", help="Target coordinate epoch (default: 2010.0)."
)
def plan(
    input_datum: str,
    output_datum: str,
    epoch_in: str,
    epoch_out: str,
) -> None:
    """Preview the geodetic transformation steps without executing them."""

    try:
        src_parsed = parse_reference(input_datum)
        dst_parsed = parse_reference(output_datum)

        src_resolved = resolve_reference(src_parsed, default_epoch=float(epoch_in))
        dst_resolved = resolve_reference(dst_parsed, default_epoch=float(epoch_out))

        plan = TransformationPlanner.build_plan(src_resolved, dst_resolved)

    except Exception as e:
        click.secho(f"Failed to build plan: {e}", fg="red")
        sys.exit(1)

    click.secho(
        f"\n🗺️  Transformation Plan: {input_datum} ➔ {output_datum}",
        fg="cyan",
        bold=True,
    )

    src_name = (
        plan.source.vertical.reference.name if plan.source.vertical else "Unknown"
    )
    dst_name = (
        plan.target.vertical.reference.name if plan.target.vertical else "Unknown"
    )

    click.echo(f"  Source: {src_name} (@ {plan.source.coordinate_epoch})")
    click.echo(f"  Target: {dst_name} (@ {plan.target.coordinate_epoch})\n")

    if plan.horizontal_transform:
        click.secho("  [Horizontal Operation]", fg="yellow")
        click.echo("  • Reprojecting horizontal coordinates.\n")

    if not plan.steps:
        click.secho(
            "  ✓ Identity Transformation (No vertical steps required).", fg="green"
        )
        return

    click.secho("  [Vertical Operations]", fg="yellow")
    for i, step in enumerate(plan.steps, start=1):
        if isinstance(step, GridOperation):
            # Parse Grid Operations
            direction_str = (
                "Extract from" if step.direction == "from_native" else "Step to"
            )
            engine_str = step.binding.engine.replace("_", " ").title()
            model_str = f" via {step.reference.model}" if step.reference.model else ""

            click.echo(
                f"  {i}. Grid Shift [{engine_str}]: "
                f"{direction_str} Native Hub ({step.native_frame.name}){model_str}"
            )

        elif isinstance(step, FrameOperation):
            # Parse HTDP/Frame Operations
            click.echo(
                f"  {i}. Frame Shift [HTDP]: "
                f"ID {step.source_id} (@ {step.epoch_in}) ➔ ID {step.target_id} (@ {step.epoch_out})"
            )

    click.echo()
