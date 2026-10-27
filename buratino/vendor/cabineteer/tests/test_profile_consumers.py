"""Exercise the saved native project through its existing MCP consumers."""

import asyncio
import json
import runpy
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "name,count", [("profile-row-sloped", 28), ("profile-row-transition", 29)]
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
        for primitive in mesh["primitives"]:
            accessor = document["accessors"][primitive["attributes"]["POSITION"]]
            view = document["bufferViews"][accessor["bufferView"]]
            offset = (
                binary_offset
                + view.get("byteOffset", 0)
                + accessor.get("byteOffset", 0)
            )
            stride = view.get("byteStride", 12)
            for i in range(accessor["count"]):
                actual.add(
                    tuple(
                        round(x, 2)
                        for x in struct.unpack_from("<fff", data, offset + i * stride)
                    )
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
