#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.reference.types
~~~~~~~~~~~~~

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from pyproj import CRS


if TYPE_CHECKING:
    from .bindings import HtdpFrameBinding, OperationBinding


class VerticalKind(StrEnum):
    ELLIPSOIDAL_HEIGHT = "ellipsoidal_height"
    GRAVITY_RELATED_HEIGHT = "gravity_related_height"
    TIDAL_HEIGHT = "tidal_height"
    DEPTH = "depth"
    DYNAMIC_HEIGHT = "dynamic_height"
    MODEL_SURFACE = "model_surface"
    LOCAL_HEIGHT = "local_height"


class AxisDirection(StrEnum):
    UP = "up"
    DOWN = "down"


@dataclass(frozen=True, slots=True)
class VerticalReference:
    """A vertical coordinate reference."""

    id: str
    name: str
    kind: VerticalKind
    axis_direction: AxisDirection
    unit_name: str
    unit_to_metre: float
    crs: CRS | None = None

    @property
    def is_authority_crs(self) -> bool:
        return self.crs is not None


@dataclass(frozen=True, slots=True)
class ParsedReference:
    """A reference as supplied, before missing components are resolved."""

    horizontal: CRS | None
    vertical: VerticalReference | None
    horizontal_specified: bool
    vertical_specified: bool
    coordinate_epoch: float | None = None
    source_text: str | None = None


@dataclass(frozen=True, slots=True)
class ResolvedVerticalReference:
    reference: VerticalReference
    binding: OperationBinding | None
    native_frame: CRS
    frame_binding: HtdpFrameBinding | None
    model: str | None = None


@dataclass(frozen=True, slots=True)
class ResolvedReference:
    """A fully resolved coordinate reference endpoint."""

    horizontal: CRS | None
    vertical: ResolvedVerticalReference | None
    coordinate_epoch: float | None

    @property
    def vertical_reference(self) -> VerticalReference | None:
        return self.vertical.reference if self.vertical else None

    @property
    def native_vertical_frame(self) -> CRS | None:
        return self.vertical.native_frame if self.vertical else None
