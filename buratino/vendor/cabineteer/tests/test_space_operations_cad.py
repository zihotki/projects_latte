from copy import deepcopy
from types import SimpleNamespace

import pytest

pytest.importorskip("cadquery")

from cabineteer.space_adapter import materialize_model, space_model_records, validate_model
from cabineteer.drawer import DrawerConfig
from cabineteer.joinery import (
    DrawerJoineryStyle, apply_drawer_joinery_to_front_back,
    apply_drawer_joinery_to_side,
)
from cabineteer.operations import drawer_pockets


def _model(size=(20, 30, 40), operations=(), translation=(0, 0, 0)):
    part = {
        "id": "part", "kind": "test", "material": "wood",
        "profile": {"type": "box", "size": list(size)},
        "stock": {"dimensions": list(size), "thickness": min(size), "thickness_axis": size.index(min(size))},
        "transform": {"axes": [[1, 0, 0], [0, 1, 0], [0, 0, 1]], "translation": list(translation)},
        "operations": list(operations),
    }
    return SimpleNamespace(part_plan=SimpleNamespace(parts=[part], contacts=[]), contents=[], placements=[])


@pytest.mark.parametrize("face", ["x-", "x+", "y-", "y+", "z-", "z+"])
def test_pocket_uses_inward_depth_on_every_face_and_keeps_stock(face):
    dims = (17, 29, 43)
    record = {"id": "user/cut", "type": "pocket", "face": face,
              "u": 2, "v": 3, "size_u": 4, "size_v": 5, "depth": 6}
    model = _model(dims, [record])
    before = deepcopy(model.part_plan.parts[0]["stock"])
    shape = materialize_model(model)["part"]
    assert shape.val().Volume() == pytest.approx(17 * 29 * 43 - 4 * 5 * 6)
    assert model.part_plan.parts[0]["stock"] == before
    assert len(shape.solids().vals()) == 1


def test_bevel_is_a_swept_triangle_with_explicit_legs():
    bevel = {"id": "user/bevel", "type": "bevel", "face": "z-", "edge": "x+",
             "start": 4, "length": 10, "leg_a": 3, "leg_b": 4}
    shape = materialize_model(_model(operations=[bevel]))["part"]
    assert shape.val().Volume() == pytest.approx(20 * 30 * 40 - 3 * 4 / 2 * 10)
    assert shape.val().isValid()


@pytest.mark.parametrize("face,edge", [
    ("x-", "y-"), ("x+", "y+"), ("y-", "z-"),
    ("y+", "z+"), ("z-", "x-"), ("z+", "x+"),
])
def test_bevel_maps_legs_and_sweep_across_face_normals(face, edge):
    bevel = {"id": "user/bevel", "type": "bevel", "face": face, "edge": edge,
             "start": 3, "length": 8, "leg_a": 2, "leg_b": 5}
    shape = materialize_model(_model(size=(17, 29, 43), operations=[bevel]))["part"]
    assert shape.val().Volume() == pytest.approx(17 * 29 * 43 - 2 * 5 / 2 * 8)


@pytest.mark.parametrize("face", ["x-", "x+", "y-", "y+", "z-", "z+"])
@pytest.mark.parametrize("axis", ["u", "v"])
@pytest.mark.parametrize("length", [4, 12])
def test_mortise_is_an_obround_with_requested_axis(face, axis, length):
    mortise = {"id": "joint/j/a", "type": "mortise", "face": "z-",
               "u": 10, "v": 15, "axis": axis, "length": length, "width": 4, "depth": 5}
    mortise["face"] = face
    shape = materialize_model(_model(operations=[mortise]))["part"]
    area = (length - 4) * 4 + 3.141592653589793 * 2**2
    assert shape.val().Volume() == pytest.approx(20 * 30 * 40 - area * 5, abs=1e-5)


def test_translation_is_applied_after_local_cuts():
    bore = {"id": "user/bore", "type": "bore", "face": "x+",
            "u": 10, "v": 20, "diameter": 4, "depth": 7}
    shape = materialize_model(_model(operations=[bore], translation=(101, -20, 5)))["part"]
    bounds = shape.val().BoundingBox()
    assert (bounds.xmin, bounds.ymin, bounds.zmin) == pytest.approx((101, -20, 5))
    assert (bounds.xmax, bounds.ymax, bounds.zmax) == pytest.approx((121, 10, 45))
    assert shape.val().Volume() == pytest.approx(20 * 30 * 40 - 3.141592653589793 * 4 * 7)


def test_space_records_copy_datum_and_resolved_operations():
    records = [{"id": "drawer/part/bottom_groove", "part_id": "part",
                "type": "pocket", "source": "drawer", "role": "bottom_groove",
                "face": "x+", "u": 0, "v": 2, "size_u": 30, "size_v": 4, "depth": 6}]
    part = _model(operations=records).part_plan.parts[0]
    report = space_model_records(SimpleNamespace(
        part_plan=SimpleNamespace(parts=[part], contacts=[]), contents=[], placements=[]
    ))
    assert report["parts"][0]["datum"] == {"origin": "localminXYZ", "axes": "partXYZ"}
    assert report["parts"][0]["operations"] == records


def test_rabbet_and_bore_can_start_from_opposite_faces():
    records = [
        {"id": "user/rabbet", "type": "rabbet", "face": "z+", "edge": "x-",
         "start": 3, "length": 8, "width": 4, "depth": 2},
        {"id": "user/bore", "type": "bore", "face": "y-", "u": 10, "v": 20,
         "diameter": 4, "depth": 6},
    ]
    shape = materialize_model(_model(operations=records))["part"]
    expected = 20 * 30 * 40 - 8 * 4 * 2 - 3.141592653589793 * 4 * 6
    assert shape.val().Volume() == pytest.approx(expected, abs=1e-5)


def test_disconnected_solids_are_preserved_and_reported():
    cut = {"id": "user/split", "type": "pocket", "face": "z-", "u": 0,
           "v": 14, "size_u": 20, "size_v": 2, "depth": 40}
    model = _model(size=(20, 30, 40), operations=[cut])
    shape = materialize_model(model)["part"]
    assert len(shape.solids().vals()) == 2
    assert any(d["code"] == "disconnected_solids" for d in validate_model(model, shapes={"part": shape})["diagnostics"])


def test_fully_removed_stock_and_unknown_operations_fail():
    full = {"id": "user/full", "type": "pocket", "face": "z-", "u": 0,
            "v": 0, "size_u": 20, "size_v": 30, "depth": 40}
    with pytest.raises(ValueError, match="removes all stock"):
        materialize_model(_model(operations=[full]))
    unknown = {"id": "user/other", "type": "groove", "face": "z-"}
    with pytest.raises(ValueError, match="unsupported operation"):
        materialize_model(_model(operations=[unknown]))


@pytest.mark.parametrize("style", list(DrawerJoineryStyle))
@pytest.mark.parametrize("side", ["side_L", "side_R", "sub_front", "back"])
def test_drawer_wall_cuts_match_existing_joinery_helpers(style, side):
    import cadquery as cq

    cfg = DrawerConfig(opening_width=600, opening_height=200, opening_depth=500,
                       joinery_style=style, use_standard_height=False)
    if side.startswith("side"):
        size = (cfg.side_thickness, cfg.side_panel_length, cfg.box_height)
    else:
        size = (cfg.front_back_panel_length, cfg.front_back_thickness, cfg.box_height)
    records = drawer_pockets("drawer/" + side, side, size, cfg.bottom_dado_inset,
                             cfg.bottom_thickness, cfg.bottom_dado_depth, cfg.joinery)
    part = _model(size=size, operations=records).part_plan.parts[0]
    part["id"] = "drawer/" + side
    actual = materialize_model(SimpleNamespace(
        part_plan=SimpleNamespace(parts=[part], contacts=[]), contents=[], placements=[]
    ))[part["id"]].val()

    expected = cq.Workplane("XY").box(*size, centered=False)
    if side.startswith("side"):
        expected = apply_drawer_joinery_to_side(
            expected, cfg.joinery, size[1], size[2],
            side="left" if side == "side_L" else "right",
        )
    else:
        expected = apply_drawer_joinery_to_front_back(
            expected, cfg.joinery, size[0], size[2],
            position="front" if side == "sub_front" else "back",
        )
    # The former CAD branch cut the bottom groove as a box and delegated only
    # the corner geometry to these established helpers.
    groove = next(op for op in records if op["role"] == "bottom_groove")
    expected = expected.cut(_operation_cutter_for_test(cq, groove, size))
    left = actual.cut(expected.val()).Volume()
    right = expected.val().cut(actual).Volume()
    assert left + right == pytest.approx(0, abs=1e-5)


def _operation_cutter_for_test(cq, op, size):
    """Build the old rectangular drawer groove from its canonical pocket."""
    face = op["face"]
    axis = "xyz".index(face[0])
    positive = face[1] == "+"
    uv = [i for i in range(3) if i != axis]
    bounds = [[0, size[i]] for i in range(3)]
    bounds[axis] = [size[axis] - op["depth"], size[axis]] if positive else [0, op["depth"]]
    bounds[uv[0]] = [op["u"], op["u"] + op["size_u"]]
    bounds[uv[1]] = [op["v"], op["v"] + op["size_v"]]
    lengths = [high - low for low, high in bounds]
    return cq.Solid.makeBox(*lengths, pnt=cq.Vector(*(low for low, _ in bounds)))
