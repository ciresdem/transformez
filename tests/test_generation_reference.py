# tests/test_generation.py

import numpy as np
import pytest
from pyproj import CRS

from fetchez.spatial import Region

from transformez.grid.shift import build_shift_grid, ShiftGrid
from transformez.reference.executor import ExecutionResult


def _mock_reference_executor(monkeypatch, value=-0.25, trace=None):
    """Patch computational execution while preserving parse/resolve/plan behavior."""

    trace = trace or ["+ [Synthetic reference execution]"]
    created_contexts = []
    executed_plans = []

    class FakeExecutor:
        def __init__(self, context):
            self.context = context
            created_contexts.append(context)

        def execute(self, plan):
            executed_plans.append(plan)
            shift = np.full(
                (self.context.ny, self.context.nx),
                value,
                dtype=np.float32,
            )
            return ExecutionResult(
                shift=shift,
                plan=plan,
                trace=list(trace),
            )

    monkeypatch.setattr(
        "transformez.reference.executor.TransformationExecutor",
        FakeExecutor,
    )

    return created_contexts, executed_plans


def test_build_shift_grid_uses_reference_plan_and_returns_wgs84_grid(monkeypatch):
    contexts, plans = _mock_reference_executor(monkeypatch)

    grid = build_shift_grid(
        region=[-80.0, -79.0, 25.0, 26.0],
        increment="0.1",
        datum_in="EPSG:4326+3855",
        datum_out="EPSG:4326+5703",
    )

    assert isinstance(grid, ShiftGrid)
    assert grid.crs == CRS.from_epsg(4326)
    assert grid.array.shape == (10, 10)

    assert grid.source_reference.vertical is not None
    assert grid.target_reference.vertical is not None
    assert grid.source_reference.vertical.id == "epsg:3855"
    assert grid.target_reference.vertical.id == "epsg:5703"

    assert len(contexts) == 1
    assert len(plans) == 1

    plan = plans[0]
    assert plan.source.vertical is not None
    assert plan.target.vertical is not None
    assert plan.source.vertical.reference.id == "epsg:3855"
    assert plan.target.vertical.reference.id == "epsg:5703"

    context = contexts[0]
    assert context.nx == 10
    assert context.ny == 10
    assert context.region.xmin == pytest.approx(-80.0)
    assert context.region.xmax == pytest.approx(-79.0)
    assert context.region.ymin == pytest.approx(25.0)
    assert context.region.ymax == pytest.approx(26.0)


def test_build_shift_grid_preserves_effective_epochs_in_plan(monkeypatch):
    _, plans = _mock_reference_executor(monkeypatch)

    grid = build_shift_grid(
        region=[-80.0, -79.0, 25.0, 26.0],
        increment="0.1",
        datum_in={
            "horizontal": "EPSG:4326",
            "vertical": "EPSG:3855",
            "coordinate_epoch": 2017.5,
        },
        datum_out={
            "horizontal": "EPSG:4326",
            "vertical": "EPSG:5703",
            "coordinate_epoch": 2020.0,
        },
        epoch_in="2010.0",
        epoch_out="2010.0",
    )

    assert grid.epoch_in == "2017.5"
    assert grid.epoch_out == "2020.0"

    assert len(plans) == 1
    plan = plans[0]
    assert plan.source.coordinate_epoch == 2017.5
    assert plan.target.coordinate_epoch == 2020.0

    assert grid.provenance["TRANSFORMEZ_EPOCH_IN"] == "2017.5"
    assert grid.provenance["TRANSFORMEZ_EPOCH_OUT"] == "2020.0"


def test_build_shift_grid_preserves_execution_trace(monkeypatch):
    expected_trace = [
        "+ [GeoidGrid(g2008)]",
        "- [GeoidGrid(g2018)]",
    ]
    _mock_reference_executor(
        monkeypatch,
        value=-0.25,
        trace=expected_trace,
    )

    grid = build_shift_grid(
        region=[-80.0, -79.0, 25.0, 26.0],
        increment="0.1",
        datum_in="EPSG:4326+3855",
        datum_out="EPSG:4326+5703",
    )

    assert grid.trace == expected_trace
    assert grid.uncertainty is None


def test_build_shift_grid_forwards_execution_options_to_context(monkeypatch, tmp_path):
    contexts, _ = _mock_reference_executor(monkeypatch)

    grid = build_shift_grid(
        region=[-80.0, -79.0, 25.0, 26.0],
        increment="0.1",
        datum_in="EPSG:4326+3855",
        datum_out="EPSG:4326+5703",
        decay_pixels=123,
        decay_distance_m=5000.0,
        buffer_distance_m=250.0,
        max_vdatum_extension_m=1000.0,
        extrapolate_inland=True,
        cache_dir=tmp_path,
        use_stations=True,
        verbose=True,
    )

    assert isinstance(grid, ShiftGrid)
    assert len(contexts) == 1

    context = contexts[0]
    assert context.decay_pixels == 123
    assert context.decay_distance_m == 5000.0
    assert context.buffer_distance_m == 250.0
    assert context.max_vdatum_extension_m == 1000.0
    assert context.extrapolate_inland is True
    assert context.cache_dir == tmp_path
    assert context.use_stations is True
    assert context.verbose is True


def test_identical_generation_requests_have_same_key(monkeypatch):
    _mock_reference_executor(monkeypatch)

    kwargs = dict(
        region=[-80.0, -79.0, 25.0, 26.0],
        increment="0.1",
        datum_in="EPSG:4326+3855",
        datum_out="EPSG:4326+5703",
        epoch_in="2010.0",
        epoch_out="2020.0",
        decay_distance_m=5000.0,
        buffer_distance_m=250.0,
    )

    a = build_shift_grid(**kwargs)
    b = build_shift_grid(**kwargs)

    assert a.generation_key == b.generation_key


@pytest.mark.parametrize(
    "override",
    [
        {"increment": "0.05"},
        {"epoch_in": "2015.0"},
        {"epoch_out": "2025.0"},
        {"decay_pixels": 200},
        {"decay_distance_m": 10000.0},
        {"buffer_distance_m": 500.0},
        {"max_vdatum_extension_m": 1000.0},
        {"extrapolate_inland": True},
        {"use_stations": True},
    ],
)
def test_generation_key_changes_with_generation_options(
    monkeypatch,
    override,
):
    _mock_reference_executor(monkeypatch)

    base_kwargs = dict(
        region=[-80.0, -79.0, 25.0, 26.0],
        increment="0.1",
        datum_in="EPSG:4326+3855",
        datum_out="EPSG:4326+5703",
        epoch_in="2010.0",
        epoch_out="2020.0",
        decay_pixels=100,
        decay_distance_m=5000.0,
        buffer_distance_m=250.0,
        max_vdatum_extension_m=None,
        extrapolate_inland=False,
        use_stations=False,
    )

    base = build_shift_grid(**base_kwargs)

    changed_kwargs = {**base_kwargs, **override}
    changed = build_shift_grid(**changed_kwargs)

    assert base.generation_key != changed.generation_key


def test_generation_key_changes_with_region(monkeypatch):
    _mock_reference_executor(monkeypatch)

    a = build_shift_grid(
        region=[-80.0, -79.0, 25.0, 26.0],
        increment="0.1",
        datum_in="EPSG:4326+3855",
        datum_out="EPSG:4326+5703",
    )

    b = build_shift_grid(
        region=[-80.0, -78.9, 25.0, 26.0],
        increment="0.1",
        datum_in="EPSG:4326+3855",
        datum_out="EPSG:4326+5703",
    )

    assert a.generation_key != b.generation_key


def test_projected_region_is_normalized_to_wgs84_before_execution(monkeypatch):
    contexts, _ = _mock_reference_executor(monkeypatch)

    region = Region(
        400000.0,
        410000.0,
        4930000.0,
        4940000.0,
    )
    region.srs = 32610

    grid = build_shift_grid(
        region=region,
        increment="0.01",
        datum_in="EPSG:32610+3855",
        datum_out="EPSG:32610+5703",
    )

    assert grid.crs == CRS.from_epsg(4326)
    assert -180.0 <= grid.region.xmin <= 180.0
    assert -90.0 <= grid.region.ymin <= 90.0

    assert len(contexts) == 1
    context = contexts[0]
    assert context.region.xmin == pytest.approx(grid.region.xmin)
    assert context.region.xmax == pytest.approx(grid.region.xmax)
    assert context.region.ymin == pytest.approx(grid.region.ymin)
    assert context.region.ymax == pytest.approx(grid.region.ymax)
