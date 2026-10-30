from copy import deepcopy
from xml.etree import ElementTree as ET

import cadquery as cq
import pytest
from cabineteer.space_adapter import materialize_box_part

from buratino.mortise_views import mortise_faces
from buratino.panel_views import panel_views

NS = {"s": "http://www.w3.org/2000/svg"}


def _part(face="x+", thickness_axis=0, slot_axis="u"):
    size = [120, 96, 80]
    size[thickness_axis] = 18
    normal = "xyz".index(face[0])
    uv = [i for i in range(3) if i != normal]
    return {
        "id": "panel",
        "role": "panel",
        "profile": {"type": "box", "size": size},
        "stock": {"dimensions": size, "thickness_axis": thickness_axis},
        "stock_mm": {"length": max(size), "width": sorted(size)[1], "thickness": 18},
        "blank_mm": {"length": max(size), "width": sorted(size)[1], "thickness": 18},
        "transform": {
            "translation": [123, -49, 77],
            "axes": [[0, 1, 0], [-1, 0, 0], [0, 0, 1]],
        },
        "operations": [
            {
                "id": "cut",
                "type": "mortise",
                "face": face,
                "u": size[uv[0]] / 2,
                "v": size[uv[1]] / 2,
                "axis": slot_axis,
                "length": 20,
                "width": 6,
                "depth": 12 if normal == thickness_axis else 28,
            }
        ],
    }


@pytest.mark.parametrize("face", ["x-", "x+", "y-", "y+", "z-", "z+"])
@pytest.mark.parametrize("broad", [False, True])
def test_signed_mortise_planes_and_rims_match_rotated_translated_cad(face, broad):
    normal = "xyz".index(face[0])
    thickness = normal if broad else (normal + 1) % 3
    # The long slot must fit on the selected edge as well as on a broad face.
    uv = [i for i in range(3) if i != normal]
    axis = "v" if uv[0] == thickness else "u"
    part = _part(face, thickness, axis)
    before = deepcopy(part)
    (feature,) = mortise_faces(part)
    assert ("PANEL FACE" if broad else "PANEL EDGE") in feature.label
    assert ("max" if face[1] == "+" else "min") in feature.label
    assert feature.axes == tuple("XYZ"[i] for i in uv)
    assert feature.size == tuple(part["profile"]["size"][i] for i in uv)
    shape = (
        materialize_box_part(part)
        .rotate((0, 0, 0), (0, 0, 1), 90)
        .translate(part["transform"]["translation"])
        .val()
    )
    # Every displayed capsule rim anchor is on the real mouth of the cut.
    for rim in feature.rims_world:
        for point in rim:
            assert shape.distance(cq.Vertex.makeVertex(*point)) < 1e-6
    (center,) = feature.centers_world
    assert shape.distance(cq.Vertex.makeVertex(*center)) == pytest.approx(3)
    cut = part["operations"][0]
    floor = tuple(
        c + cut["depth"] * n for c, n in zip(center, feature.inward_world, strict=True)
    )
    assert shape.distance(cq.Vertex.makeVertex(*floor)) < 1e-6
    assert part == before


def test_native_frame_uses_recorded_lwt_mortises_without_inventing_profile_cuts():
    part = _part("z-", 2)
    part["local_frame"] = {
        "origin_mm": (141, -49, 77),
        "length_axis": (0, 1, 0),
        "width_axis": (0, 0, 1),
        "thickness_axis": (1, 0, 0),
    }
    (feature,) = mortise_faces(part)
    assert feature.axes == ("L", "W")
    assert feature.centers_world == ((141, 11, 125),)
    assert feature.inward_world == (1, 0, 0)
    assert "PANEL FACE · T min" in feature.label
    part["operations"] = [{"kind": "pocket", "local_profile_mm": [(0, 0, 0)]}]
    assert mortise_faces(part) == []


@pytest.mark.parametrize(
    "face,thickness,axis", [("x+", 0, "u"), ("x-", 2, "u"), ("x+", 1, "v")]
)
def test_layout_shows_actual_face_aspect_slots_datums_and_unclipped_dimensions(
    face,
    thickness,
    axis,
):
    part = _part(face, thickness, axis)
    # This assertion needs the actual CAD overview in the same returned SVG.
    assembly = cq.Assembly(name="root")
    assembly.add(materialize_box_part(part), name=part["role"])
    view = panel_views(assembly, [part])[part["id"]]
    root = ET.fromstring(view)
    layout = root.find('.//s:g[@class="mortise-stock-layout"]', NS)
    assert layout is not None
    assert layout.attrib["data-face"] == face
    assert "CAD overview · modeled solid" in view
    assert "Stock-face layout" in view
    assert "U=0 / V=0 at stock min edges" in view
    assert "Centre stations from datum (U/V)" in view
    assert "20 × 6" in view
    assert ("12 mm deep" if thickness == 0 else "28 mm deep") in view
    stock = layout.find('s:rect[@class="stock-face"]', NS)
    rim = layout.find('s:rect[@class="mortise-rim"]', NS)
    (feature,) = mortise_faces(part)
    assert float(stock.attrib["width"]) / float(
        stock.attrib["height"]
    ) == pytest.approx(max(feature.size) / min(feature.size), abs=0.001)
    assert rim.attrib["fill"] == "#ffc66d"
    assert float(rim.attrib["stroke-width"]) >= 1.5
    assert layout.find('s:path[@class="mortise-center"]', NS) is not None
    for dimension in ("x", "y"):
        length = {"x": "width", "y": "height"}[dimension]
        assert float(rim.attrib[dimension]) >= float(stock.attrib[dimension])
        assert (
            float(rim.attrib[dimension]) + float(rim.attrib[length])
            <= float(stock.attrib[dimension]) + float(stock.attrib[length]) + 0.002
        )
    viewport_height = float(root.attrib["viewBox"].split()[3])
    assert float(root.attrib["height"]) == viewport_height
    for label in layout.findall("s:text", NS):
        assert 0 <= float(label.attrib["x"]) <= 360
        assert 0 <= float(label.attrib["y"]) <= viewport_height - 5
        assert float(label.attrib["font-size"]) >= 11


def test_mortise_layouts_stay_equal_for_translated_copies_and_changed_ids():
    part = _part("x-", 2)
    copied = deepcopy(part)
    copied.update(id="copy", role="copy")
    copied["transform"]["translation"] = (600, 99, -200)
    copied["operations"][0]["id"] = "other-operation-id"
    assembly = cq.Assembly(name="root")
    shape = materialize_box_part(part)
    assembly.add(shape, name=part["role"])
    assembly.add(shape.translate((600, 99, -200)), name=copied["role"])
    views = panel_views(assembly, [part, copied])
    layouts = [
        ET.tostring(
            ET.fromstring(view).find('.//s:g[@class="mortise-stock-layout"]', NS)
        )
        for view in views.values()
    ]
    assert layouts[0] == layouts[1]


def test_classification_requires_stock_thickness_axis_instead_of_smallest_size():
    part = _part("x+", 0)
    part["stock"]["dimensions"][2] = 12
    assert "PANEL FACE" in mortise_faces(part)[0].label
    del part["stock"]["thickness_axis"]
    assert mortise_faces(part) == []


def test_repeated_rows_keep_exact_centres_and_compact_notes():
    from buratino.machining_notes import machining_notes
    from buratino.mortise_views import _center_rows

    part = _part("x+", 0)
    part["profile"]["size"] = [18, 554, 679]
    part["stock"]["dimensions"] = [18, 554, 679]
    prototype = part["operations"][0]
    part["operations"] = [
        dict(prototype, id=f"{u}/{v}", u=u, v=v)
        for u in (70, 152, 234, 316, 398, 480)
        for v in (9, 670)
    ]
    part["operations"].append(dict(prototype, id="rail", u=25, v=339))
    assert _center_rows(part["operations"]) == [
        "V = 9, 670",
        "U = 70, 152, 234, 316, 398, 480",
        "V = 339",
        "U = 25",
    ]
    (note,) = machining_notes(part, mortise_layout_available=True)
    assert "Mortises (13)" in note and "PANEL FACE" in note
    assert "See stock-face layout for centres." in note
    assert "70, 152" not in note


def test_report_css_preserves_stock_layout_colours_and_plain_overview_background():
    from buratino.build import _page
    from buratino.mortise_views import mortise_layouts

    layouts, _ = mortise_layouts(_part(), 0)
    page = _page(
        "Machining", '<figure class="panel-drawing"><svg>' + layouts + "</svg></figure>"
    )
    assert ".panel-drawing svg rect{fill:" not in page
    assert (
        ".panel-drawing svg rect:not(.stock-face):not(.mortise-rim)"
        "{fill:#fff;stroke:#333}"
    ) in page
    assert 'fill="#ffc66d" stroke="#8c3600"' in page
    assert 'fill="#f2f5f7" stroke="#465c68"' in page


@pytest.mark.parametrize("layout", [None, "cad-only", "stock-layout"])
def test_report_keeps_mortise_centres_unless_a_stock_layout_is_actually_supplied(
    root,
    tmp_path,
    layout,
):
    from buratino.build import render_documents
    from buratino.engine import calculate
    from buratino.mortise_views import mortise_layouts
    from buratino.project import load_project

    result = calculate(load_project(root / "projects/two-under-window")).result
    part = next(p for p in result["parts"] if p["id"].endswith("/box-lower/side_L"))
    views = None
    if layout:
        content = mortise_layouts(part, 0)[0] if layout == "stock-layout" else "<path/>"
        views = {part["id"]: "<svg>" + content + "</svg>"}
    render_documents(tmp_path, result, panel_views=views)
    for filename in ("report.html", "assembly.html"):
        document = (tmp_path / filename).read_text()
        assert "centers U/V (mm)" in document
        if layout == "stock-layout":
            assert document.count("See stock-face layout for centres.") == 1
            assert "Centre stations from datum (U/V)" in document
        else:
            assert "See stock-face layout for centres." not in document
            assert "Panel view unavailable." in document
