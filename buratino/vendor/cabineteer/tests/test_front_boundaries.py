import pytest

from cabineteer.front_boundaries import resolve_front_boundaries
from cabineteer.spaces import AppliedFaceboard, Carcass, Door, Fr, Space, Split, resolve_model


def face(name, bounds, kind="door", **kwargs):
    return dict(id=name, coverage=bounds, plane=0, kind=kind, reveal=2,
                door_gap=2, drawer_front_gap=2, instance=name, **kwargs)


def test_adjacent_fronts_and_partial_seam():
    faces = [face("left", (0, 720, 0, 720)),
             face("lower", (720, 1440, 0, 300), "drawer_front"),
             face("upper", (720, 1440, 300, 600), "drawer_front")]
    bounds = resolve_front_boundaries(faces)
    assert bounds["left"] == (2, 719, 2, 718)
    assert bounds["lower"] == (721, 1438, 2, 299)
    faces[2]["drawer_front_gap"] = 4
    with pytest.raises(ValueError, match="lower.*upper|upper.*lower"):
        resolve_front_boundaries(faces)


def test_faceboard_gap_and_exposed_edges():
    faces = [face("a", (0, 100, 0, 100), "applied_faceboard", boundary_gap=4),
             face("b", (100, 200, 0, 100))]
    assert resolve_front_boundaries(faces)["a"] == (2, 98, 2, 98)
    faces[1]["boundary_gap"] = 3
    with pytest.raises(ValueError, match="conflicting front gaps"):
        resolve_front_boundaries(faces)


def test_outer_allowance_and_faceboard():
    root = Space("root", split=Split("height", [Space("a", Fr()), Space("b", Fr()), Space("c", Fr())]))
    model = resolve_model(Carcass(400, 236, 400), root, [AppliedFaceboard("panel", "c")])
    assert model.fronts[0]["origin"][2] == 152
    assert model.fronts[0]["size"][2] == 82
    assert model.fronts[0]["motion_group"] is None
    assert resolve_model(Carcass(400, 236, 400), Space("root"), [Door("door", "root")]).fronts[0]["hinge_side"] == "right"


def test_internal_allowance_belongs_to_parent():
    from cabineteer.spaces import Divider, Fixed
    lower = Space("lower", Fixed(200), split=Split("height", (Space("a", Fr()), Space("b", Fr()), Space("c", Fr()))))
    root = Space("root", split=Split("height", (lower, Divider("divider"), Space("upper", Fr()))))
    child = resolve_model(Carcass(400, 336, 400), root, [Door("child", "c")])
    parent = resolve_model(Carcass(400, 336, 400), root, [Door("parent", "lower")])
    assert (child.fronts[0]["origin"][2], child.fronts[0]["size"][2]) == (152, 62)
    assert (parent.fronts[0]["origin"][2], parent.fronts[0]["size"][2]) == (2, 223)


def test_nested_exterior_allowance_extends_to_outer_boundary():
    from cabineteer.spaces import Divider, Fixed
    upper = Space("upper", Fr(), split=Split("height", (Space("a", Fr()), Space("b", Fr()), Space("c", Fr()))))
    root = Space("root", split=Split("height", (Space("lower", Fixed(50)), Divider("divider"), upper)))
    model = resolve_model(Carcass(400, 237, 400), root, [Door("door", "c")])
    front = model.fronts[0]
    assert front["origin"][2] + front["size"][2] == 235


def test_bare_module_exterior_allowance_extends_to_module_edge():
    root = Space("insert", split=Split("height", (Space("a", Fr()), Space("b", Fr()), Space("c", Fr()))))
    model = resolve_model(Carcass(400, 236, 400), root, [Door("top", "c")], _bare=True)
    front = model.fronts[0]
    assert front["origin"][2] + front["size"][2] == 234
