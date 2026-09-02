# import pytest
from transformez.reference.parser import parse_reference
from transformez.reference.resolver import resolve_reference
from transformez.reference.planner import (
    TransformationPlanner,
    GridOperation,
    FrameOperation,
)


def make_plan(source, target, **kwargs):
    src = resolve_reference(parse_reference(source), **kwargs)
    dst = resolve_reference(parse_reference(target), **kwargs)

    return TransformationPlanner.build_plan(src, dst)


def test_plan_mllw_to_native_ellipsoid():
    plan = make_plan("vdatum:mllw", "EPSG:6319")

    assert len(plan.steps) == 1

    step = plan.steps[0]

    assert isinstance(step, GridOperation)
    assert step.direction == "to_native"
    assert step.reference.reference.id == "vdatum:mllw"
    assert step.native_frame == parse_reference("EPSG:6319").vertical.crs


def test_plan_native_ellipsoid_to_mllw():
    plan = make_plan("EPSG:6319", "vdatum:mllw")

    assert len(plan.steps) == 1

    step = plan.steps[0]

    assert isinstance(step, GridOperation)
    assert step.direction == "from_native"
    assert step.reference.reference.id == "vdatum:mllw"


def test_plan_ellipsoid_to_ellipsoid():
    plan = make_plan("EPSG:6319", "EPSG:7663")

    assert len(plan.steps) == 1

    step = plan.steps[0]

    assert isinstance(step, FrameOperation)
    assert step.source_frame.srs == "EPSG:6319"
    assert step.target_frame.srs == "EPSG:7663"

    assert step.source_id == 1
    assert step.target_id == 8


def test_plan_mllw_to_global_lat():
    plan = make_plan("vdatum:mllw", "global:lat")

    assert len(plan.steps) == 3

    first, second, third = plan.steps

    assert isinstance(first, GridOperation)
    assert first.direction == "to_native"
    assert first.reference.reference.id == "vdatum:mllw"
    assert first.native_frame.srs == "EPSG:6319"

    assert isinstance(second, FrameOperation)
    assert second.source_frame.srs == "EPSG:6319"
    assert second.target_frame.srs == "EPSG:4979"

    assert isinstance(third, GridOperation)
    assert third.direction == "from_native"
    assert third.reference.reference.id == "global:lat"
    assert third.native_frame.srs == "EPSG:4979"


def test_plan_same_frame_different_epoch():
    src = resolve_reference(
        parse_reference("EPSG:6319"),
        default_epoch=2010.0,
    )
    dst = resolve_reference(
        parse_reference("EPSG:6319"),
        default_epoch=2020.0,
    )

    plan = TransformationPlanner.build_plan(src, dst)

    assert len(plan.steps) == 1

    step = plan.steps[0]

    assert isinstance(step, FrameOperation)
    assert step.source_frame == step.target_frame
    assert step.epoch_in == 2010.0
    assert step.epoch_out == 2020.0


def test_plan_identity():
    plan = make_plan("EPSG:6319", "EPSG:6319")

    assert plan.steps == ()
    assert plan.horizontal_transform is None


def test_plan_same_surface_identity():
    plan = make_plan("vdatum:mllw", "vdatum:mllw")

    assert plan.steps == ()


# @pytest.mark.parametrize(
#     ("source", "target", "expected"),
#     [
#         (
#             "vdatum:mllw",
#             "EPSG:6319",
#             [("grid", "to_native")],
#         ),
#         (
#             "EPSG:6319",
#             "vdatum:mllw",
#             [("grid", "from_native")],
#         ),
#         (
#             "EPSG:6319",
#             "EPSG:7662",
#             [("frame", None)],
#         ),
#     ],
# )
# def test_plan_shapes(source, target, expected):
#     plan = make_plan(source, target)

#     actual = []

#     for step in plan.steps:
#         if isinstance(step, GridOperation):
#             actual.append(("grid", step.direction))
#         elif isinstance(step, FrameOperation):
#             actual.append(("frame", None))

#     assert actual == expected
