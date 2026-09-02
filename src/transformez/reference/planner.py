#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.reference.planner
~~~~~~~~~~~~~

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
from dataclasses import dataclass
from typing import List, Literal

from pyproj import Transformer, CRS

from .types import ResolvedReference, ResolvedVerticalReference
from .bindings import OperationBinding

logger = logging.getLogger(__name__)


class TransformationError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class GridOperation:
    reference: ResolvedVerticalReference
    native_frame: CRS
    binding: OperationBinding
    direction: Literal["to_native", "from_native"]


@dataclass(frozen=True, slots=True)
class FrameOperation:
    source_frame: CRS
    target_frame: CRS
    source_id: int
    target_id: int
    epoch_in: float | None
    epoch_out: float | None


PlanOperation = GridOperation | FrameOperation


@dataclass(frozen=True, slots=True)
class TransformationPlan:
    source: ResolvedReference
    target: ResolvedReference
    steps: tuple[PlanOperation, ...]
    horizontal_transform: Transformer | None


class TransformationPlanner:
    @classmethod
    def build_plan(
        cls, source: ResolvedReference, target: ResolvedReference
    ) -> TransformationPlan:

        steps: List[PlanOperation] = []

        horizontal_transform = None

        if source.horizontal and target.horizontal:
            if source.horizontal != target.horizontal:
                horizontal_transform = Transformer.from_crs(
                    source.horizontal,
                    target.horizontal,
                    always_xy=True,
                )

        src_vert = source.vertical
        dst_vert = target.vertical

        if src_vert and dst_vert:
            if (
                src_vert.binding is not None
                and src_vert.reference != dst_vert.reference
            ):
                steps.append(
                    GridOperation(
                        reference=src_vert,
                        native_frame=src_vert.native_frame,
                        binding=src_vert.binding,
                        direction="to_native",
                    )
                )

            if (
                src_vert.native_frame != dst_vert.native_frame
                or source.coordinate_epoch != target.coordinate_epoch
            ):
                if src_vert.frame_binding and dst_vert.frame_binding:
                    steps.append(
                        FrameOperation(
                            source_frame=src_vert.native_frame,
                            target_frame=dst_vert.native_frame,
                            source_id=src_vert.frame_binding.htdp_id,
                            target_id=dst_vert.frame_binding.htdp_id,
                            epoch_in=source.coordinate_epoch,
                            epoch_out=target.coordinate_epoch,
                        )
                    )
                else:
                    raise TransformationError(
                        "Frame operation required, but no frame bindings were validated."
                    )

            if (
                dst_vert.binding is not None
                and src_vert.reference != dst_vert.reference
            ):
                steps.append(
                    GridOperation(
                        reference=dst_vert,
                        native_frame=dst_vert.native_frame,
                        binding=dst_vert.binding,
                        direction="from_native",
                    )
                )

        return TransformationPlan(
            source=source,
            target=target,
            steps=tuple(steps),
            horizontal_transform=horizontal_transform,
        )
