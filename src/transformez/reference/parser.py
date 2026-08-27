#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.reference.parser
~~~~~~~~~~~~~

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
from pyproj import CRS
from typing import Union, Dict

from .types import ParsedReference

logger = logging.getLogger(__name__)

CUSTOM_REFERENCE_PREFIXES = {"tidal", "vdatum", "global", "model", "local"}
LEGACY_ALIASES = {"mllw": "vdatum:mllw", "lat": "global:lat"}


class InvalidReferenceError(Exception):
    pass


class UnsupportedReferenceError(Exception):
    pass


def warn_legacy_alias(old: str, new: str):
    logger.warning(f"Legacy alias '{old}' is deprecated. Please use '{new}'.")


def decompose_standard_crs(crs: CRS) -> ParsedReference:
    """Decomposes a standard PROJ CRS into its Horizontal and Vertical components."""
    if crs.is_compound:
        horizontal, vertical = None, None
        for component in crs.sub_crs_list:
            if component.is_vertical:
                if vertical:
                    raise UnsupportedReferenceError("Multiple verticals unsupported.")
                # TODO: Map component to a VerticalReference
                vertical = component
            elif component.is_geographic or component.is_projected:
                if horizontal:
                    raise UnsupportedReferenceError("Multiple horizontals unsupported.")
                horizontal = component

        return ParsedReference(
            horizontal=horizontal,
            vertical=None,  # Will be resolved via bindings
            horizontal_specified=horizontal is not None,
            vertical_specified=vertical is not None,
            source_text=crs.to_string(),
        )

    # Add explicit 3D Geographic / Vertical-Only checks here
    return ParsedReference(
        horizontal=crs,
        vertical=None,
        horizontal_specified=True,
        vertical_specified=False,
        source_text=crs.to_string(),
    )


def parse_reference(
    value: Union[str, int, CRS, Dict, ParsedReference],
) -> ParsedReference:
    """The polymorphic entry point for all coordinate reference strings."""
    if isinstance(value, ParsedReference):
        return value
    if isinstance(value, CRS):
        return decompose_standard_crs(value)
    if isinstance(value, int):
        return decompose_standard_crs(CRS.from_epsg(value))

    text = str(value).strip()
    if not text:
        raise InvalidReferenceError("Reference cannot be empty.")

    legacy_id = LEGACY_ALIASES.get(text.casefold())
    if legacy_id:
        warn_legacy_alias(text, legacy_id)
        text = legacy_id

    prefix = text.partition(":")[0].casefold()
    if prefix in CUSTOM_REFERENCE_PREFIXES:
        # We will resolve this directly against bindings.py
        return ParsedReference(
            horizontal=None,
            vertical=None,
            horizontal_specified=False,
            vertical_specified=True,
            source_text=text,
        )

    if text.isdecimal():
        text = f"EPSG:{text}"

    try:
        crs = CRS.from_user_input(text)
    except Exception as exc:
        raise InvalidReferenceError(
            f"Unsupported coordinate reference: {value!r}"
        ) from exc

    return decompose_standard_crs(crs)
