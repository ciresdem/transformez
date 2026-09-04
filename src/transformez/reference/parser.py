#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.reference.parser
~~~~~~~~~~~~~

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

from __future__ import annotations

import logging
from pyproj import CRS
from pyproj.exceptions import CRSError
from typing import Mapping, Any

from .types import (
    VerticalKind,
    AxisDirection,
    VerticalReference,
    ParsedReference,
    ReferenceInput,
)
from .bindings import CUSTOM_REGISTRY

logger = logging.getLogger(__name__)

CUSTOM_REFERENCE_PREFIXES = {"tidal", "vdatum", "global", "model", "local"}
LEGACY_ALIASES = {
    "msl": "vdatum:msl",
    "mlw": "vdatum:mlw",
    "mllw": "vdatum:mllw",
    "mhw": "vdatum:mhw",
    "mhhw": "vdatum:mhhw",
    "mss": "global:mss",
    "lat": "global:lat",
    "hat": "global:hat",
    "9001": "global:lat",
    "9002": "global:hat",
    "9003": "global:mss",
}


class ReferenceInputError(ValueError):
    """Base error for invalid or unsupported reference input."""


class InvalidReferenceError(ReferenceError):
    pass


class UnsupportedReferenceError(ReferenceError):
    pass


def warn_legacy_alias(old: str, new: str):
    logger.warning(f"Legacy alias '{old}' is deprecated. Please use '{new}'.")


def vertical_only(vert_ref: VerticalReference, text: str) -> ParsedReference:
    """Helper to cleanly construct a vertical-only ParsedReference."""
    return ParsedReference(
        horizontal=None,
        vertical=vert_ref,
        horizontal_specified=False,
        vertical_specified=True,
        source_text=text,
    )


def infer_vertical_kind(crs: CRS) -> VerticalKind:
    axis = crs.axis_info[-1]
    name = crs.name.casefold()
    axis_name = axis.name.casefold()

    if crs.is_vertical:
        if axis.direction.casefold() == "down":
            return VerticalKind.DEPTH

        if "dynamic height" in name:
            return VerticalKind.DYNAMIC_HEIGHT

        if "depth" in name or "depth" in axis_name:
            return VerticalKind.DEPTH

        return VerticalKind.GRAVITY_RELATED_HEIGHT

    if crs.is_geographic and len(crs.axis_info) == 3:
        return VerticalKind.ELLIPSOIDAL_HEIGHT

    return VerticalKind.LOCAL_HEIGHT


def vertical_reference_from_crs(
    crs: CRS,
    kind: VerticalKind | None = None,
) -> VerticalReference:
    axis = crs.axis_info[-1]

    direction = (
        AxisDirection.DOWN if axis.direction.casefold() == "down" else AxisDirection.UP
    )

    auth = crs.to_authority()
    ref_id = f"{auth[0]}:{auth[1]}".lower() if auth else "proj:unknown"

    if kind is None:
        kind = infer_vertical_kind(crs)

    return VerticalReference(
        id=ref_id,
        name=crs.name,
        kind=kind,
        axis_direction=direction,
        unit_name=axis.unit_name,
        unit_to_metre=axis.unit_conversion_factor,
        crs=crs,
    )


def decompose_standard_crs(crs: CRS) -> ParsedReference:
    """Decomposes a standard PROJ CRS into its Horizontal and Vertical components."""

    if crs.is_compound:
        horizontal, vertical = None, None
        for component in crs.sub_crs_list:
            if component.is_vertical:
                if vertical:
                    raise UnsupportedReferenceError("Multiple verticals unsupported.")
                vertical = vertical_reference_from_crs(component)
            elif component.is_geographic or component.is_projected:
                if horizontal:
                    raise UnsupportedReferenceError("Multiple horizontals unsupported.")
                horizontal = component

        return ParsedReference(
            horizontal=horizontal,
            vertical=vertical,
            horizontal_specified=horizontal is not None,
            vertical_specified=vertical is not None,
            source_text=crs.to_string(),
        )

    if len(crs.axis_info) == 3 and crs.is_geographic:
        return ParsedReference(
            horizontal=crs.to_2d(),
            vertical=vertical_reference_from_crs(crs),
            horizontal_specified=True,
            vertical_specified=True,
            source_text=crs.to_string(),
        )

    if crs.is_vertical:
        vert_ref = vertical_reference_from_crs(crs)
        return vertical_only(vert_ref, crs.to_string())

    return ParsedReference(
        horizontal=crs,
        vertical=None,
        horizontal_specified=True,
        vertical_specified=False,
        source_text=crs.to_string(),
    )


_COMPONENT_KEYS = {
    "horizontal",
    "vertical",
    "coordinate_epoch",
}


def parse_reference_mapping(mapping: Mapping[str, Any]) -> ParsedReference:
    """Parses a dictionary containing explicit horizontal and vertical keys."""

    horz_val = mapping.get("horizontal")
    vert_val = mapping.get("vertical")
    epoch_val = mapping.get("coordinate_epoch", mapping.get("epoch"))
    # geoid_val = mapping.get("geoid")

    horz_ref = parse_reference(horz_val) if horz_val else None
    vert_ref = parse_reference(vert_val) if vert_val else None

    # Strict Dimensional Guardrails
    if horz_ref and horz_ref.vertical_specified:
        raise UnsupportedReferenceError(
            f"Explicit horizontal component ({horz_val}) cannot contain a vertical definition."
        )
    if vert_ref and vert_ref.horizontal_specified:
        raise UnsupportedReferenceError(
            f"Explicit vertical component ({vert_val}) cannot contain a horizontal definition."
        )

    # Stitch and Return
    return ParsedReference(
        horizontal=horz_ref.horizontal if horz_ref else None,
        vertical=vert_ref.vertical if vert_ref else None,
        horizontal_specified=horz_ref is not None,
        vertical_specified=vert_ref is not None,
        coordinate_epoch=epoch_val,
        source_text=str(mapping),
    )


def parse_reference(value: ReferenceInput) -> ParsedReference:
    if isinstance(value, ParsedReference):
        return value

    if isinstance(value, bool):
        raise InvalidReferenceError("Boolean values are not valid CRS identifiers.")

    if isinstance(value, Mapping):
        return parse_reference_mapping(value)

    if isinstance(value, CRS):
        return decompose_standard_crs(value)

    if isinstance(value, int):
        try:
            return decompose_standard_crs(CRS.from_epsg(value))
        except CRSError as exc:
            raise InvalidReferenceError(f"Unknown EPSG CRS: {value}") from exc

    text = str(value).strip()
    if not text:
        raise InvalidReferenceError("Reference cannot be empty.")

    # Legacy bare aliases
    alias = LEGACY_ALIASES.get(text.casefold())
    if alias is not None:
        warn_legacy_alias(text, alias)
        return parse_reference(alias)

    # Transformez custom namespaces
    prefix = text.partition(":")[0].casefold()
    if prefix in CUSTOM_REFERENCE_PREFIXES:
        try:
            vert_ref = CUSTOM_REGISTRY.resolve(text)
        except ValueError as exc:
            raise InvalidReferenceError(f"Unknown custom reference: {text!r}") from exc
        return vertical_only(vert_ref, text)

    # Numeric EPSG shorthand
    if text.isdecimal():
        text = f"EPSG:{text}"

    # Let PROJ have first chance at all normal CRS strings/WKT
    try:
        crs = CRS.from_user_input(text)
    except CRSError:
        crs = None

    if crs is not None:
        return decompose_standard_crs(crs)

    # Transformez compound shorthand: horizontal+vertical
    if "+" in text:
        horizontal, vertical = text.rsplit("+", 1)
        return parse_reference(
            {
                "horizontal": horizontal,
                "vertical": vertical,
            }
        )

    raise InvalidReferenceError(f"Unsupported coordinate reference: {value!r}")
