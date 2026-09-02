import numpy as np
from pathlib import Path
from transformez.reference.executor import TransformationExecutor, ExecutionContext
from fetchez.spatial import Region

# import pytest
from transformez.reference.parser import parse_reference
from transformez.reference.resolver import resolve_reference
from transformez.reference.planner import TransformationPlanner


def make_plan(source, target, **kwargs):
    src = resolve_reference(parse_reference(source), **kwargs)
    dst = resolve_reference(parse_reference(target), **kwargs)

    return TransformationPlanner.build_plan(src, dst)


def test_executor_applies_steps_in_order():
    region = Region(-120, -119, 30, 31)
    tmp_path = Path.cwd()

    src = resolve_reference(
        parse_reference("vdatum:mllw"),
        default_epoch=2010.0,
    )
    dst = resolve_reference(
        parse_reference("global:lat"),
        default_epoch=2020.0,
    )

    plan = TransformationPlanner.build_plan(src, dst)

    class FakeFetcher:
        def fetch_vdatum_chain(self, datum_name, geoid_name):
            return np.full((2, 2), 1.0), "vdatum"

        def fetch_global_chain(self, datum_name, model):
            return np.full((2, 2), 3.0), "global"

    class FakeHTDP:
        def run_grid(self, **kwargs):
            return np.full((2, 2), 2.0)

    context = ExecutionContext(
        region=region,
        nx=2,
        ny=2,
        cache_dir=tmp_path,
    )

    executor = TransformationExecutor(
        context,
        fetcher=FakeFetcher(),
        htdp=FakeHTDP(),
    )

    result = executor.execute(plan)
    expected = np.full((2, 2), 1.0 + 2.0 - 3.0)

    np.testing.assert_allclose(
        result.shift,
        expected,
    )
