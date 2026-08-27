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
from typing import Union, Dict, Mapping, Any

from .types import VerticalKind, AxisDirection, VerticalReference, ParsedReference
from .bindings import CUSTOM_REGISTRY

logger = logging.getLogger(__name__)

CUSTOM_REFERENCE_PREFIXES = {"tidal", "vdatum", "global", "model", "local"}
LEGACY_ALIASES = {"mllw": "vdatum:mllw", "lat": "global:lat"}


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


def vertical_reference_from_crs(crs: CRS) -> VerticalReference:
    """Translates a pure PROJ Vertical CRS into our internal VerticalReference."""

    # Extract the vertical axis (usually the first and only axis in a vertical CRS)
    axis = crs.axis_info[0]

    direction = (
        AxisDirection.DOWN if axis.direction.lower() == "down" else AxisDirection.UP
    )

    # Try to grab the EPSG code, otherwise fallback to unknown
    auth = crs.to_authority()
    ref_id = f"{auth[0]}:{auth[1]}".lower() if auth else "proj:unknown"

    return VerticalReference(
        id=ref_id,
        name=crs.name,
        kind=VerticalKind.GRAVITY_RELATED_HEIGHT,  # A safe default for standard PROJ datums
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
    epoch_val = mapping.get("epoch")

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


def parse_reference(
    value: Union[str, int, CRS, Dict, ParsedReference, VerticalReference],
) -> ParsedReference:
    """The entry point for all coordinate reference strings."""
    if isinstance(value, ParsedReference):
        return value

    if isinstance(value, bool):
        raise InvalidReferenceError("Boolean values are not valid CRS identifiers.")

    if isinstance(value, Mapping):
        return parse_reference_mapping(value)

    if isinstance(value, CRS):
        return decompose_standard_crs(value)  # , source_text=value.to_string())

    if isinstance(value, int):
        try:
            crs = CRS.from_epsg(value)
        except CRSError as exc:
            raise InvalidReferenceError(f"Unknown EPSG CRS: {value}") from exc
        return decompose_standard_crs(crs)  # , source_text=f"EPSG:{value}")

    text = str(value).strip()
    if not text:
        raise InvalidReferenceError("Reference cannot be empty.")

    legacy_id = LEGACY_ALIASES.get(text.casefold())
    if legacy_id:
        warn_legacy_alias(text, legacy_id)
        text = legacy_id

    # if "+" in text:
    #     horz_str, vert_str = text.split("+", 1)

    #     # Recursively parse both halves
    #     horz_ref = parse_reference(horz_str.strip())
    #     vert_ref = parse_reference(vert_str.strip())

    #     # Ensure they don't contain conflicting dimensions
    #     if horz_ref.vertical_specified:
    #         raise UnsupportedReferenceError(
    #             f"Left side of '+' ({horz_str}) already contains a vertical component."
    #         )
    #     if vert_ref.horizontal_specified:
    #         raise UnsupportedReferenceError(
    #             f"Right side of '+' ({vert_str}) contains an unexpected horizontal component."
    #         )

    #     return ParsedReference(
    #         horizontal=horz_ref.horizontal,
    #         vertical=vert_ref.vertical,
    #         horizontal_specified=True,
    #         vertical_specified=True,
    #         source_text=text,
    #     )

    prefix = text.partition(":")[0].casefold()
    if prefix in CUSTOM_REFERENCE_PREFIXES:
        try:
            vert_ref = CUSTOM_REGISTRY.resolve(text)
        except ValueError:
            raise InvalidReferenceError("Invalid custom reference")
        return vertical_only(vert_ref, text)

    if text.isdecimal():
        text = f"EPSG:{text}"

    try:
        crs = CRS.from_user_input(text)
    except Exception as exc:
        raise InvalidReferenceError(
            f"Unsupported coordinate reference: {value!r}"
        ) from exc

    return decompose_standard_crs(crs)
