#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.reference.types
~~~~~~~~~~~~~

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

from dataclasses import dataclass
from typing import Literal, Any

from pyproj import CRS

from .types import VerticalReference, VerticalKind, AxisDirection


@dataclass(frozen=True, slots=True)
class OperationBinding:
    """Instructions for how to route and execute a specific reference."""

    reference_id: str
    engine: Literal["vdatum_grid", "geoid_grid", "global_model", "htdp", "proj"]
    provider: str
    provider_datum: str | None = None
    native_frame: str | None = None
    default_model: str | None = None
    global_proxy: str | None = None


@dataclass(frozen=True, slots=True)
class HtdpFrameBinding:
    """Tectonic metadata required to perform HTDP hub-to-hub shifts."""

    htdp_id: int
    name: str
    reference_epoch: float


# =========================================================================
# THE METADATA (What the datum is)
# =========================================================================
CUSTOM_VERTICAL_REFERENCES = {
    "vdatum:msl": VerticalReference(
        id="vdatum:msl",
        name="NOAA VDatum Mean Sea Level",
        kind=VerticalKind.TIDAL_HEIGHT,
        axis_direction=AxisDirection.UP,
        unit_name="metre",
        unit_to_metre=1.0,
    ),
    "vdatum:mllw": VerticalReference(
        id="vdatum:mllw",
        name="NOAA VDatum Mean Lower Low Water",
        kind=VerticalKind.TIDAL_HEIGHT,
        axis_direction=AxisDirection.UP,
        unit_name="metre",
        unit_to_metre=1.0,
    ),
    "vdatum:mlw": VerticalReference(
        id="vdatum:mlw",
        name="NOAA VDatum Mean Low Water",
        kind=VerticalKind.TIDAL_HEIGHT,
        axis_direction=AxisDirection.UP,
        unit_name="metre",
        unit_to_metre=1.0,
    ),
    "vdatum:mhw": VerticalReference(
        id="vdatum:mhw",
        name="NOAA VDatum Mean High Water",
        kind=VerticalKind.TIDAL_HEIGHT,
        axis_direction=AxisDirection.UP,
        unit_name="metre",
        unit_to_metre=1.0,
    ),
    "vdatum:mhhw": VerticalReference(
        id="vdatum:mhhw",
        name="NOAA VDatum Mean Higher High Water",
        kind=VerticalKind.TIDAL_HEIGHT,
        axis_direction=AxisDirection.UP,
        unit_name="metre",
        unit_to_metre=1.0,
    ),
    "global:mss": VerticalReference(
        id="global:mss",
        name="Mean Sea Surface (Global Proxy)",
        kind=VerticalKind.MODEL_SURFACE,
        axis_direction=AxisDirection.UP,
        unit_name="metre",
        unit_to_metre=1.0,
    ),
    "global:lat": VerticalReference(
        id="global:lat",
        name="Lowest Astronomical Tide (Global Proxy)",
        kind=VerticalKind.MODEL_SURFACE,
        axis_direction=AxisDirection.UP,
        unit_name="metre",
        unit_to_metre=1.0,
    ),
    "global:hat": VerticalReference(
        id="global:hat",
        name="Highest Astronomical Tide (Global Proxy)",
        kind=VerticalKind.MODEL_SURFACE,
        axis_direction=AxisDirection.UP,
        unit_name="metre",
        unit_to_metre=1.0,
    ),
    "epsg:5703": VerticalReference(
        id="epsg:5703",
        name="NAVD88",
        kind=VerticalKind.GRAVITY_RELATED_HEIGHT,
        axis_direction=AxisDirection.UP,
        unit_name="metre",
        unit_to_metre=1.0,
    ),
    "epsg:3855": VerticalReference(
        id="epsg:3855",
        name="EGM2008 height",
        kind=VerticalKind.GRAVITY_RELATED_HEIGHT,
        axis_direction=AxisDirection.UP,
        unit_name="metre",
        unit_to_metre=1.0,
    ),
}


# =========================================================================
# THE EXECUTION INSTRUCTIONS (How to shift it)
# =========================================================================
OPERATION_BINDINGS = {
    "vdatum:msl": OperationBinding(
        reference_id="vdatum:msl",
        engine="vdatum_grid",
        provider="vdatum",
        provider_datum="msl",
        native_frame="EPSG:6319",  # NAD83(2011) Hub
        default_model="geoid:g2018",
    ),
    "vdatum:mllw": OperationBinding(
        reference_id="vdatum:mllw",
        engine="vdatum_grid",
        provider="vdatum",
        provider_datum="mllw",
        native_frame="EPSG:6319",  # NAD83(2011) Hub
        default_model="g2018",
    ),
    "vdatum:mlw": OperationBinding(
        reference_id="vdatum:mlw",
        engine="vdatum_grid",
        provider="vdatum",
        provider_datum="mlw",
        native_frame="EPSG:6319",  # NAD83(2011) Hub
        default_model="geoid:g2018",
    ),
    "vdatum:mhhw": OperationBinding(
        reference_id="vdatum:mhhw",
        engine="vdatum_grid",
        provider="vdatum",
        provider_datum="mhhw",
        native_frame="EPSG:6319",  # NAD83(2011) Hub
        default_model="geoid:g2018",
    ),
    "vdatum:mhw": OperationBinding(
        reference_id="vdatum:mhw",
        engine="vdatum_grid",
        provider="vdatum",
        provider_datum="mhw",
        native_frame="EPSG:6319",  # NAD83(2011) Hub
        default_model="geoid:g2018",
    ),
    "global:mss": OperationBinding(
        reference_id="global:mss",
        engine="global_model",
        provider="dtu25",
        provider_datum="mss",
        native_frame="EPSG:4979",  # WGS84 Hub
        default_model=None,
    ),
    "global:lat": OperationBinding(
        reference_id="global:lat",
        engine="global_model",
        provider="fes2014",
        provider_datum="lat",
        native_frame="EPSG:4979",  # WGS84 Hub
        default_model=None,
    ),
    "global:hat": OperationBinding(
        reference_id="global:hat",
        engine="global_model",
        provider="fes2014",
        provider_datum="hat",
        native_frame="EPSG:4979",  # WGS84 Hub
        default_model=None,
    ),
    "epsg:5703": OperationBinding(
        reference_id="epsg:5703",
        engine="proj",
        provider="cdn",
        provider_datum=None,
        native_frame="EPSG:6319",  # NAD83 Hub
        default_model="g2018",
    ),
    "epsg:3855": OperationBinding(
        reference_id="epsg:3755",
        engine="proj",
        provider="cdn",
        provider_datum=None,
        native_frame="EPSG:4979",  # WGS84 Hub
        default_model="egm2008",
    ),
}


# =========================================================================
# THE TECTONIC BRIDGES (Hub-to-Hub translation)
# =========================================================================
HTDP_FRAME_BINDINGS = {
    "EPSG:6319": HtdpFrameBinding(
        htdp_id=1, name="NAD_83(2011/CORS96/2007)", reference_epoch=1997.0
    ),
    "EPSG:7663": HtdpFrameBinding(
        htdp_id=8, name="WGS_84(G1674)", reference_epoch=2000.0
    ),
    "EPSG:4979": HtdpFrameBinding(
        htdp_id=10, name="WGS_84(G2139)", reference_epoch=2020.0
    ),
    "EPSG:6321": HtdpFrameBinding(
        htdp_id=2,
        name="NAD_83(PA11/PACP00)",
        reference_epoch=1997.0,
    ),
}


# =========================================================================
# THE RESOLVER (Used by parser.py)
# =========================================================================
class CustomRegistry:
    """Resolves custom namespaced references into typed VerticalReferences."""

    @classmethod
    def resolve(cls, text: str) -> VerticalReference:
        key = text.casefold()
        if key not in CUSTOM_VERTICAL_REFERENCES:
            # We raise a standard ValueError here;
            # parser.py catches it and wraps it in InvalidReferenceError.
            raise ValueError(f"Unknown custom reference namespace: '{text}'")
        return CUSTOM_VERTICAL_REFERENCES[key]


CUSTOM_REGISTRY = CustomRegistry()


def get_operation_binding(
    reference: VerticalReference,
) -> OperationBinding | None:
    return OPERATION_BINDINGS.get(reference.id.casefold())


def get_htdp_frame_binding(
    reference_id: Any,
) -> HtdpFrameBinding | None:
    resolved_reference_id = CRS.from_user_input(reference_id).srs
    return HTDP_FRAME_BINDINGS.get(resolved_reference_id.upper())
