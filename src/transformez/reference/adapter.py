#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.reference.adapter
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Temporary compatibility bridge between the typed reference system and the
legacy definitions-driven transformation engine.

The adapter can be removed once the transformation engine consumes
VerticalReference / OperationBinding directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Tuple

from pyproj import CRS

from transformez.definitions import Datums

from .bindings import OperationBinding, get_operation_binding
from .types import ParsedReference, VerticalReference
from .parser import parse_reference


class LegacyAdapterError(ValueError):
    """Raised when a typed reference cannot be represented by the legacy engine."""


@dataclass(frozen=True, slots=True)
class LegacyVerticalSpec:
    """Vertical reference expressed in the current transform.py vocabulary."""

    reference: VerticalReference

    # Legacy identifier used by VerticalTransform.
    epsg: int

    # Legacy transform.py routing value:
    # "surface", "global_tidal", "cdn", "htdp", ...
    ref_type: str

    # Optional geoid/model name expected by the old engine.
    geoid: str | None

    # Native ellipsoidal frame expected by the old hub-and-spoke logic.
    native_epsg: int

    # New execution metadata retained for provenance/debugging.
    binding: OperationBinding | None = None

    @property
    def provider_datum(self) -> str | None:
        if self.binding is None:
            return None
        return self.binding.provider_datum


@dataclass(frozen=True, slots=True)
class LegacyReferenceSpec:
    """Complete parsed reference translated for legacy consumers."""

    horizontal: CRS | None
    vertical: LegacyVerticalSpec | None
    coordinate_epoch: float | None = None


def _extract_geoid(srs_str: str) -> Tuple[str, Optional[str]]:
    """Extract geoid from legacy SRS string."""

    parts = str(srs_str).split("+geoid:")
    return parts[0], (parts[1] if len(parts) > 1 else None)


def _epsg_from_reference(reference: VerticalReference) -> int | None:
    """Return an EPSG CRS identifier when the reference represents one."""

    if reference.crs is not None:
        auth = reference.crs.to_authority()
        if auth and auth[0].upper() == "EPSG":
            return int(auth[1])

    prefix, sep, code = reference.id.partition(":")
    if sep and prefix.casefold() == "epsg" and code.isdecimal():
        return int(code)

    return None


def _epsg_from_frame_id(frame_id: str | None) -> int | None:
    """Convert an authority frame identifier such as EPSG:6319 to an integer."""

    if not frame_id:
        return None

    prefix, sep, code = frame_id.partition(":")
    if sep and prefix.casefold() == "epsg" and code.isdecimal():
        return int(code)

    raise LegacyAdapterError(
        f"Legacy engine requires an EPSG native frame; got {frame_id!r}."
    )


def _legacy_surface_id(provider_datum: str, region: str | None = None) -> int | None:
    """Find the legacy SURFACES identifier matching a provider datum."""

    matches: list[int] = []

    for legacy_id, definition in Datums.SURFACES.items():
        if str(definition.get("name", "")).casefold() != provider_datum.casefold():
            continue

        if region is not None:
            if str(definition.get("region", "")).casefold() != region.casefold():
                continue

        matches.append(legacy_id)

    if not matches:
        return None

    return matches[0]


def _legacy_from_binding(
    reference: VerticalReference,
    binding: OperationBinding,
) -> LegacyVerticalSpec:
    """Translate a namespaced/custom reference through its operation binding."""

    native_epsg = _epsg_from_frame_id(binding.native_frame)

    if native_epsg is None:
        raise LegacyAdapterError(
            f"Reference {reference.id!r} has no legacy-compatible native frame."
        )

    if binding.engine == "vdatum_grid":
        if not binding.provider_datum:
            raise LegacyAdapterError(
                f"VDatum reference {reference.id!r} has no provider datum."
            )

        epsg = _legacy_surface_id(
            binding.provider_datum,
            region="usa",
        )

        if epsg is None:
            raise LegacyAdapterError(
                f"No legacy SURFACES entry represents {reference.id!r} "
                f"({binding.provider_datum!r})."
            )

        return LegacyVerticalSpec(
            reference=reference,
            epsg=epsg,
            ref_type="surface",
            geoid=_legacy_model_name(binding.default_model),
            native_epsg=native_epsg,
            binding=binding,
        )

    if binding.engine == "global_model":
        if not binding.provider_datum:
            raise LegacyAdapterError(
                f"Global model reference {reference.id!r} has no provider datum."
            )

        epsg = _legacy_surface_id(
            binding.provider_datum,
            region="global",
        )

        if epsg is None:
            raise LegacyAdapterError(
                f"No legacy global SURFACES entry represents {reference.id!r} "
                f"({binding.provider_datum!r})."
            )

        return LegacyVerticalSpec(
            reference=reference,
            epsg=epsg,
            ref_type="global_tidal",
            geoid=None,
            native_epsg=native_epsg,
            binding=binding,
        )

    if binding.engine == "geoid_grid":
        epsg = _epsg_from_reference(reference)
        if epsg is None:
            raise LegacyAdapterError(
                f"Geoid-backed reference {reference.id!r} has no EPSG CRS."
            )

        return LegacyVerticalSpec(
            reference=reference,
            epsg=epsg,
            ref_type="cdn",
            geoid=_legacy_model_name(binding.default_model)
            or Datums.get_default_geoid(epsg),
            native_epsg=native_epsg,
            binding=binding,
        )

    if binding.engine == "htdp":
        epsg = _epsg_from_reference(reference)
        if epsg is None:
            raise LegacyAdapterError(
                f"HTDP reference {reference.id!r} has no EPSG CRS."
            )

        return LegacyVerticalSpec(
            reference=reference,
            epsg=epsg,
            ref_type="htdp",
            geoid=None,
            native_epsg=native_epsg,
            binding=binding,
        )

    if binding.engine == "proj":
        epsg = _epsg_from_reference(reference)
        if epsg is None:
            raise LegacyAdapterError(
                f"PROJ reference {reference.id!r} has no EPSG CRS."
            )

        ref_type = Datums.get_frame_type(epsg)

        if ref_type is None:
            raise LegacyAdapterError(
                f"EPSG:{epsg} is valid but unsupported by the legacy "
                "transformation engine."
            )

        return LegacyVerticalSpec(
            reference=reference,
            epsg=epsg,
            ref_type=ref_type,
            geoid=Datums.get_default_geoid(epsg),
            native_epsg=_legacy_native_frame(epsg, ref_type),
            binding=binding,
        )

    raise LegacyAdapterError(
        f"Unsupported operation engine {binding.engine!r} for {reference.id!r}."
    )


def _legacy_model_name(model_id: str | None) -> str | None:
    """Translate namespaced model identifiers into current legacy model names."""

    if model_id is None:
        return None

    prefix, sep, value = model_id.partition(":")

    if not sep:
        return model_id

    if prefix.casefold() in {"geoid", "model"}:
        return value

    return model_id


def _legacy_native_frame(epsg: int, ref_type: str) -> int:
    """Replicate the current VerticalTransform native-frame selection."""

    if ref_type in {"surface", "global_tidal"}:
        definition = Datums.SURFACES.get(epsg, {})
        return 6319 if definition.get("region") == "usa" else 4979

    if ref_type == "cdn":
        return int(Datums.CDN.get(epsg, {}).get("ellipsoid", 6319))

    if ref_type == "htdp":
        return epsg

    return 4979


def _legacy_from_epsg(reference: VerticalReference) -> LegacyVerticalSpec:
    """Translate an ordinary authority vertical CRS through legacy definitions."""

    epsg = _epsg_from_reference(reference)

    if epsg is None:
        raise LegacyAdapterError(
            f"Reference {reference.id!r} cannot be represented as a legacy EPSG."
        )

    ref_type = Datums.get_frame_type(epsg)

    if ref_type is None:
        raise LegacyAdapterError(
            f"{reference.id!r} is a valid reference but is not supported by "
            "the current legacy transformation engine."
        )

    return LegacyVerticalSpec(
        reference=reference,
        epsg=epsg,
        ref_type=ref_type,
        geoid=Datums.get_default_geoid(epsg),
        native_epsg=_legacy_native_frame(epsg, ref_type),
        binding=None,
    )


def adapt_vertical_reference(
    reference: VerticalReference,
) -> LegacyVerticalSpec:
    """Translate a typed vertical reference into legacy transform inputs."""

    binding = get_operation_binding(reference)

    if binding is not None:
        return _legacy_from_binding(reference, binding)

    return _legacy_from_epsg(reference)


def adapt_parsed_reference(
    parsed: ParsedReference,
) -> LegacyReferenceSpec:
    """Translate a ParsedReference without changing its horizontal component."""

    vertical = (
        adapt_vertical_reference(parsed.vertical)
        if parsed.vertical is not None
        else None
    )

    return LegacyReferenceSpec(
        horizontal=parsed.horizontal,
        vertical=vertical,
        coordinate_epoch=parsed.coordinate_epoch,
    )


def adapt_reference(value: Any) -> LegacyReferenceSpec:
    """Parse a reference input and adapt it for the legacy engine."""

    clean_val, geoid_val = _extract_geoid(value)
    if not geoid_val:
        return adapt_parsed_reference(parse_reference(value))
    else:
        legacy_ref = adapt_parsed_reference(parse_reference(clean_val))
        vertical = LegacyVerticalSpec(
            reference=legacy_ref.vertical.reference,
            epsg=legacy_ref.vertical.epsg,
            ref_type=legacy_ref.vertical.ref_type,
            native_epsg=legacy_ref.vertical.native_epsg,
            binding=legacy_ref.vertical.binding,
            geoid=geoid_val,
        )
        return LegacyReferenceSpec(
            horizontal=legacy_ref.horizontal,
            vertical=vertical,
            coordinate_epoch=legacy_ref.coordinate_epoch,
        )
