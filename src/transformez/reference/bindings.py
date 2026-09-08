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
    "vdatum:xgeoid19b": VerticalReference(
        id="vdatum:xgeoid19b",
        name="NGS X-GEOID 19b",
        kind=VerticalKind.GRAVITY_RELATED_HEIGHT,
        axis_direction=AxisDirection.UP,
        unit_name="metre",
        unit_to_metre=1.0,
    ),
    "vdatum:xgeoid20b": VerticalReference(
        id="vdatum:xgeoid20b",
        name="NGS X-GEOID 20b",
        kind=VerticalKind.GRAVITY_RELATED_HEIGHT,
        axis_direction=AxisDirection.UP,
        unit_name="metre",
        unit_to_metre=1.0,
    ),
    # GLOBAL
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
    # Temporary! These are retained for backward compatibility, but will be removed.
    # These are all ambiguous tidal epsg codes. There is no valid way to
    # operate on them without more context, which can be given from downstream
    # applications, which should be the ones deciding what it is supposed to mean
    # as far as it's vertical surface goes.
    "epsg:5866": VerticalReference(
        id="epsg:5866",
        name="Mean Lower Low Water (Generic)",
        kind=VerticalKind.TIDAL_HEIGHT,
        axis_direction=AxisDirection.UP,
        unit_name="metre",
        unit_to_metre=1.0,
    ),
    "epsg:5869": VerticalReference(
        id="epsg:5869",
        name="Mean Higher High Water (Generic)",
        kind=VerticalKind.TIDAL_HEIGHT,
        axis_direction=AxisDirection.UP,
        unit_name="metre",
        unit_to_metre=1.0,
    ),
    "epsg:5714": VerticalReference(
        id="epsg:5714",
        name="Mean Lower Low Water (Generic)",
        kind=VerticalKind.TIDAL_HEIGHT,
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
        native_frame="EPSG:6319",
        default_model="geoid:g2018",
        global_proxy="global:mss",
    ),
    "vdatum:mllw": OperationBinding(
        reference_id="vdatum:mllw",
        engine="vdatum_grid",
        provider="vdatum",
        provider_datum="mllw",
        native_frame="EPSG:6319",
        default_model="g2018",
        global_proxy="global:lat",
    ),
    "vdatum:mlw": OperationBinding(
        reference_id="vdatum:mlw",
        engine="vdatum_grid",
        provider="vdatum",
        provider_datum="mlw",
        native_frame="EPSG:6319",
        default_model="geoid:g2018",
        global_proxy="global:lat",
    ),
    "vdatum:mhhw": OperationBinding(
        reference_id="vdatum:mhhw",
        engine="vdatum_grid",
        provider="vdatum",
        provider_datum="mhhw",
        native_frame="EPSG:6319",
        default_model="geoid:g2018",
        global_proxy="global:hat",
    ),
    "vdatum:mhw": OperationBinding(
        reference_id="vdatum:mhw",
        engine="vdatum_grid",
        provider="vdatum",
        provider_datum="mhw",
        native_frame="EPSG:6319",
        default_model="geoid:g2018",
        global_proxy="global:hat",
    ),
    "vdatum:xgeoid19b": OperationBinding(
        reference_id="vdatum:xgeoid19b",
        engine="vdatum_grid",
        provider="vdatum",
        provider_datum="xgeoid19b",
        native_frame="EPSG:7912",
        default_model=None,
    ),
    "vdatum:xgeoid20b": OperationBinding(
        reference_id="vdatum:xgeoid20b",
        engine="vdatum_grid",
        provider="vdatum",
        provider_datum="xgeoid20b",
        native_frame="EPSG:7912",
        default_model=None,
    ),
    "global:mss": OperationBinding(
        reference_id="global:mss",
        engine="global_model",
        provider="dtu25",
        provider_datum="mss",
        native_frame="EPSG:4979",
        default_model=None,
    ),
    "global:lat": OperationBinding(
        reference_id="global:lat",
        engine="global_model",
        provider="fes2014",
        provider_datum="lat",
        native_frame="EPSG:4979",
        default_model=None,
    ),
    "global:hat": OperationBinding(
        reference_id="global:hat",
        engine="global_model",
        provider="fes2014",
        provider_datum="hat",
        native_frame="EPSG:4979",
        default_model=None,
    ),
    "epsg:5703": OperationBinding(
        reference_id="epsg:5703",
        engine="proj",
        provider="cdn",
        provider_datum=None,
        native_frame="EPSG:6319",
        default_model="g2018",
    ),
    "epsg:8228": OperationBinding(
        reference_id="epsg:8228",
        engine="proj",
        provider="cdn",
        provider_datum=None,
        native_frame="EPSG:6319",
        default_model="g2012b",
    ),
    "epsg:3855": OperationBinding(
        reference_id="epsg:3855",
        engine="proj",
        provider="cdn",
        provider_datum=None,
        native_frame="EPSG:4979",
        default_model="egm2008",
    ),
    "epsg:5773": OperationBinding(
        reference_id="epsg:5773",
        engine="proj",
        provider="cdn",
        provider_datum=None,
        native_frame="EPSG:4979",
        default_model="egm96",
    ),
    "epsg:6641": OperationBinding(
        reference_id="epsg:6641",
        engine="proj",
        provider="cdn",
        provider_datum=None,
        native_frame="EPSG:6319",
        default_model="g2018",
    ),
    "epsg:6642": OperationBinding(
        reference_id="epsg:6642",
        engine="proj",
        provider="cdn",
        provider_datum=None,
        native_frame="epsg:6310",
        default_model="g2018",
    ),
    "epsg:6643": OperationBinding(
        reference_id="epsg:6643",
        engine="proj",
        provider="cdn",
        provider_datum=None,
        native_frame="epsg:6321",
        default_model="g2012bs0",
    ),
    "epsg:6647": OperationBinding(
        reference_id="epsg:6647",
        engine="proj",
        provider="cdn",
        provider_datum=None,
        native_frame="epsg:6321",
        default_model="CGG2013",
    ),
    # Temporary! These are retained for backward compatibility, but will be removed.
    # These are all ambiguous tidal epsg codes. There is no valid way to
    # operate on them without more context, which can be given from downstream
    # applications, which should be the ones deciding what it is supposed to mean
    # as far as it's vertical surface goes.
    "epsg:5866": OperationBinding(
        reference_id="epsg:5866",
        engine="vdatum_grid",
        provider="vdatum",
        provider_datum="mllw",
        native_frame="EPSG:6319",
        default_model="g2018",
        global_proxy="global:lat",
    ),
    "epsg:5869": OperationBinding(
        reference_id="epsg:5869",
        engine="vdatum_grid",
        provider="vdatum",
        provider_datum="mhhm",
        native_frame="EPSG:6319",
        default_model="g2018",
        global_proxy="global:hat",
    ),
    "epsg:5714": OperationBinding(
        reference_id="epsg:5714",
        engine="vdatum_grid",
        provider="vdatum",
        provider_datum="msl",
        native_frame="EPSG:6319",
        default_model="g2018",
        global_proxy="global:mss",
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
        reference_epoch=2010.0,
    ),
    "EPSG:7911": HtdpFrameBinding(
        htdp_id=22,
        name="IGS08/IGb08",
        reference_epoch=2000.0,
    ),
    "EPSG:7912": HtdpFrameBinding(
        htdp_id=23,
        name="IGS14/IGb14/WGS84/ITRF2014 Ellipsoid",
        reference_epoch=2000.0,
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
