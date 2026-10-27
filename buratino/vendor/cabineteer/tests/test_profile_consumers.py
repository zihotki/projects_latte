"""Exercise the saved native project through its existing MCP consumers."""

import asyncio
import json
import runpy
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "name,count", [("profile-row-sloped", 27), ("profile-row-transition", 28)]
)
def test_native_project_consumers(monkeypatch, tmp_path, name, count):
    from cabineteer import server
    from cabineteer.project import project_to_dict

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    root = Path(__file__).resolve().parents[3]
    project = runpy.run_path(str(root / "projects" / name / "project.py"))["project"]
    payload = json.loads(json.dumps(project_to_dict(project)))

    async def call(handler, args):
        return json.loads((await handler(args))[0].text)

    async def run():
        designed = await call(server._tool_design_project, payload)
        loaded = await call(server._tool_load_project, {"name": name})
        evaluated = await call(server._tool_evaluate_project, {"project_name": name})
        cutlist = await call(
            server._tool_generate_project_cutlist, {"project_name": name}
        )
        viewer = await call(
            server._tool_visualize_project,
            {"project_name": name, "open_browser": False, "output_dir": str(tmp_path)},
        )
        expected = designed["assembly"]
        assert len(expected["parts"]) == count
        assert (
            expected["hardware"][0]["slide_key"]
            == "buratino_hettich_quadro_v6_eb20_480"
        )
        assert expected["hardware"][0]["status"] == "unverified"
        lower = next(
            p for p in expected["parts"] if p["id"] == "lower.carcass.side_left"
        )
        assert lower["geometry"]["vertices_mm"]
        assert lower["geometry"]["triangles"]
        for actual in (
            loaded["assembly"],
            evaluated["assembly"],
            cutlist["assembly"],
            viewer["assembly"],
        ):
            assert actual == expected
        assert loaded["project"]["layout"] == payload["layout"]
        assert loaded["project"]["profile_assembly"] == payload["profile_assembly"]
        assert Path(cutlist["files"]["csv"]).is_file()
        assert Path(viewer["glb"]).is_file()
        assert evaluated["issues"] == []
        assert_rendered_profiles(Path(viewer["glb"]), project.resolved_assembly())
        assert any(p["operations"] for p in expected["parts"])

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(run())
    finally:
        loop.close()


def assert_rendered_profiles(glb_path, assembly):
    """Compare exported vertices against each native world-space profile."""
    import struct

    from cabineteer.profiles import ProfilePart

    data = glb_path.read_bytes()
    json_size, _ = struct.unpack_from("<II", data, 12)
    document = json.loads(data[20 : 20 + json_size])
    binary_offset = 20 + json_size + 8
    root = document["nodes"][document["scenes"][0]["nodes"][0]]
    assert root["rotation"] == pytest.approx([-(2**-0.5), 0, 0, 2**-0.5])
    nodes = {node.get("name"): node for node in document["nodes"]}
    for part in assembly.parts:
        node = nodes[part.id]
        assert set(node) == {"name", "children"}
        mesh_node = document["nodes"][node["children"][0]]
        assert set(mesh_node) == {"name", "mesh"}
        mesh = document["meshes"][mesh_node["mesh"]]
        actual = set()
        actual_triangles = set()
        for primitive in mesh["primitives"]:
            assert primitive.get("mode", 4) == 4, part.id
            accessor = document["accessors"][primitive["attributes"]["POSITION"]]
            view = document["bufferViews"][accessor["bufferView"]]
            offset = (
                binary_offset
                + view.get("byteOffset", 0)
                + accessor.get("byteOffset", 0)
            )
            stride = view.get("byteStride", 12)
            vertices = [
                tuple(
                    round(x, 2)
                    for x in struct.unpack_from("<fff", data, offset + i * stride)
                )
                for i in range(accessor["count"])
            ]
            actual.update(vertices)
            indices = document["accessors"][primitive["indices"]]
            index_view = document["bufferViews"][indices["bufferView"]]
            index_offset = (
                binary_offset
                + index_view.get("byteOffset", 0)
                + indices.get("byteOffset", 0)
            )
            code = {5121: "B", 5123: "H", 5125: "I"}[indices["componentType"]]
            values = struct.unpack_from(
                f"<{indices['count']}{code}", data, index_offset
            )
            for i in range(0, len(values), 3):
                actual_triangles.add(
                    tuple(sorted(vertices[index] for index in values[i : i + 3]))
                )
        if isinstance(part, ProfilePart):
            x0, y0, z0 = part.world_offset_mm
            expected = {
                (round(x + x0, 2), round(y + y0, 2), round(z + z0, 2))
                for x, z in part.profile_xz_mm
                for y in (part.y_mm, part.y_mm + part.extrusion_mm)
            }
        else:
            expected = {
                tuple(round(v, 2) for v in vertex.Center().toTuple())
                for vertex in part.solid().val().Vertices()
            }
        vertices, triangles = part.solid().val().tessellate(0.1, 0.1)
        expected_triangles = {
            tuple(
                sorted(
                    tuple(round(v, 2) for v in vertices[index].toTuple())
                    for index in triangle
                )
            )
            for triangle in triangles
        }
        assert actual_triangles == expected_triangles, part.id
        assert expected <= actual, part.id
        for axis in range(3):
            assert min(p[axis] for p in actual) == pytest.approx(
                min(p[axis] for p in expected), abs=0.01
            ), part.id
            assert max(p[axis] for p in actual) == pytest.approx(
                max(p[axis] for p in expected), abs=0.01
            ), part.id


def test_rendered_bounded_kink(tmp_path):
    import cadquery as cq
    from cabineteer.layout import Frame, LayoutLeaf, Row, Stack
    from cabineteer.profiles import ProfiledBox, RoofProfile, resolve_profile_assembly
    from cabineteer.visualize import visualize_assembly

    frame = Frame("frame.support", 1440, 380, 50, 18)
    layout = Stack(
        "stack",
        (
            LayoutLeaf("lower", 1440, 550, 720),
            frame,
            Row(
                "upper",
                (
                    LayoutLeaf("upper.left", 720, 420, 1204),
                    LayoutLeaf("upper.right", 720, 420, 1204),
                ),
            ),
        ),
    )
    boxes = (
        ProfiledBox("upper.left", 0, 720, 420, 18, 18, 6),
        ProfiledBox("upper.right", 720, 720, 420, 18, 18, 6),
    )
    native = resolve_profile_assembly(
        layout,
        RoofProfile(((0, 235), (1071, 1204), (1440, 1204)), 18),
        boxes,
        "roof",
        ("slope", "level"),
        frame,
    )
    assembly = cq.Assembly(name="bounded_kink")
    for part in native.parts:
        assembly.add(part.solid(), name=part.id)
    result = visualize_assembly(
        assembly,
        list(native.parts),
        output_dir=tmp_path,
        name="bounded_kink",
        open_browser=False,
    )
    assert_rendered_profiles(Path(result["glb"]), native)


@pytest.mark.parametrize("name", ["profile-row-sloped", "profile-row-transition"])
def test_shared_upper_geometry_and_roundtrip(name):
    from dataclasses import replace

    from cabineteer.profiles import (
        evaluate_assembly,
        profile_spec_from_dict,
        profile_spec_to_dict,
        resolved_profile_spec,
    )

    root = Path(__file__).resolve().parents[3]
    project = runpy.run_path(str(root / "projects" / name / "project.py"))["project"]
    spec = project.profile_assembly
    assert profile_spec_from_dict(profile_spec_to_dict(spec)) == spec
    legacy = profile_spec_to_dict(spec)
    del legacy["shared_owner"]
    del legacy["roof_joint"]
    assert profile_spec_from_dict(legacy).shared_owner is None
    assert profile_spec_from_dict(legacy).roof_joint is None
    assert resolved_profile_spec(replace(spec, roof_joint=None)).roof == spec.roof
    assembly = project.resolved_assembly()
    upper = [p for p in assembly.parts if p.owner == "upper"]
    divider = next(p for p in upper if p.id == "upper.divider")
    assert {x for x, _ in divider.profile_xz_mm} == {351, 369}
    assert sorted(p.stock_mm[0] for p in upper if p.component == "bottom") == [333, 333]
    sides = [p for p in upper if p.component in ("side_left", "side_right", "divider")]
    assert len(sides) == 3
    assert evaluate_assembly(assembly) == []
    for i, side in enumerate(sides):
        for other in sides[i + 1 :]:
            assert side.solid().intersect(other.solid()).val().Volume() < 0.01
    caps = [p for p in assembly.parts if p.component == "cap"]
    for cap in caps:
        assert divider.solid().val().distance(cap.solid().val()) < 0.01
        assert divider.solid().intersect(cap.solid()).val().Volume() < 0.01
    bottoms = [p for p in upper if p.component == "bottom"]
    for bottom in bottoms:
        assert bottom.solid().val().distance(divider.solid().val()) < 0.01
        assert bottom.solid().intersect(divider.solid()).val().Volume() < 0.01
    doors = sorted(
        (p for p in upper if p.component == "door"), key=lambda p: p.profile_xz_mm[0][0]
    )
    assert [(p.profile_xz_mm[0][0], p.profile_xz_mm[1][0]) for p in doors] == [
        (2, 359),
        (361, 718),
    ]
    assert all(p.owner == "upper" for p in doors)
    if name.endswith("transition"):
        assert divider.profile_xz_mm == ((351, 0), (369, 0), (369, 582), (351, 582))
        assert divider.stock_mm == (582, 414, 18)
        assert divider.operations == ()
        slope, level = caps
        assert slope.profile_xz_mm[1] == (351, 600)
        assert level.profile_xz_mm[:2] == ((351, 600), (720, 600))
        assert level.stock_mm == (369, 414, 18)
        assert slope.stock_mm[0] == pytest.approx(
            (351**2 + 300**2) ** 0.5 + 18 * 300 / 351
        )
        assert slope.solid().val().distance(level.solid().val()) < 0.01
        assert slope.solid().intersect(level.solid()).val().Volume() < 0.01
        # The offset lines meet inside the left door, beyond the cap joint.
        assert len(doors[0].profile_xz_mm) == 5
        kink = doors[0].profile_xz_mm[3]
        slope_value = 300 / 351
        expected_x = 351 + 2 * (slope_value / (1 + slope_value**2) ** 0.5) / (
            1 + (1 + slope_value**2) ** -0.5
        )
        assert kink[0] == pytest.approx(expected_x)
        assert kink[1] == pytest.approx(598)


def test_shared_transition_without_faces_exports_flat_divider():
    from dataclasses import replace

    from cabineteer.profiles import assembly_records, evaluate_assembly

    root = Path(__file__).resolve().parents[3]
    project = runpy.run_path(
        str(root / "projects" / "profile-row-transition" / "project.py")
    )["project"]
    project = replace(
        project, profile_assembly=replace(project.profile_assembly, faces=None)
    )
    assembly = project.resolved_assembly()
    divider = next(p for p in assembly.parts if p.id == "upper.divider")
    record = next(
        p for p in assembly_records(assembly)["parts"] if p["id"] == divider.id
    )
    assert divider.profile_xz_mm == ((351, 0), (369, 0), (369, 582), (351, 582))
    assert record["operations"] == []
    assert record["stock_mm"]["thickness"] == 18
    assert evaluate_assembly(assembly) == []
