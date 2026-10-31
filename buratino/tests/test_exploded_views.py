import copy
import json
import xml.etree.ElementTree as ET

import cadquery as cq
import pytest

from buratino.exploded_views import (
    _DIRECTION,
    _X_DIRECTION,
    _drawing,
    _explode,
    _items,
    _layout,
    _placed_shape,
    _visible_projections,
    exploded_views,
)

NS = {"s": "http://www.w3.org/2000/svg"}
AXES = ((1, 0, 0), (0, 1, 0), (0, 0, 1))


def _part(ident, member, item="cabinet", recipe="rectangular", **extra):
    return {
        "id": ident,
        "role": ident,
        "report": {"item_id": item, "member": member, "recipe": recipe, "axes": AXES},
        **extra,
    }


def _state(assembly):
    result = {}
    for name in assembly.objects:
        shape = _placed_shape(assembly, name)
        box = shape.BoundingBox()
        result[name] = (
            shape.Volume(),
            (box.xmin, box.ymin, box.zmin, box.xmax, box.ymax, box.zmax),
            len(shape.Faces()),
            len(shape.Edges()),
        )
    return result


def _root(assembly, parts, codes):
    return ET.fromstring(f"<div>{exploded_views(assembly, parts, codes)}</div>")


def test_real_machined_solids_and_manufacturing_records_are_unchanged():
    profile = (
        cq.Workplane("XY")
        .polyline([(0, 0), (120, 0), (120, 50), (75, 85), (0, 85)])
        .close()
        .extrude(12)
    )
    machined = profile.cut(
        cq.Workplane("XY").box(9, 30, 8).translate((35, 35, 10))
    ).val()
    assembly = cq.Assembly()
    parts = []
    for ident, shape in (("left", machined), ("right", machined.mirror("YZ"))):
        assembly.add(shape.translate((600, -120, 900)), name=ident)
        parts.append(
            _part(
                ident,
                "side_left" if ident == "left" else "side_right",
                recipe="profiled",
                stock_mm={"thickness": 12},
                operations=[{"kind": "pocket", "depth_mm": 8}],
            )
        )
    before, records = _state(assembly), copy.deepcopy(parts)
    rows = _layout(parts, assembly, {"left": "P01", "right": "P02"})
    for row, (_, moved) in zip(rows, _explode(rows), strict=True):
        assert moved.Volume() == pytest.approx(row[2].Volume())
        assert (len(moved.Faces()), len(moved.Edges())) == (
            len(row[2].Faces()),
            len(row[2].Edges()),
        )
        assert moved.Center().toTuple() != row[2].Center().toTuple()
    root = _root(assembly, parts, {"left": "P01", "right": "P02"})
    assert sorted(e.text for e in root.findall(".//s:text", NS)) == ["P01", "P02"]
    assert _state(assembly) == before
    assert parts == records


def test_nested_locations_and_rotated_item_axes_are_applied_once():
    panel = cq.Workplane("XY").box(120, 80, 12).val()
    nested = cq.Assembly(name="nested")
    nested.add(panel, name="panel", loc=cq.Location((10, 0, 0)))
    assembly = cq.Assembly(loc=cq.Location((0, 200, 0)))
    assembly.add(nested, loc=cq.Location((100, 20, 0), (0, 0, 1), 90))
    part = _part("panel", "side_right", local_frame={"thickness_axis": (0, 0, 1)})
    part["role"] = "nested/panel"
    part["report"]["axes"] = ((0, 1, 0), (-1, 0, 0), (0, 0, 1))
    rows = _layout([part], assembly, {"panel": "P01"})
    assert rows[0][2].Center().toTuple() == pytest.approx((100, 230, 0))
    moved = _explode(rows)[0][1]
    delta = tuple(
        b - a
        for a, b in zip(
            rows[0][2].Center().toTuple(), moved.Center().toTuple(), strict=True
        )
    )
    assert delta[0] == pytest.approx(0)
    assert delta[1] > 0
    assert delta[2] == pytest.approx(0)
    # The independent item basis also rotates the camera, not the stock frame.
    assert _root(assembly, [part], {"panel": "P01"}).find(".//s:text", NS).text == "P01"


@pytest.mark.parametrize("recipe", ["drawer", "rectangular", "profiled", "frame"])
def test_fixed_recipes_preserve_group_poses_and_use_item_directions(recipe):
    assembly = cq.Assembly()
    members = (
        ("rail_left", "rail_right")
        if recipe == "frame"
        else ("side_left", "side_right", "top", "top")
    )
    parts = []
    for i, member in enumerate(members):
        ident = str(i)
        assembly.add(
            cq.Workplane("XY").box(20, 100, 80).translate((i * 100, 0, 0)), name=ident
        )
        parts.append(_part(ident, member, recipe=recipe))
    rows = _layout(parts, assembly, {p["id"]: p["id"] for p in parts})
    source = {p["id"]: shape.Center() for _, p, shape in rows}
    moved = {p["id"]: shape.Center() for p, shape in _explode(rows)}
    assert moved["0"].x < source["0"].x
    assert moved["1"].x > source["1"].x
    if recipe != "frame":
        assert (moved["3"] - moved["2"]).toTuple() == pytest.approx(
            (source["3"] - source["2"]).toTuple()
        )
        assert moved["2"].z > source["2"].z


def test_translated_items_collapse_but_arrangement_machining_and_presentation_do_not():
    assembly = cq.Assembly()
    parts, codes = [], {}
    for item, offset, side_x, recipe, operation in (
        ("a", 0, 0, "drawer", 1),
        ("b", 500, 0, "drawer", 1),
        ("arrangement", 1000, 8, "drawer", 1),
        ("machining", 1500, 0, "drawer", 2),
        ("presentation", 2000, 0, "rectangular", 1),
    ):
        for member, x, code in (("bottom", 0, "P01"), ("side_left", side_x, "P02")):
            ident = f"{item}.{member}"
            assembly.add(
                cq.Workplane("XY").box(120, 80, 12).translate((offset + x, 0, 0)),
                name=ident,
            )
            parts.append(
                _part(
                    ident,
                    member,
                    item,
                    recipe,
                    operations=[
                        {
                            "id": ident,
                            "joint_id": ident,
                            "joint_side": "a",
                            "depth": operation,
                        }
                    ],
                )
            )
            codes[ident] = code
    root = _root(assembly, parts, codes)
    figures = root.findall("figure")
    assert len(figures) == 4
    assert [f.find("figcaption").text for f in figures].count("Drawer ×2") == 1
    ids = [ident for f in figures for ident in json.loads(f.get("data-part-ids"))]
    assert sorted(ids) == sorted(p["id"] for p in parts)


def test_geometry_with_same_code_and_bounds_stays_distinct():
    assembly = cq.Assembly()
    parts = []
    for i, x in enumerate((20, 70)):
        shape = (
            cq.Workplane("XY")
            .box(120, 80, 12)
            .cut(cq.Workplane("XY").center(x - 60, 0).circle(4).extrude(30, both=True))
        )
        assembly.add(shape, name=str(i))
        parts.append(_part(str(i), "bottom", str(i)))
    assert len(_root(assembly, parts, {"0": "P01", "1": "P01"}).findall("figure")) == 2


def test_facades_are_excluded_and_roof_uses_report_membership():
    assembly = cq.Assembly()
    parts = [
        _part("body", "side_left", recipe="profiled", owner="upper"),
        _part("roof", "top", recipe="profiled", owner="roof-owner"),
        {"id": "front", "component": "drawer_front", "motion_group": "drawer"},
    ]
    for ident, z in (("body", 0), ("roof", 100)):
        assembly.add(
            cq.Workplane("XY").box(120, 80, 12).translate((0, 0, z)), name=ident
        )
    assert len(_items(parts)) == 1
    root = _root(assembly, parts, {"body": "P01", "roof": "P02"})
    assert len(root.findall("figure")) == 1
    assert set(json.loads(root.find("figure").get("data-part-ids"))) == {"body", "roof"}
    assert parts[1]["owner"] == "roof-owner"


def test_context_occludes_normally_and_is_not_labelled_or_counted_twice():
    plane = cq.Plane(origin=(0, 0, 0), xDir=_X_DIRECTION, normal=_DIRECTION)
    rear = cq.Workplane(plane).box(10, 10, 1).val()
    front = cq.Workplane(plane).transformed(offset=(0, 0, 10)).box(20, 20, 1).val()
    assembly = cq.Assembly()
    parts = [_part("rear", "divider"), _part("front", "back")]
    for part, shape in zip(parts, (rear, front), strict=True):
        assembly.add(shape, name=part["id"])
    rows = _layout(parts, assembly, {"rear": "P01", "front": "P02"})
    panels = [(part, shape) for _, part, shape in rows]
    svg, covered = _drawing(rows, [rows], panels, {"rear"})
    root = ET.fromstring(svg)
    assert not root.findall(".//s:text", NS)
    assert covered == set()
    assert root.find(".//s:g[@data-part-id='rear']/s:path", NS).get("d") == ""
    result = _root(assembly, parts, {"rear": "P01", "front": "P02"})
    assert {e.text for e in result.findall(".//s:text", NS)} == {"P02"}
    assert [link.get("href") for link in result.findall(".//a")] == [
        "report.html#part-P01"
    ]
    assert json.loads(result.find("figure").get("data-part-ids")).count("rear") == 1


@pytest.mark.parametrize("two_strips", [False, True])
def test_tiny_visible_sliver_is_not_readable_coverage(two_strips):
    rear = cq.Workplane("XY").box(100, 100, 1).val()
    front = (
        cq.Workplane("XY")
        .box(99.6 if two_strips else 100, 100, 1)
        .translate((0 if two_strips else 0.2, 0, 10))
        .val()
    )
    assembly = cq.Assembly()
    parts = [_part("rear", "divider"), _part("front", "back")]
    for part, shape in zip(parts, (rear, front), strict=True):
        assembly.add(shape, name=part["id"])
    rows = _layout(parts, assembly, {"rear": "P01", "front": "P02"})
    svg, covered = _drawing(
        rows,
        [rows],
        [(p, s) for _, p, s in rows],
        {"rear"},
        direction=(0, 0, 1),
        x_direction=(1, 0, 0),
    )
    assert covered == set()
    assert not ET.fromstring(svg).findall(".//s:text", NS)


@pytest.mark.parametrize("fault", ["unknown", "duplicate", "shape", "code", "axes"])
def test_invalid_members_fail_with_affected_ids(fault):
    assembly = cq.Assembly()
    assembly.add(cq.Workplane("XY").box(100, 80, 12), name="panel")
    parts, codes = [_part("panel", "bottom")], {"panel": "P01"}
    if fault == "unknown":
        parts[0]["report"]["member"] = "guess-from-shape"
    elif fault == "duplicate":
        parts *= 2
    elif fault == "shape":
        parts[0]["role"] = "missing"
    elif fault == "code":
        codes = {}
    else:
        parts[0]["report"]["axes"] = ((2, 0, 0), (0, 1, 0), (0, 0, 1))
    with pytest.raises(ValueError, match="panel"):
        exploded_views(assembly, parts, codes)


def _segments(shape):
    return sorted(
        tuple(
            sorted(
                tuple(round(v, 7) for v in point.toTuple())
                for point in (edge.startPoint(), edge.endPoint())
            )
        )
        for edge in shape.Edges()
    )


def test_global_hlr_front_plate_hides_rear_plate():
    rear = cq.Workplane("XY").box(10, 10, 1).val()
    front = cq.Workplane("XY").box(20, 20, 1).translate((0, 0, 10)).val()
    alone = _visible_projections([rear], (0, 0, 1), (1, 0, 0))[0]
    rear_view, front_view = _visible_projections([rear, front], (0, 0, 1), (1, 0, 0))
    assert len(alone.Edges()) == 4
    assert rear_view.Edges() == []
    assert sum(edge.Length() for edge in front_view.Edges()) == pytest.approx(80)


def test_global_hlr_clips_rear_edges_and_is_independent_of_input_order():
    rear = cq.Workplane("XY").box(10, 10, 1).val()
    front = cq.Workplane("XY").box(10, 20, 1).translate((5, 0, 10)).val()
    views = _visible_projections([rear, front], (0, 0, 1), (1, 0, 0))
    reversed_views = _visible_projections([front, rear], (0, 0, 1), (1, 0, 0))
    assert _segments(views[0]) == [
        ((-5, -5, 0), (-5, 5, 0)),
        ((-5, -5, 0), (0, -5, 0)),
        ((-5, 5, 0), (0, 5, 0)),
    ]
    assert [_segments(v) for v in views] == [
        _segments(v) for v in reversed(reversed_views)
    ]


def test_many_labels_stay_inside_viewport():
    assembly = cq.Assembly()
    parts, codes = [], {}
    for i in range(21):
        ident = str(i)
        assembly.add(
            cq.Workplane("XY").box(10, 10, 1).translate((0, i * 20, 0)), name=ident
        )
        parts.append(_part(ident, "shelf"))
        codes[ident] = f"P{i + 1:02}"
    root = _root(assembly, parts, codes)
    assert {e.text for e in root.findall(".//s:text", NS)} == set(codes.values())
    for svg in root.findall(".//s:svg", NS):
        _, _, width, height = map(float, svg.get("viewBox").split())
        for label in svg.findall("s:text", NS):
            assert 0 < float(label.get("x")) < width
            assert 16 < float(label.get("y")) < height - 16


def test_space_frames_publish_members_and_rotated_space_axes_remain_unsupported():
    from types import SimpleNamespace

    from cabineteer.layout import Frame
    from cabineteer.space_adapter import materialize_model, space_model_records
    from cabineteer.space_assembly import resolve_space_assembly

    project = SimpleNamespace(
        layout=Frame("support", 700, 400, 50, 18),
        space_model=None,
        space_cabinets=(),
        space_modules=(),
    )
    plan = resolve_space_assembly(project)
    records = space_model_records(plan)["parts"]
    assert {p["report"]["member"] for p in records} == {
        "rail_front",
        "rail_back",
        "rail_left",
        "rail_right",
    }
    assert len({p["report"]["item_id"] for p in records}) == 1
    assert all(p["report"]["recipe"] == "frame" for p in records)
    source = copy.deepcopy(plan.part_plan.parts)
    shapes = materialize_model(plan)
    assembly = cq.Assembly()
    for part in records:
        assembly.add(shapes[part["id"]], name=part["role"])
    root = _root(
        assembly, records, {p["id"]: f"P{i:02}" for i, p in enumerate(records)}
    )
    assert len(root.findall(".//s:text", NS)) == 4
    assert plan.part_plan.parts == source
    plan.part_plan.parts[0]["transform"]["axes"] = [[0, 1, 0], [-1, 0, 0], [0, 0, 1]]
    with pytest.raises(ValueError, match="unsupported transform axes"):
        materialize_model(plan)


def test_two_thin_visible_strips_link_to_part_drawing_without_new_view(monkeypatch):
    import buratino.exploded_views as views

    monkeypatch.setattr(views, "_DIRECTION", (0, 0, 1))
    monkeypatch.setattr(views, "_X_DIRECTION", (1, 0, 0))
    assembly = cq.Assembly()
    assembly.add(cq.Workplane("XY").box(100, 100, 1), name="rear")
    assembly.add(
        cq.Workplane("XY").box(99.6, 100, 1).translate((0, 0, 10)), name="front"
    )
    parts = [_part("rear", "divider"), _part("front", "divider")]
    before = _state(assembly)
    root = _root(assembly, parts, {"rear": "P01", "front": "P02"})
    assert len(root.findall(".//div[@class='exploded-view']")) == 1
    assert not root.findall(".//div/p")
    assert [link.get("href") for link in root.findall(".//a")] == [
        "report.html#part-P01"
    ]
    assert {label.text for label in root.findall(".//s:text", NS)} == {"P02"}
    assert _state(assembly) == before


def test_single_interior_member_uses_the_only_assembly_view():
    assembly = cq.Assembly()
    assembly.add(cq.Workplane("XY").box(100, 80, 12), name="shelf")
    parts = [_part("shelf", "shelf")]

    root = _root(assembly, parts, {"shelf": "P01"})

    assert len(root.findall(".//div[@class='exploded-view']")) == 1
    assert root.find(".//div[@class='exploded-view']/p") is None
    assert [label.text for label in root.findall(".//s:text", NS)] == ["P01"]


def test_multiple_interior_members_are_absent_from_exterior_view():
    assembly = cq.Assembly()
    parts = [
        _part("left", "side_left"),
        _part("shelf", "shelf"),
        _part("divider", "divider"),
    ]
    for part, x in zip(parts, (0, 20, 40), strict=True):
        assembly.add(
            cq.Workplane("XY").box(20, 80, 60).translate((x, 0, 0)),
            name=part["id"],
        )

    root = _root(assembly, parts, {"left": "P01", "shelf": "P02", "divider": "P03"})

    exterior = root.find(".//div[@data-view='Exterior']")
    interior = root.find(".//div[@data-view='Interior']")
    assert exterior is not None
    assert interior is not None
    assert exterior.find(".//s:g[@data-part-id='shelf']", NS) is None
    assert exterior.find(".//s:g[@data-part-id='divider']", NS) is None
    assert interior.find(".//s:g[@data-part-id='shelf']", NS) is not None
    assert interior.find(".//s:g[@data-part-id='divider']", NS) is not None
