import json
import xml.etree.ElementTree as ET

import cadquery as cq
import pytest

from buratino.exploded_views import _explode, _items, _layout, exploded_views

NS = {"s": "http://www.w3.org/2000/svg"}


def _shape_state(assembly):
    state = {}
    for name, item in assembly.objects.items():
        shape = item.toCompound()
        bounds = shape.BoundingBox()
        state[name] = (
            shape.Volume(),
            bounds.xmin,
            bounds.ymin,
            bounds.zmin,
            bounds.xmax,
            bounds.ymax,
            bounds.zmax,
            len(shape.Faces()),
            len(shape.Edges()),
        )
    return state


def test_exploded_views_uses_machined_profile_solids_without_mutation():
    profile = (
        cq.Workplane("XY")
        .polyline([(0, 0), (120, 0), (120, 50), (75, 85), (0, 85)])
        .close()
        .extrude(12)
    )
    cutter = cq.Workplane("XY").box(9, 30, 8).translate((35, 35, 10))
    machined = profile.cut(cutter).val()
    mirrored = machined.mirror("YZ")
    assembly = cq.Assembly()
    parts = []
    for ident, shape in (("left", machined), ("right", mirrored)):
        assembly.add(shape.translate((600, -120, 900)), name=ident)
        parts.append({"id": ident, "role": ident, "cabinet_id": "cab"})
    before = _shape_state(assembly)
    rows = _layout(parts, assembly, {"left": "P01", "right": "P02"})
    exploded = _explode(rows)
    for row, (_, copy) in zip(rows, exploded, strict=True):
        assert copy.Volume() == pytest.approx(row[2].Volume())
        assert len(copy.Faces()) == len(row[2].Faces())
        assert len(copy.Edges()) == len(row[2].Edges())
        assert copy.Center().toTuple() != row[2].Center().toTuple()
    html = exploded_views(assembly, parts, {"left": "P01", "right": "P02"})
    assert _shape_state(assembly) == before
    root = ET.fromstring(f"<div>{html}</div>")
    assert sorted(e.text for e in root.findall(".//s:text", NS)) == ["P01", "P02"]
    panels = root.findall(".//s:g[@data-part-id]", NS)
    assert {p.get("data-part-id") for p in panels} == {"left", "right"}
    assert all(len(p.findall("s:path", NS)) == 2 for p in panels)
    # Actual filled face triangles and CAD edge paths both have geometry.
    assert all(len(path.get("d")) > 100 for p in panels for path in p)


def test_repeated_items_share_view_with_complete_part_coverage():
    assembly = cq.Assembly()
    parts = []
    codes = {}
    for instance, offset in (("a", 0), ("b", 500)):
        for component, origin, code in (
            ("bottom", (0, 0, 0), "P01"),
            ("front", (0, -15, 30), "P02"),
        ):
            ident = f"{instance}.{component}"
            assembly.add(
                cq.Workplane("XY")
                .box(120, 80, 12)
                .translate((offset + origin[0], origin[1], origin[2])),
                name=ident,
            )
            parts.append(
                {
                    "id": ident,
                    "role": ident,
                    "cabinet_id": instance,
                    # The front must join the drawer through its motion group.
                    **(
                        {"motion_group": instance}
                        if component == "front"
                        else {"instance_id": instance}
                    ),
                }
            )
            codes[ident] = code
    assert len(_items(parts)) == 2
    before = _shape_state(assembly)
    root = ET.fromstring(f"<div>{exploded_views(assembly, parts, codes)}</div>")
    figures = root.findall("figure")
    assert len(figures) == 1
    assert figures[0].find("figcaption").text == "Drawer ×2"
    assert set(json.loads(figures[0].get("data-part-ids"))) == set(codes)
    panels = root.findall(".//s:g[@data-part-id]", NS)
    all_ids = [ident for p in panels for ident in json.loads(p.get("data-part-ids"))]
    assert sorted(all_ids) == sorted(codes)
    assert len(root.findall(".//s:text", NS)) == 2
    assert _shape_state(assembly) == before
    svg = root.find(".//s:svg", NS)
    _, _, width, height = map(float, svg.get("viewBox").split())
    assert width == 440
    for label in root.findall(".//s:text", NS):
        assert 0 < float(label.get("x")) < width
        assert 0 < float(label.get("y")) < height


def test_drawers_group_when_applied_front_positions_differ():
    assembly = cq.Assembly()
    parts = []
    codes = {}
    for index, offset in enumerate((0, 300, 600, 900)):
        for component, origin, code in (
            ("bottom", (0, 0, 0), "P01"),
            ("drawer_front", (0, -15 - index, 30 + index), "P02"),
        ):
            ident = f"drawer-{index}.{component}"
            assembly.add(
                cq.Workplane("XY")
                .box(120, 80, 12)
                .translate((offset + origin[0], origin[1], origin[2])),
                name=ident,
            )
            parts.append(
                {
                    "id": ident,
                    "role": ident,
                    "cabinet_id": f"cabinet-{index}",
                    "component": component,
                    **(
                        {"motion_group": f"drawer-{index}"}
                        if component == "drawer_front"
                        else {"instance_id": f"drawer-{index}"}
                    ),
                }
            )
            codes[ident] = code

    root = ET.fromstring(f"<div>{exploded_views(assembly, parts, codes)}</div>")
    figures = root.findall("figure")
    assert len(figures) == 1
    assert figures[0].find("figcaption").text == "Drawer ×4"
    assert sorted(json.loads(figures[0].get("data-part-ids"))) == sorted(codes)
    panels = root.findall(".//s:g[@data-part-id]", NS)
    assert {panel.get("data-part-id") for panel in panels} == {
        "drawer-0.bottom",
        "drawer-0.drawer_front",
    }
    for panel in panels:
        ids = json.loads(panel.get("data-part-ids"))
        assert len(ids) == 4
        assert len(set(ids)) == 4
    assert len(root.findall(".//s:text", NS)) == 2


def test_drawers_keep_front_codes_and_box_placement_in_signature():
    assembly = cq.Assembly()
    parts = []
    codes = {}
    for name, bottom_x, front_code in (
        ("base", 0, "P02"),
        ("other-front", 0, "P03"),
        ("other-box", 8, "P02"),
        ("shifted-front", 0, "P02"),
    ):
        for component, x, code in (
            ("bottom", 0, "P01"),
            ("side_left", bottom_x, "P04"),
            ("drawer_front", 0, front_code),
        ):
            ident = f"{name}.{component}"
            assembly.add(
                cq.Workplane("XY").box(120, 80, 12).translate((x, 0, 0)),
                name=ident,
            )
            parts.append(
                {
                    "id": ident,
                    "role": ident,
                    "cabinet_id": name,
                    "component": component,
                    **(
                        {"motion_group": name}
                        if component == "drawer_front"
                        else {"instance_id": name}
                    ),
                }
            )
            codes[ident] = code
    root = ET.fromstring(f"<div>{exploded_views(assembly, parts, codes)}</div>")
    captions = sorted(
        figure.find("figcaption").text for figure in root.findall("figure")
    )
    assert captions == ["Drawer", "Drawer", "Drawer ×2"]


def test_different_placed_orientations_do_not_share_view():
    assembly = cq.Assembly()
    shape = cq.Workplane("XY").box(120, 80, 12)
    assembly.add(shape, name="a")
    assembly.add(shape.rotate((0, 0, 0), (0, 0, 1), 90), name="b")
    parts = [{"id": name, "role": name, "cabinet_id": name} for name in ("a", "b")]
    html = exploded_views(assembly, parts, {"a": "P01", "b": "P01"})
    assert html.count("<figure ") == 2


def test_missing_geometry_has_no_invented_diagram():
    assert exploded_views(None, [{"id": "panel"}], {}) == ""
    assert exploded_views(cq.Assembly(), [], {}) == ""


def test_profile_records_use_owner_and_explicit_drawer_metadata():
    parts = [
        {"id": "upper.side_left", "owner": "upper", "component": "side_left"},
        {"id": "lower.side_left", "owner": "lower", "component": "side_left"},
        {
            "id": "upper.section-1.drawer.bottom",
            "instance_id": "upper.section-1.drawer",
            "owner": "upper",
            "component": "bottom",
        },
        {
            "id": "upper.section-1.drawer_front",
            "motion_group": "upper.section-1.drawer",
            "owner": "upper",
            "component": "drawer_front",
        },
        {
            "id": "upper.door",
            "owner": "upper",
            "component": "door",
            "instance_id": "door-1",
        },
    ]
    groups = _items(parts)
    assert set(groups) == {
        ("upper", None),
        ("lower", None),
        ("upper", "upper.section-1.drawer"),
    }
    assert {p["id"] for p in groups[("upper", "upper.section-1.drawer")]} == {
        "upper.section-1.drawer.bottom",
        "upper.section-1.drawer_front",
    }


def test_many_panels_on_one_side_keep_all_labels_inside_viewport():
    assembly = cq.Assembly()
    parts = []
    codes = {}
    panel = cq.Workplane("XY").box(10, 10, 1)
    for index in range(21):
        ident = f"panel-{index}"
        # One distant panel shifts the viewport center away from the other 20.
        x = 1000 if index == 20 else index * 2
        assembly.add(panel.translate((0, x, 0)), name=ident)
        parts.append({"id": ident, "role": ident, "cabinet_id": "body"})
        codes[ident] = f"P{index + 1:02}"
    root = ET.fromstring(f"<div>{exploded_views(assembly, parts, codes)}</div>")
    svg = root.find(".//s:svg", NS)
    _, _, width, height = map(float, svg.get("viewBox").split())
    labels = root.findall(".//s:text", NS)
    assert len(labels) == 21
    side_counts = [
        sum(label.get("text-anchor") == side for label in labels)
        for side in ("start", "end")
    ]
    assert max(side_counts) == 20
    for label in labels:
        assert 0 < float(label.get("x")) < width
        # Include the text baseline offset, font extent and white outline.
        assert 16 < float(label.get("y")) < height - 16


def test_exploded_projection_keeps_world_z_up_and_matches_cad_edges():
    from buratino.exploded_views import _DIRECTION, _X_DIRECTION
    from buratino.panel_views import _projected_geometry, _svg_projector

    shape = cq.Workplane("XY").box(120, 80, 12).val()
    bounds = _projected_geometry(shape, _DIRECTION, _X_DIRECTION).BoundingBox()
    project = _svg_projector(_DIRECTION, bounds, 1, 0, 0, x_direction=_X_DIRECTION)
    origin = project((0, 0, 0))
    up = project((0, 0, 100))
    assert up[0] == pytest.approx(origin[0])
    assert up[1] < origin[1]
    corners = [project(vertex.Center().toTuple()) for vertex in shape.Vertices()]
    assert min(x for x, _ in corners) == pytest.approx(0, abs=1e-6)
    assert max(x for x, _ in corners) == pytest.approx(bounds.xlen, abs=1e-6)
    assert min(y for _, y in corners) == pytest.approx(0, abs=1e-6)
    assert max(y for _, y in corners) == pytest.approx(bounds.ylen, abs=1e-6)


def test_applied_front_and_subfront_explode_into_separate_layers():
    assembly = cq.Assembly()
    parts = []
    for ident, y, width, height in (
        ("applied-front", 0, 200, 100),
        ("subfront", 18, 170, 80),
        ("back", 250, 170, 80),
    ):
        assembly.add(
            cq.Workplane("XY").box(width, 18, height).translate((0, y, 0)),
            name=ident,
        )
        parts.append({"id": ident, "role": ident})
    rows = _layout(parts, assembly, {p["id"]: p["id"] for p in parts})
    original = {part["id"]: shape for _, part, shape in rows}
    copies = dict((part["id"], shape) for part, shape in _explode(rows))
    shifts = {
        ident: copies[ident].Center().y - shape.Center().y
        for ident, shape in original.items()
    }
    assert shifts["subfront"] < 0
    assert shifts["applied-front"] == pytest.approx(2 * shifts["subfront"])
    assert copies["applied-front"].BoundingBox().ymax < (
        copies["subfront"].BoundingBox().ymin - 50
    )
    for ident, shape in copies.items():
        assert shape.Volume() == pytest.approx(original[ident].Volume())
