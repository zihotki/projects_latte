"""Fresh CAD and GLB checks for the authored coordinate contract."""

from __future__ import annotations

import json
import math
import struct
from dataclasses import replace

import pytest

from buratino.engine import calculate, make_geometry
from buratino.project import load_project


def _read_glb(path):
    data = path.read_bytes()
    magic, version, length = struct.unpack_from("<4sII", data)
    assert (magic, version, length) == (b"glTF", 2, len(data))
    json_length, json_type = struct.unpack_from("<II", data, 12)
    assert json_type == 0x4E4F534A
    document = json.loads(data[20 : 20 + json_length].decode("utf-8").rstrip())
    binary_header = 20 + json_length
    binary_length, binary_type = struct.unpack_from("<II", data, binary_header)
    assert binary_type == 0x004E4942
    binary = data[binary_header + 8 : binary_header + 8 + binary_length]
    return document, binary


def _accessor(document, binary, index):
    accessor = document["accessors"][index]
    view = document["bufferViews"][accessor["bufferView"]]
    formats = {5121: "B", 5123: "H", 5125: "I", 5126: "f"}
    components = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
    item_format = formats[accessor["componentType"]]
    item_size = struct.calcsize("<" + item_format)
    width = components[accessor["type"]]
    stride = view.get("byteStride", item_size * width)
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    return [
        struct.unpack_from("<" + item_format * width, binary, start + i * stride)
        for i in range(accessor["count"])
    ]


def _apply_node(point, node):
    if "matrix" in node:
        matrix = node["matrix"]
        x, y, z = point
        return (
            matrix[0] * x + matrix[4] * y + matrix[8] * z + matrix[12],
            matrix[1] * x + matrix[5] * y + matrix[9] * z + matrix[13],
            matrix[2] * x + matrix[6] * y + matrix[10] * z + matrix[14],
        )

    scale = node.get("scale", (1, 1, 1))
    x, y, z = (point[i] * scale[i] for i in range(3))
    qx, qy, qz, qw = node.get("rotation", (0, 0, 0, 1))
    uv = (qy * z - qz * y, qz * x - qx * z, qx * y - qy * x)
    uuv = (qy * uv[2] - qz * uv[1], qz * uv[0] - qx * uv[2], qx * uv[1] - qy * uv[0])
    translation = node.get("translation", (0, 0, 0))
    return tuple(
        point + 2 * (qw * cross + double_cross) + translation[i]
        for i, (point, cross, double_cross) in enumerate(
            zip((x, y, z), uv, uuv, strict=False)
        )
    )


def _exported_part_triangles(path, part_id):
    document, binary = _read_glb(path)
    roots = document["scenes"][document.get("scene", 0)]["nodes"]
    assert len(roots) == 1
    root_index = roots[0]
    root = document["nodes"][root_index]
    half = math.sqrt(0.5)
    assert root.get("rotation") == pytest.approx([-half, 0, 0, half])
    assert root.get("translation", [0, 0, 0]) == pytest.approx([0, 0, 0])
    assert root.get("scale", [1, 1, 1]) == pytest.approx([1, 1, 1])

    matches = []
    triangles = []

    def visit(index, node_path, selected=False):
        node = document["nodes"][index]
        current_path = (*node_path, node)
        selected = selected or node.get("name") == part_id
        if node.get("name") == part_id:
            matches.append(index)
        if selected and "mesh" in node:
            mesh = document["meshes"][node["mesh"]]
            for primitive in mesh["primitives"]:
                assert primitive.get("mode", 4) == 4
                positions = _accessor(
                    document, binary, primitive["attributes"]["POSITION"]
                )
                indices = (
                    _accessor(document, binary, primitive["indices"])
                    if "indices" in primitive
                    else [(i,) for i in range(len(positions))]
                )
                flat_indices = [item[0] for item in indices]
                points = []
                for position in positions:
                    transformed = tuple(position)
                    for transform in reversed(current_path):
                        transformed = _apply_node(transformed, transform)
                    # CadQuery's root maps CAD (x,y,z) to GLTF (x,z,-y).
                    points.append((transformed[0], -transformed[2], transformed[1]))
                triangles.extend(
                    tuple(points[flat_indices[i + j]] for j in range(3))
                    for i in range(0, len(flat_indices), 3)
                )
        for child in node.get("children", ()):
            visit(child, current_path, selected)

    for root_index in roots:
        visit(root_index, ())
    assert len(matches) == 1, f"expected one named GLB node for {part_id}"
    assert triangles, f"expected triangle geometry under GLB node {part_id}"
    return triangles


def _triangle_bounds(triangles):
    points = [point for triangle in triangles for point in triangle]
    return tuple(min(point[axis] for point in points) for axis in range(3)) + tuple(
        max(point[axis] for point in points) for axis in range(3)
    )


def _assert_bounds(actual, bounds):
    expected = (*bounds[0], *bounds[1])
    assert actual == pytest.approx(expected, abs=0.02, rel=0)


def _cad_bounds(shape):
    bounds = shape.val().BoundingBox()
    return (
        bounds.xmin,
        bounds.ymin,
        bounds.zmin,
        bounds.xmax,
        bounds.ymax,
        bounds.zmax,
    )


def test_nested_space_report_cad_and_glb_share_stock_frame(root, tmp_path):
    from cabineteer.edge_banding import EdgeBand
    from cabineteer.operations import Pocket
    from cabineteer.part_grain import PartGrain

    project = load_project(root / "projects/space-nested-inserts")
    target_id = (
        "/cabinet/host-root/bare-slot/bare-insert-instance/insert-root/"
        "drawer-space/insert-box/side_L"
    )
    plan = project.native_project.resolved_space_assembly()
    original = next(part for part in plan.part_plan.parts if part["id"] == target_id)
    assert original["origin"] == [32, 2, 58]
    second_nested_id = (
        "/cabinet/host-root/complete-slot/complete-cabinet-instance/"
        "complete-row/cabinet/carcass/side_left"
    )
    second_nested = next(
        part for part in plan.part_plan.parts if part["id"] == second_nested_id
    )
    assert second_nested["origin"] == [328, 20, 28]
    dimensions = original["profile"]["size"]
    assert len(set(dimensions)) == 3
    assert all(value != 0 for value in original["origin"])
    assert dimensions[1] > 30 and dimensions[2] > 30

    pocket_width = 12
    pocket = Pocket(
        "coordinate-check",
        target_id,
        "x+",
        (dimensions[1] - pocket_width) / 2,
        (dimensions[2] - pocket_width) / 2,
        pocket_width,
        pocket_width,
        2,
    )
    native = replace(
        project.native_project,
        operations=(pocket,),
        edge_banding=(EdgeBand("front-edge", target_id, "y-"),),
        part_grain=(PartGrain("grain", target_id, "z"),),
    )
    calculation = calculate(replace(project, native_project=native))
    record = next(
        part for part in calculation.result["parts"] if part["id"] == target_id
    )
    assert record["origin"] == original["origin"]
    assert record["transform"]["translation"] == original["origin"]
    assert record["operations"][0]["face"] == "x+"
    assert record["grain_axis_local"] == "z"
    assert record["surface_normal_axis_local"] == "x"
    assert record["edge_banding"][0]["edge"] == "y-"

    assembly, _ = make_geometry(calculation)
    shape = calculation.space_shapes[target_id]
    _assert_bounds(_cad_bounds(shape), record["bounds"])
    from cabineteer.visualize import export_glb

    output = export_glb(assembly, tmp_path / "nested-space.glb")
    triangles = _exported_part_triangles(output, target_id)
    _assert_bounds(_triangle_bounds(triangles), record["bounds"])

    # The actual exported mesh must retain both broad-face planes used by the
    # stock-frame grain normal, even after a local face pocket and edge band.
    normal_axis = "xyz".index(record["surface_normal_axis_local"])
    grain_axis = "xyz".index(record["grain_axis_local"])
    assert normal_axis != grain_axis
    origin = record["origin"]
    stock_size = record["stock"]["dimensions"]
    for plane in (origin[normal_axis], origin[normal_axis] + stock_size[normal_axis]):
        face_area = 0.0
        for triangle in triangles:
            a, b, c = triangle
            ab = tuple(b[i] - a[i] for i in range(3))
            ac = tuple(c[i] - a[i] for i in range(3))
            cross = (
                ab[1] * ac[2] - ab[2] * ac[1],
                ab[2] * ac[0] - ab[0] * ac[2],
                ab[0] * ac[1] - ab[1] * ac[0],
            )
            magnitude = math.sqrt(sum(value * value for value in cross))
            if magnitude <= 1e-8 or abs(cross[normal_axis]) / magnitude < 0.9999:
                continue
            if all(abs(point[normal_axis] - plane) < 0.02 for point in triangle):
                face_area += magnitude / 2
        assert face_area > 1, f"missing broad grain face at {plane} mm"


@pytest.mark.parametrize("part_id", ["upper.side_left", "roof.cap.slope"])
def test_sloped_profile_record_cad_and_glb_share_local_frame(root, tmp_path, part_id):
    project = load_project(root / "projects/profile-row-drawers")
    calculation = calculate(project)
    record = next(part for part in calculation.result["parts"] if part["id"] == part_id)
    native_part = next(
        part for part in calculation.native_assembly.parts if part.id == part_id
    )
    frame = record["local_frame"]
    assert frame["origin_mm"][1] != 0 and frame["origin_mm"][2] != 0
    if part_id == "roof.cap.slope":
        assert frame["length_axis"][0] != 0 and frame["length_axis"][2] != 0
        assert frame["thickness_axis"][0] != 0 and frame["thickness_axis"][2] != 0

    axes = (frame["length_axis"], frame["width_axis"], frame["thickness_axis"])
    origin = frame["origin_mm"]
    extrusion = record["extrusion_mm"]
    world_points = []
    for profile_point in record["profile_mm"]:
        for extra in (0, 1):
            local = tuple(
                profile_point[axis] + (extrusion[axis] if extra else 0)
                for axis in range(3)
            )
            world_points.append(
                tuple(
                    origin[world_axis]
                    + sum(local[axis] * axes[axis][world_axis] for axis in range(3))
                    for world_axis in range(3)
                )
            )
    expected = [
        [min(point[axis] for point in world_points) for axis in range(3)],
        [max(point[axis] for point in world_points) for axis in range(3)],
    ]

    assembly, _ = make_geometry(calculation)
    _assert_bounds(_cad_bounds(native_part.solid()), expected)
    from cabineteer.visualize import export_glb

    output = export_glb(assembly, tmp_path / "sloped-profile.glb")
    triangles = _exported_part_triangles(output, part_id)
    _assert_bounds(_triangle_bounds(triangles), expected)
