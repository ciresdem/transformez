#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.reference.executor
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Execute a resolved TransformationPlan.

The planner decides which operations are required and in what order;
the executor performs those operations and accumulates their vertical shifts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from fetchez.spatial import Region

from .fetcher import GridFetcher
from .planner import (
    FrameOperation,
    GridOperation,
    PlanOperation,
    TransformationPlan,
)
from ..htdp import HTDP

logger = logging.getLogger(__name__)


class ExecutionError(RuntimeError):
    """Base error raised when a planned transformation cannot be executed."""


class UnsupportedOperationError(ExecutionError):
    """Raised when the executor cannot execute a planned operation."""


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    """Runtime information required to execute a transformation plan."""

    region: Region
    nx: int
    ny: int
    cache_dir: Path

    decay_pixels: int = 100
    decay_distance_m: float | None = None
    buffer_distance_m: float = 0.0
    max_vdatum_extension_m: float | None = None
    extrapolate_inland: bool = False
    use_stations: bool = False

    verbose: bool = False


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """Result produced by executing a TransformationPlan."""

    shift: np.ndarray
    plan: TransformationPlan

    @property
    def shape(self) -> tuple[int, ...]:
        return self.shift.shape


class TransformationExecutor:
    """Execute transformation operations produced by TransformationPlanner."""

    def __init__(
        self,
        context: ExecutionContext,
        fetcher: GridFetcher | None = None,
        htdp: HTDP | None = None,
    ):
        self.context = context

        self.fetcher = fetcher or GridFetcher(
            region=context.region,
            nx=context.nx,
            ny=context.ny,
            cache_dir=context.cache_dir,
            decay_pixels=context.decay_pixels,
            decay_distance_m=context.decay_distance_m,
            buffer_distance_m=context.buffer_distance_m,
            max_vdatum_extension_m=context.max_vdatum_extension_m,
            extrapolate_inland=context.extrapolate_inland,
            use_stations=context.use_stations,
            verbose=context.verbose,
        )

        self.htdp = htdp or HTDP(verbose=context.verbose)

    def execute(self, plan: TransformationPlan) -> ExecutionResult:
        """Execute all vertical operations in a transformation plan."""

        shift = np.zeros(
            (self.context.ny, self.context.nx),
            dtype=np.float32,
        )

        for step in plan.steps:
            component = self.execute_step(step)

            if component.shape != shift.shape:
                raise ExecutionError(
                    "Operation returned an unexpected grid shape: "
                    f"{component.shape} != {shift.shape}"
                )

            shift += component.astype(np.float32, copy=False)

        return ExecutionResult(
            shift=shift,
            plan=plan,
        )

    def execute_step(self, operation: PlanOperation) -> np.ndarray:
        """Execute a single planned operation."""

        if isinstance(operation, GridOperation):
            return self._execute_grid_operation(operation)

        if isinstance(operation, FrameOperation):
            return self._execute_frame_operation(operation)

        raise UnsupportedOperationError(
            f"Unsupported plan operation: {type(operation).__name__}"
        )

    def _execute_grid_operation(
        self,
        operation: GridOperation,
    ) -> np.ndarray:
        """Execute a vertical reference <-> native-frame operation."""

        engine = operation.binding.engine

        if engine == "vdatum_grid":
            shift = self._execute_vdatum_grid(operation)

        elif engine == "geoid_grid":
            shift = self._execute_geoid_grid(operation)

        elif engine == "global_model":
            shift = self._execute_global_model(operation)

        elif engine == "proj":
            shift = self._execute_proj_grid(operation)

        else:
            raise UnsupportedOperationError(
                f"Grid engine {engine!r} is not supported by the executor."
            )

        return self._apply_direction(shift, operation.direction)

    def _execute_vdatum_grid(
        self,
        operation: GridOperation,
    ) -> np.ndarray:
        """Generate the native-frame shift for a VDatum reference."""

        datum_name = operation.binding.provider_datum

        if datum_name is None:
            raise ExecutionError(
                f"VDatum binding {operation.binding.reference_id!r} "
                "does not define provider_datum."
            )

        shift, _source = self.fetcher.fetch_vdatum_chain(
            datum_name,
            operation.reference.model,
        )

        if shift is None:
            raise ExecutionError(
                f"Unable to build VDatum shift for "
                f"{operation.reference.reference.id!r}."
            )

        return shift

    def _execute_global_model(
        self,
        operation: GridOperation,
    ) -> np.ndarray:
        """Generate a global-model <-> ellipsoid shift."""

        datum_name = operation.binding.provider_datum

        if datum_name is None:
            raise ExecutionError(
                f"Global-model binding {operation.binding.reference_id!r} "
                "does not define provider_datum."
            )

        model = operation.binding.provider

        shift, _source = self.fetcher.fetch_global_chain(
            datum_name,
            model=model,
        )

        return shift

    def _execute_geoid_grid(
        self,
        operation: GridOperation,
    ) -> np.ndarray:
        """Generate a geoid-backed reference <-> ellipsoid shift."""

        model = operation.reference.model or operation.binding.default_model

        if model is None:
            raise ExecutionError(
                f"Reference {operation.reference.reference.id!r} "
                "does not define a geoid model."
            )

        shift, _source = self.fetcher.fetch_geoid(model)

        return shift

    def _execute_proj_grid(
        self,
        operation: GridOperation,
    ) -> np.ndarray:
        """Temporary compatibility path for PROJ/CDN-backed vertical grids.

        This currently treats the resolved model as the required geoid grid.
        This method will likely become more specific once the legacy CDN logic
        is fully migrated out of VerticalTransform.
        """

        model = operation.reference.model or operation.binding.default_model

        if model is None:
            raise ExecutionError(
                f"PROJ-backed reference {operation.reference.reference.id!r} "
                "does not define an executable model."
            )

        shift, _source = self.fetcher.fetch_geoid(model)

        return shift

    def _execute_frame_operation(
        self,
        operation: FrameOperation,
    ) -> np.ndarray:
        """Execute an HTDP frame and/or epoch transformation."""

        if operation.epoch_in is None or operation.epoch_out is None:
            raise ExecutionError(
                "HTDP FrameOperation requires concrete input and output epochs."
            )

        return self.htdp.run_grid(
            region=self.context.region,
            nx=self.context.nx,
            ny=self.context.ny,
            frame_id_in=operation.source_id,
            frame_id_out=operation.target_id,
            epoch_in=str(operation.epoch_in),
            epoch_out=str(operation.epoch_out),
        )

    @staticmethod
    def _apply_direction(
        shift: np.ndarray,
        direction: str,
    ) -> np.ndarray:
        """Apply traversal direction to a native-reference shift."""

        if direction == "to_native":
            return shift

        if direction == "from_native":
            return -shift

        raise UnsupportedOperationError(
            f"Unknown grid-operation direction: {direction!r}"
        )
