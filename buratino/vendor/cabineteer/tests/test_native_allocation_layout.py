from dataclasses import dataclass

import pytest
from cabineteer.allocation import Fixed, Fr
from cabineteer.layout import CabinetRef, Frame, LayoutLeaf, Row, Stack, Bounds3D, resolve_layout


@dataclass(frozen=True)
class Body:
    width: object
    height: object = 100
    depth: object = 100


@dataclass(frozen=True)
class Definition:
    carcass: Body


def test_nested_group_box_slack_and_weighted_tracks():
    defs = {"fixed": Definition(Body(100)), "flex": Definition(Body(Fr()))}
    inner = Row("inner", (CabinetRef("one", "fixed"),), size_x=Fixed(400))
    result = resolve_layout(Row("outer", (inner, CabinetRef("two", "fixed")), size_x=Fixed(500)), definitions=defs)
    assert result.placements[1].origin_mm[0] == 400
    assert result.allocations[1].slack == 300
    assert result.carcass_bounds_mm.width_mm == 500
    row = Row("run", (CabinetRef("fixed", "fixed"), Row("a", (CabinetRef("a", "flex"),), size_x=Fr(1)), Row("b", (CabinetRef("b", "flex"),), size_x=Fr(2))), gap_mm=10, size_x=Fixed(1000))
    result = resolve_layout(row, definitions=defs)
    assert [a.bounds.width_mm for a in result.allocations] == [1000, 293, 586]
    assert result.allocations[0].slack == 1


def test_stack_uses_structural_datum_and_fixed_cross_axis():
    lower = LayoutLeaf("lower", 720, 100, 720, Bounds3D(0, 0, -10, 720, 100, 720))
    upper = LayoutLeaf("upper", 720, 100, 600)
    result = resolve_layout(Stack("stack", (lower, Frame("frame", 720, 100, 100, 18), upper), gap_mm=10))
    assert [p.origin_mm[2] for p in result.placements] == [0, 730, 840]
    assert result.carcass_bounds_mm.height_mm == 1440
    assert result.occupied_world_bounds_mm.min_z == -10


def test_root_budget_and_dependency_validation():
    row = Row("run", (LayoutLeaf("one", Fr(), 100, 100),), size_x=Fr())
    assert resolve_layout(row, available_size_mm=(364, 100, 100)).carcass_bounds_mm.width_mm == 364
    with pytest.raises(ValueError, match="finite budget"):
        resolve_layout(row)
    with pytest.raises(ValueError, match="unresolved Fr"):
        resolve_layout(Row("natural", (LayoutLeaf("one", Fr(), 100, 100),)))
    with pytest.raises(ValueError, match="duplicate"):
        resolve_layout(Row("duplicates", (LayoutLeaf("a", 1, 1, 1), LayoutLeaf("a", 1, 1, 1))))
