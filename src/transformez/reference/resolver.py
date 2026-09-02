#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.reference.resolver
~~~~~~~~~~~~~

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

from pyproj import CRS

from .types import (
    ParsedReference,
    ResolvedReference,
    ResolvedVerticalReference,
    VerticalKind,
)
from .bindings import get_operation_binding, get_htdp_frame_binding
from .parser import UnsupportedReferenceError


def resolve_reference(
    parsed: ParsedReference,
    inherited_horizontal: CRS | None = None,
    default_epoch: float | None = None,
    model: str | None = None,
) -> ResolvedReference:
    horizontal = parsed.horizontal or inherited_horizontal
    epoch = (
        parsed.coordinate_epoch
        if parsed.coordinate_epoch is not None
        else default_epoch
    )

    if parsed.vertical is None:
        vertical = None
    else:
        binding = get_operation_binding(parsed.vertical)

        if parsed.vertical.kind is VerticalKind.ELLIPSOIDAL_HEIGHT:
            if parsed.vertical.crs is None:
                raise UnsupportedReferenceError(
                    f"Ellipsoidal reference {parsed.vertical.id!r} "
                    "does not provide a CRS."
                )

            native_frame = parsed.vertical.crs
            effective_model = None

        elif binding is not None:
            native_frame = CRS.from_user_input(binding.native_frame)
            effective_model = model or binding.default_model

        else:
            raise UnsupportedReferenceError(
                f"No operation binding is available for {parsed.vertical.id!r}."
            )

        frame_binding = get_htdp_frame_binding(native_frame)
        vertical = ResolvedVerticalReference(
            reference=parsed.vertical,
            binding=binding,
            native_frame=native_frame,
            frame_binding=frame_binding,
            model=effective_model,
        )

    return ResolvedReference(
        horizontal=horizontal,
        vertical=vertical,
        coordinate_epoch=epoch,
    )
