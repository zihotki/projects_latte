"""Tests for geometry-independent native layout resolution."""

import math

import pytest
from cabineteer.cabinet import CabinetConfig
from cabineteer.layout import (
    Bounds3D,
    Fill,
    Frame,
    LayoutLeaf,
    Row,
    Stack,
    layout_from_dict,
    layout_to_dict,
    resolve_layout,
)
from cabineteer.project import (
    CabinetProject,
    ProjectCabinet,
    build_project,
    project_from_dict,
    project_to_dict,
)


def test_synthetic_stack_resolves_positions_and_frame_rails():
    frame = Frame("frame", 720, 380, 50, 18, "18 mm plywood")
    upper = Row(
        "upper_row",
        (
            LayoutLeaf("upper.left", 360, 420, 450),
            LayoutLeaf("upper.right", 360, 420, 600),
        ),
        span_mm=720,
        depth_alignment="back",
    )
    stack = Stack(
        "assembly",
        (LayoutLeaf("lower", 720, 550, 720), frame, upper),
        alignment="left",
        depth_alignment="back",
    )

    result = resolve_layout(stack)
    placements = {placement.name: placement for placement in result.placements}
    assert placements["lower"].origin_mm == (0, 0, 0)
    assert placements["frame"].origin_mm == (0, 170, 720)
    assert placements["upper.left"].origin_mm == (0, 130, 770)
    assert placements["upper.right"].origin_mm == (360, 130, 770)
    assert result.carcass_bounds_mm == Bounds3D(0, 0, 0, 720, 550, 1370)

    rails = {rail.name: rail for rail in frame.rails()}
    assert rails["front"].origin_mm == (0, 0, 0)
    assert (rails["front"].width_mm, rails["front"].depth_mm) == (720, 18)
    assert rails["back"].origin_mm == (0, 362, 0)
    assert rails["left"].origin_mm == (0, 18, 0)
    assert (rails["left"].width_mm, rails["left"].depth_mm) == (18, 344)
    assert rails["right"].origin_mm == (702, 18, 0)


def test_row_fixed_and_fill_widths_use_parent_span_and_named_alignment():
    row = Row(
        "row",
        (
            LayoutLeaf("fixed_left", 100, 20, 10),
            LayoutLeaf("fill", Fill(), 20, 10),
            LayoutLeaf("fixed_right", 100, 20, 10),
        ),
        gap_mm=10,
        span_mm=720,
        alignment="center",
        depth_alignment="center",
    )
    placements = {p.name: p for p in resolve_layout(row).placements}
    assert placements["fixed_left"].origin_mm == (0, 0, 0)
    assert placements["fill"].carcass_bounds_mm.width_mm == 500
    assert placements["fixed_right"].origin_mm == (620, 0, 0)

    centered = Row(
        "centered",
        (LayoutLeaf("narrow", 100, 20, 10),),
        span_mm=720,
        alignment="center",
    )
    assert resolve_layout(centered).placements[0].origin_mm == (310, 0, 0)


def test_stack_uses_occupied_height_once_and_keeps_bounds_distinct():
    first = LayoutLeaf(
        "first",
        100,
        100,
        50,
        Bounds3D(0, -20, 0, 100, 100, 60),
    )
    second = LayoutLeaf("second", 100, 100, 20)
    result = resolve_layout(Stack("stack", (first, second), gap_mm=5))
    placements = {p.name: p for p in result.placements}
    assert placements["second"].origin_mm == (0, 0, 65)
    assert placements["first"].carcass_bounds_mm.height_mm == 50
    assert placements["first"].occupied_world_bounds_mm.height_mm == 60
    assert result.carcass_bounds_mm.max_z == 85
    assert result.occupied_world_bounds_mm.min_y == -20


@pytest.mark.parametrize(
    "row",
    [
        Row(
            "overflow",
            (LayoutLeaf("a", 100, 10, 10), LayoutLeaf("b", 100, 10, 10)),
            span_mm=150,
        ),
        Row("unbounded", (LayoutLeaf("fill", Fill(), 10, 10),)),
    ],
)
def test_row_rejects_overflow_and_unbounded_fill(row):
    with pytest.raises(ValueError):
        resolve_layout(row)


@pytest.mark.parametrize("size", [-1, math.inf, math.nan])
def test_leaf_rejects_negative_or_nonfinite_dimensions(size):
    with pytest.raises(ValueError):
        resolve_layout(LayoutLeaf("bad", size, 20, 10))


def test_layout_rejects_cycles():
    node = Stack("cycle", ())
    object.__setattr__(node, "children", (node,))
    with pytest.raises(ValueError, match="cycle"):
        resolve_layout(node)


def test_layout_snapshot_round_trip_keeps_legacy_resolution():
    config = CabinetConfig(width=600, height=720, depth=500)
    layout = Row("row", (LayoutLeaf("left", 600, 500, 720),))
    project = CabinetProject(
        "legacy", (ProjectCabinet("cabinet", config),), layout=layout
    )
    payload = project_to_dict(project)
    restored = project_from_dict(payload)
    assert restored.layout == layout_from_dict(layout_to_dict(layout)) == layout
    assert restored.resolved() == project.resolved()
    assert build_project(payload).layout == layout

    # Snapshots that predate native layout remain readable and retain config resolution.
    old_payload = {key: value for key, value in payload.items() if key != "layout"}
    old_project = project_from_dict(old_payload)
    assert old_project.layout is None
    assert old_project.resolved() == project.resolved()
