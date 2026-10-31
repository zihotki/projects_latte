from xml.etree import ElementTree

import cadquery as cq
import pytest

from buratino.panel_views import panel_views


def test_curved_panel_has_projected_dimensions():
    assembly = cq.Assembly(name="root")
    assembly.add(cq.Workplane("XY").circle(50).extrude(18), name="round")
    part = {
        "id": "round",
        "role": "round",
        "finished_mm": {
            "length": 100,
            "width": 100,
            "thickness": 18,
        },
    }
    view = panel_views(assembly, [part])["round"]
    assert view.count(">100.0 mm</text>") == 2
    viewport = ElementTree.fromstring(view)
    assert viewport.attrib["viewBox"] == "0 0 360 255"
    assert float(viewport.attrib["width"]) == 360
    assert float(viewport.attrib["height"]) == 255
    assert "Stock thickness: 18 mm" in view
    assert "Max stock blank" not in view


def test_different_stock_envelope_keeps_full_dimensions():
    assembly = cq.Assembly(name="root")
    assembly.add(cq.Workplane("XY").box(100, 50, 18), name="panel")
    part = {
        "id": "panel",
        "role": "panel",
        "finished_mm": {
            "length": 100,
            "width": 50,
            "thickness": 18,
        },
        "blank_mm": {"length": 110, "width": 50, "thickness": 18},
    }
    view = panel_views(assembly, [part])["panel"]
    assert "Max stock blank" in view
    assert "110 × 50 × 18 mm" in view
    assert "Stock thickness:" not in view


def test_missing_panel_is_not_silently_rendered():
    assembly = cq.Assembly(name="root")
    with pytest.raises(KeyError):
        panel_views(assembly, [{"id": "missing", "role": "missing"}])


def test_groups_only_matching_solids_and_processing():
    from buratino.panel_views import panel_groups

    assembly = cq.Assembly(name="root")
    plain = cq.Workplane("XY").box(100, 50, 10).val()
    notch = cq.Workplane("XY").box(10, 10, 10).translate((45, 20, 0)).val()
    assembly.add(plain, name="first")
    assembly.add(plain.translate((200, 0, 0)), name="copy")
    assembly.add(plain.cut(notch), name="notched")
    assembly.add(plain, name="different_processing")
    parts = [
        {"id": name, "role": name, "component": "panel", "material": "board"}
        for name in ("first", "copy", "notched", "different_processing")
    ]
    parts[-1]["machining_assumptions"] = [{"operation": "drill"}]
    assert [
        [part["id"] for part in group] for group in panel_groups(assembly, parts)
    ] == [
        ["first", "copy"],
        ["notched"],
        ["different_processing"],
    ]


def test_groups_equal_top_and_bottom_only_when_joint_assignments_match():
    from buratino.panel_views import panel_groups

    assembly = cq.Assembly(name="root")
    solid = cq.Workplane("XY").box(100, 50, 10).val()
    components = ("top", "bottom", "left_side", "right_side")
    parts = []
    for component in components:
        assembly.add(solid, name=component)
        parts.append({"id": component, "role": component, "component": component})
    joints = [
        {
            "id": f"{panel}-{side}",
            "parts": [panel, side],
            "type": "domino",
            "tenon": "6x40",
        }
        for panel in ("top", "bottom")
        for side in ("left_side", "right_side")
    ]
    groups = panel_groups(assembly, parts, joints)
    assert [[part["id"] for part in group] for group in groups] == [
        ["top", "bottom"],
        ["left_side"],
        ["right_side"],
    ]
    joints[0]["tenon"] = "8x40"
    assert len(panel_groups(assembly, parts, joints)) == 4


def test_sloped_profile_dimension_uses_projected_edge():
    assembly = cq.Assembly(name="root")
    shape = (
        cq.Workplane("XY")
        .polyline([(0, 0), (100, 0), (100, 50), (0, 25)])
        .close()
        .extrude(10)
    )
    assembly.add(shape, name="sloped")
    part = {
        "id": "sloped",
        "role": "sloped",
        "finished_mm": {"length": 100, "width": 50, "thickness": 10},
    }
    view = panel_views(assembly, [part])["sloped"]
    assert "103.1 mm at 14.0°" in view


def _grooved_space_part(face="x+", translation=(123, -49, 77)):
    return {
        "id": "grooved",
        "role": "grooved",
        "profile": {"type": "box", "size": [18, 544, 160]},
        "transform": {
            "translation": translation,
            "axes": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        },
        "stock_mm": {"length": 544, "width": 160, "thickness": 18},
        "blank_mm": {"length": 544, "width": 160, "thickness": 18},
        "operations": [
            {
                "id": "drawer/grooved/bottom_groove",
                "role": "bottom_groove",
                "type": "pocket",
                "face": face,
                "u": 0,
                "v": 13,
                "size_u": 544,
                "size_v": 12,
                "depth": 6,
            }
        ],
    }


@pytest.mark.parametrize("face", ["x-", "x+"])
def test_translated_opposite_face_grooves_are_dimensioned_without_geometry_changes(
    face,
):
    from copy import deepcopy

    from cabineteer.space_adapter import materialize_box_part

    from buratino.machining_dimensions import groove_dimensions

    part = _grooved_space_part(face)
    before = deepcopy(part)
    shape = materialize_box_part(part).translate(part["transform"]["translation"])
    volume = shape.val().Volume()
    center = shape.val().Center().toTuple()
    assembly = cq.Assembly(name="root")
    assembly.add(shape, name=part["role"])
    (feature,) = groove_dimensions(part)
    x = 123 + (18 if face == "x+" else 0)
    assert feature.profile_points == (
        (x, -49, 90),
        (x, 495, 90),
        (x, 495, 102),
        (x, -49, 102),
    )
    assert feature.width_points == ((x, 320.92, 90), (x, 320.92, 102))
    assert feature.inset_points == ((x, 179.48, 77), (x, 179.48, 90))
    view = panel_views(assembly, [part])[part["id"]]
    assert "G1 width: 12 mm" in view
    assert "G1 inset: 13 mm" in view
    assert "6 mm deep" in view
    assert 'class="groove-width"' in view
    assert 'class="groove-inset"' in view
    assert 'class="groove-section"' in view
    assert "544.0 mm" in view and "160.0 mm" in view
    assert ElementTree.fromstring(view).attrib["viewBox"] == "0 0 360 365"
    assert part == before
    assert shape.val().Volume() == volume
    assert assembly.objects[part["role"]].toCompound().Center().toTuple() == center


def test_native_negative_axis_frame_matches_space_world_feature():
    from buratino.machining_dimensions import groove_dimensions

    space = _grooved_space_part()
    native = {
        "stock_mm": space["stock_mm"],
        "local_frame": {
            "origin_mm": (141, -49, 77),
            "length_axis": (0, 1, 0),
            "width_axis": (0, 0, 1),
            "thickness_axis": (-1, 0, 0),
        },
        "operations": [
            {
                "id": space["operations"][0]["id"],
                "kind": "pocket",
                "role": "bottom_groove",
                "target": "thickness-",
                "local_profile_mm": [
                    (0, 13, 0),
                    (544, 13, 0),
                    (544, 25, 0),
                    (0, 25, 0),
                ],
                "depth_mm": 6,
                "inward_axis_local": (0, 0, 1),
            }
        ],
    }
    assert groove_dimensions(native) == groove_dimensions(space)


@pytest.mark.parametrize("edge", ["z-", "z+"])
def test_explicit_groove_uses_record_width_and_selected_stock_edge(edge):
    from buratino.machining_dimensions import groove_dimensions

    part = _grooved_space_part()
    cut = part["operations"][0]
    cut.update(input_type="groove", groove={"edge": edge, "width": 18, "offset": 13})
    cut.pop("role")
    cut.update(size_v=18, v=13 if edge == "z-" else 129)
    (feature,) = groove_dimensions(part)
    assert (feature.width_mm, feature.inset_mm, feature.depth_mm) == (18, 13, 6)
    expected_edge = 77 if edge == "z-" else 237
    assert feature.inset_points[0][2] == expected_edge


@pytest.mark.parametrize("direction", [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, 0, -1)])
@pytest.mark.parametrize("rotated", [False, True])
def test_all_feature_vertices_and_dimension_anchors_match_cad_hlr_projection(
    direction, rotated
):
    from buratino.machining_dimensions import groove_dimensions
    from buratino.panel_views import _projected_geometry, _svg_projector

    (feature,) = groove_dimensions(_grooved_space_part())
    points = feature.profile_points + feature.width_points + feature.inset_points
    # Edges exercise HLR's own projection, independently of the point projector.
    wire = cq.Compound.makeCompound(
        [
            cq.Edge.makeLine(a, b)
            for a, b in zip(points, points[1:] + points[:1], strict=True)
            if a != b
        ]
    )
    rotation = direction if rotated else None
    if rotated:
        wire = wire.rotate((0, 0, 0), rotation, 90)
    reference = _projected_geometry(wire, direction)
    bounds = reference.BoundingBox()
    scale, left, top = 0.4, 31, 23
    project = _svg_projector(direction, bounds, scale, left, top, rotation)
    expected = [
        (left + (v.X - bounds.xmin) * scale, top + (bounds.ymax - v.Y) * scale)
        for v in reference.Vertices()
    ]
    for point in points:
        actual = project(point)
        assert any(actual == pytest.approx(value) for value in expected)


def test_mortise_notes_keep_all_centers_and_separate_faces_and_depths():
    from buratino.machining_notes import machining_notes

    cuts = [
        {
            "type": "mortise",
            "id": str(i),
            "face": face,
            "axis": "v",
            "length": 20,
            "width": 6,
            "depth": depth,
            "u": u,
            "v": v,
        }
        for i, (face, depth, u, v) in enumerate(
            [
                ("x+", 12, 9, 60),
                ("x+", 12, 9, 140),
                ("x+", 12, 535, 60),
                ("x+", 12, 535, 140),
                ("x-", 12, 9, 60),
                ("x+", 28, 9, 60),
            ]
        )
    ]
    notes = machining_notes({"operations": cuts})
    assert len(notes) == 3
    assert notes[0] == (
        "Mortises (4): 20 × 6 mm; depth 12 mm; centers U/V (mm): "
        "9/(60, 140); 535/(60, 140); length along V; face x+ (stock XYZ)."
    )
    assert "face x-" in notes[1]
    assert "depth 28 mm" in notes[2]


@pytest.mark.parametrize("name", ["machined-drawer", "attic-clothing-storage"])
def test_real_project_groove_anchors_touch_the_actual_machined_solid(root, name):
    from cabineteer.space_adapter import materialize_box_part

    from buratino.engine import calculate
    from buratino.machining_dimensions import groove_dimensions
    from buratino.project import load_project

    calculation = calculate(load_project(root / "projects" / name))
    part = next(
        part
        for part in calculation.result["parts"]
        if any(cut.get("role") == "bottom_groove" for cut in part.get("operations", []))
    )
    if calculation.native_assembly:
        shape = next(
            item for item in calculation.native_assembly.parts if item.id == part["id"]
        ).solid()
    else:
        shape = materialize_box_part(part).translate(part["transform"]["translation"])
    feature, *rebates = groove_dimensions(part)
    depth = 8 if name == "attic-clothing-storage" else 6
    assert (feature.width_mm, feature.inset_mm, feature.depth_mm) == (12, 13, depth)
    if name == "attic-clothing-storage":
        assert len(rebates) == 1
        assert (rebates[0].width_mm, rebates[0].depth_mm) == (13, 2)
    for point in feature.width_points + feature.inset_points:
        assert shape.val().distance(cq.Vertex.makeVertex(*point)) < 1e-6
    assembly = cq.Assembly(name="root")
    assembly.add(shape, name=part["role"])
    view = panel_views(assembly, [part])[part["id"]]
    assert "G1 width: 12 mm" in view and "G1 inset: 13 mm" in view
    assert f"{depth} mm deep" in view
    if rebates:
        assert "G2 width: 13 mm" in view and "2 mm deep" in view


def test_multiple_grooves_keep_labels_sections_and_leaders_in_separate_rows():
    from copy import deepcopy

    from cabineteer.space_adapter import materialize_box_part

    part = _grooved_space_part()
    second = deepcopy(part["operations"][0])
    second.update(id="user/second", input_type="groove", v=60, size_v=18)
    second.pop("role")
    second["groove"] = {"edge": "z-", "width": 18, "offset": 60}
    part["operations"].append(second)
    shape = materialize_box_part(part).translate(part["transform"]["translation"])
    assembly = cq.Assembly(name="root")
    assembly.add(shape, name=part["role"])
    view = panel_views(assembly, [part])[part["id"]]
    tree = ElementTree.fromstring(view)
    assert tree.attrib["viewBox"] == "0 0 360 475"
    assert "G1 width: 12 mm" in view and "G2 width: 18 mm" in view
    assert "G1 inset: 13 mm" in view and "G2 inset: 60 mm" in view
    for node in tree.iter():
        if node.tag.endswith("text"):
            assert 0 < float(node.attrib["x"]) < 360
            assert 0 < float(node.attrib["y"]) < 475
    leaders = [
        node.attrib["d"]
        for node in tree.iter()
        if node.attrib.get("class") == "dimension-leader"
    ]
    assert "L25.000 360.000" in leaders[2]
    assert "L335.000 360.000" in leaders[3]


def test_under_window_space_joints_group_repeated_sides_without_merging_other_cuts(
    root,
):
    from copy import deepcopy

    from cabineteer.space_adapter import materialize_box_part

    from buratino.engine import calculate
    from buratino.panel_views import panel_groups
    from buratino.project import load_project

    result = calculate(load_project(root / "projects/two-under-window")).result
    parts = [
        part for part in result["parts"] if part["id"].endswith(("/side_L", "/side_R"))
    ]
    assert len(parts) == 8
    assert all(joint["type"] == "space_domino" for joint in result["joints"])
    variant = deepcopy(parts[0])
    variant["id"] = variant["role"] = "narrower-bottom-groove"
    groove = next(
        cut for cut in variant["operations"] if cut.get("role") == "bottom_groove"
    )
    groove["size_v"] = 10
    parts.append(variant)
    assembly = cq.Assembly(name="root")
    for part in parts:
        shape = materialize_box_part(part).translate(part["transform"]["translation"])
        assembly.add(shape, name=part["role"])
    groups = panel_groups(assembly, parts, result["joints"])
    assert sorted(len(group) for group in groups) == [1, 4, 4]
    assert {
        tuple(part["id"].rsplit("/", 1)[-1] for part in group) for group in groups
    } == {
        ("side_L",) * 4,
        ("side_R",) * 4,
        ("narrower-bottom-groove",),
    }


@pytest.mark.parametrize("mirrored", [False, True])
@pytest.mark.parametrize("rotated", [False, True])
def test_groove_leaders_follow_screen_order_and_keep_their_values(mirrored, rotated):
    import re

    from buratino.machining_dimensions import groove_callouts, groove_dimensions

    (feature,) = groove_dimensions(_grooved_space_part())

    def project(point):
        # Both views put width on the opposite side after mirroring/rotation.
        u, v = point[1] + 49, point[2] - 77
        x, y = (u, v) if not rotated else (v, u)
        if mirrored:
            x = -x
        return 180 + x * 0.2, 90 + y * 0.1

    drawing = ElementTree.fromstring(
        "<svg>" + groove_callouts([feature], project) + "</svg>"
    )
    leaders = [
        node.attrib["d"]
        for node in drawing.iter()
        if node.attrib.get("class") == "dimension-leader"
    ]
    paths = [
        [float(value) for value in re.findall(r"-?\d+\.\d+", path)] for path in leaders
    ]
    left, right = paths
    assert (left[0], left[1]) <= (right[0], right[1])
    assert left[2] == 25 and left[-2] == 70
    assert right[2] == 335 and right[-2] == 250
    # Each first leader segment moves outwards, so their horizontal ranges do
    # not overlap inside the panel. Old fixed width/inset routing fails here.
    assert left[2] < left[0] <= right[0] < right[2]
    labels = {
        node.text: float(node.attrib["x"])
        for node in drawing.iter()
        if node.tag == "text"
    }
    width_mid = tuple(
        sum(p[i] for p in map(project, feature.width_points)) / 2 for i in range(2)
    )
    inset_mid = tuple(
        sum(p[i] for p in map(project, feature.inset_points)) / 2 for i in range(2)
    )
    expected_width_x = 70 if width_mid < inset_mid else 250
    assert labels["G1 width: 12 mm"] == expected_width_x
    assert labels["G1 inset: 13 mm"] == 320 - expected_width_x


@pytest.mark.parametrize("face", ["x+", "y-"])
def test_mortises_have_strong_cad_outlines_without_extra_layouts(face):
    from cabineteer.space_adapter import materialize_box_part

    part = _grooved_space_part()
    part["operations"] = [
        {
            "id": "mortise",
            "type": "mortise",
            "face": face,
            "u": 60 if face == "x+" else 9,
            "v": 60,
            "axis": "v",
            "length": 20,
            "width": 6,
            "depth": 12 if face == "x+" else 28,
        }
    ]
    assembly = cq.Assembly(name="root")
    assembly.add(materialize_box_part(part), name=part["role"])
    view = panel_views(assembly, [part])[part["id"]]
    root = ElementTree.fromstring(view)
    ns = {"s": "http://www.w3.org/2000/svg"}
    outline = root.find('.//s:g[@class="machining-outline"]', ns)
    assert outline is not None
    assert outline.attrib["stroke"] == "#75400d"
    assert outline.attrib["stroke-dasharray"] == "none"
    assert len(outline.findall("s:path", ns)) > 0
    assert root.attrib["viewBox"] == "0 0 360 255"
    assert "PANEL EDGE" not in view and "PANEL FACE" not in view
    assert "stock-face layout" not in view.lower()
