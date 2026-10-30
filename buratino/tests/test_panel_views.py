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
