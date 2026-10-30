import asyncio
import json
import struct

import cadquery as cq
import pytest

from cabineteer.edge_banding import EdgeBand, make_view_assembly
from cabineteer.project import (
    CabinetProject,
    SpaceModelSpec,
    apply_project_patch,
    build_project,
    project_from_dict,
    project_to_dict,
)
from cabineteer.space_adapter import materialize_model
from cabineteer.spaces import Carcass, Space


def _project(edge_banding=(), operations=()):
    return CabinetProject(
        name="edge-test",
        space_model=SpaceModelSpec(
            carcass=Carcass(
                width=300,
                height=400,
                depth=280,
                side_thickness=18,
                bottom_thickness=18,
                top_thickness=18,
                back_thickness=6,
            ),
            root=Space("root"),
        ),
        operations=operations,
        edge_banding=edge_banding,
    )


def _read_glb_json(path):
    raw = path.read_bytes()
    assert raw[:4] == b"glTF"
    _, _, total = struct.unpack_from("<4sII", raw)
    assert total == len(raw)
    size, kind = struct.unpack_from("<I4s", raw, 12)
    assert kind == b"JSON"
    return json.loads(raw[20 : 20 + size])


def test_edge_band_tag_round_trip_and_whole_block_update():
    band = EdgeBand("front", "/cabinet/carcass/side_left", "y-")
    project = _project((band,))
    encoded = project_to_dict(project)
    assert encoded["edge_banding"] == [
        {
            "type": "EdgeBand",
            "id": "front",
            "part_id": "/cabinet/carcass/side_left",
            "edge": "y-",
            "color": "#b78b5b",
        }
    ]
    assert project_to_dict(project_from_dict(encoded)) == encoded
    replaced, changes = apply_project_patch(
        encoded,
        {
            "edge_banding": [
                {
                    "type": "EdgeBand",
                    "id": "rear",
                    "part_id": "/cabinet/carcass/side_left",
                    "edge": "y+",
                    "color": "#aabbcc",
                }
            ],
        },
    )
    rebuilt = build_project(replaced)
    resolved = rebuilt.resolved_space_model()
    left = next(p for p in resolved.part_plan.parts if p["id"] == band.part_id)
    assert changes == ["edge_banding replaced"]
    assert left["edge_banding"][0]["edge"] == "y+"
    assert left["edge_banding"][0]["color"] == "#aabbcc"
    cleared, changes = apply_project_patch(replaced, {"edge_banding": None})
    assert "edge_banding" not in cleared
    assert changes == ["edge_banding replaced"]


def test_mcp_design_update_and_recompute_replace_band_block(tmp_path, monkeypatch):
    from cabineteer import project as project_module, server

    monkeypatch.setattr(project_module, "project_dir", lambda: tmp_path / "projects")
    monkeypatch.setattr(server, "data_dir", lambda: tmp_path)

    def call(handler, args):
        loop = asyncio.new_event_loop()
        try:
            return json.loads(loop.run_until_complete(handler(args))[0].text)
        finally:
            loop.close()

    initial = _project((EdgeBand("front", "/cabinet/carcass/side_left", "y-"),))
    designed = call(server._tool_design_project, project_to_dict(initial))
    assert designed["project"]["edge_banding"][0]["edge"] == "y-"
    updated = call(
        server._tool_update_project,
        {
            "name": "edge-test",
            "edge_banding": [
                {
                    "type": "EdgeBand",
                    "id": "rear",
                    "part_id": "/cabinet/carcass/side_left",
                    "edge": "y+",
                    "color": "#aabbcc",
                }
            ],
        },
    )
    assert updated["changes"] == ["edge_banding replaced"]
    resolved = next(
        part
        for part in updated["records"]["parts"]
        if part["id"] == "/cabinet/carcass/side_left"
    )
    assert resolved["edge_banding"][0]["edge"] == "y+"
    visualized = call(
        server._tool_visualize_project,
        {
            "project": updated["project"],
            "output_dir": str(tmp_path / "visualized"),
            "open_browser": False,
        },
    )
    assert (tmp_path / "visualized" / "edge-test.glb").is_file()
    glb = _read_glb_json(tmp_path / "visualized" / "edge-test.glb")
    colors = {
        tuple(
            round(value * 255)
            for value in material["pbrMetallicRoughness"]["baseColorFactor"][:3]
        )
        for material in glb["materials"]
    }
    assert (170, 187, 204) in colors
    loaded = call(server._tool_load_project, {"name": "edge-test"})
    assert loaded["project"]["edge_banding"] == updated["project"]["edge_banding"]
    path = project_module.project_path("edge-test")
    before = path.read_bytes()
    with pytest.raises(ValueError, match="unknown resolved Space part"):
        project_module.update_saved_project(
            {
                "name": "edge-test",
                "edge_banding": [
                    {
                        "type": "EdgeBand",
                        "id": "invalid",
                        "part_id": "/missing/part",
                        "edge": "y-",
                        "color": "#b78b5b",
                    }
                ],
            }
        )
    assert path.read_bytes() == before


def test_invalid_edge_band_inputs_are_rejected():
    with pytest.raises(ValueError, match="#RRGGBB"):
        EdgeBand("bad-color", "/cabinet/carcass/side_left", "y-", "brown")
    with pytest.raises(ValueError, match="invalid edge"):
        EdgeBand("bad-edge", "/cabinet/carcass/side_left", "q-")
    with pytest.raises(ValueError, match="EdgeBand"):
        _project((object(),))
    with pytest.raises(ValueError, match="require a Space"):
        CabinetProject(
            name="legacy",
            edge_banding=(EdgeBand("legacy", "/cabinet/carcass/side_left", "y-"),),
        )


def test_null_edge_banding_is_invalid_input_but_update_null_still_clears():
    with pytest.raises(ValueError, match="edge_banding must be a list"):
        CabinetProject(name="direct-null", edge_banding=None)
    saved = project_to_dict(_project())
    saved["edge_banding"] = None
    with pytest.raises(ValueError, match="edge_banding must be a list"):
        project_from_dict(saved)
    with pytest.raises(ValueError, match="edge_banding must be a list"):
        build_project({"name": "design-null", "edge_banding": None})


def test_resolver_rejects_missing_duplicate_and_thickness_face_bands():
    from cabineteer.operations import Bore

    band = EdgeBand("front", "/cabinet/carcass/side_left", "y-")
    with pytest.raises(ValueError, match="unknown resolved Space part"):
        _project((EdgeBand("missing", "/missing/part", "y-"),)).resolved_space_model()
    with pytest.raises(ValueError, match="thickness face"):
        _project((EdgeBand("face", band.part_id, "x-"),)).resolved_space_model()
    with pytest.raises(ValueError, match="duplicate edge band id"):
        _project((band, band)).resolved_space_model()
    with pytest.raises(ValueError, match="duplicate edge band for"):
        _project(
            (band, EdgeBand("rear", band.part_id, "y-", "#abcdef"))
        ).resolved_space_model()


def test_edge_banding_keeps_physical_solid_and_exports_colored_part_surface(tmp_path):
    band = EdgeBand("front", "/cabinet/carcass/side_left", "y-", "#b78b5b")
    plain_model = _project().resolved_space_model()
    banded_model = _project((band,)).resolved_space_model()
    plain = materialize_model(plain_model)[band.part_id].val()
    banded = materialize_model(banded_model)[band.part_id].val()
    assert banded.Volume() == pytest.approx(plain.Volume())
    band_box, plain_box = banded.BoundingBox(), plain.BoundingBox()
    assert (
        band_box.xmin,
        band_box.xmax,
        band_box.ymin,
        band_box.ymax,
        band_box.zmin,
        band_box.zmax,
    ) == pytest.approx(
        (
            plain_box.xmin,
            plain_box.xmax,
            plain_box.ymin,
            plain_box.ymax,
            plain_box.zmin,
            plain_box.zmax,
        )
    )

    shapes = materialize_model(banded_model)
    assembly = make_view_assembly(banded_model, shapes, "edge-test")
    band_root = assembly.objects[band.part_id]
    assert band_root.name == band.part_id
    assert len(band_root.children) == 2
    glb = tmp_path / "edge-test.glb"
    assembly.save(str(glb), tolerance=0.1, angularTolerance=0.1)
    document = _read_glb_json(glb)
    assert any(node.get("name") == band.part_id for node in document["nodes"])
    factors = [
        material["pbrMetallicRoughness"]["baseColorFactor"]
        for material in document["materials"]
    ]
    colors = {tuple(round(value * 255) for value in factor[:3]) for factor in factors}
    assert (232, 235, 230) in colors
    assert (183, 139, 91) in colors


def test_band_colors_only_remaining_original_plane_and_rejects_removed_plane():
    from cabineteer.operations import Pocket

    band = EdgeBand("front", "/cabinet/carcass/side_left", "y-")
    base = _project((band,)).resolved_space_model()
    part = next(p for p in base.part_plan.parts if p["id"] == band.part_id)
    dims = part["stock"]["dimensions"]
    # The y- stock face spans the thickness x axis and full height z axis.
    operation = Pocket(
        "skim-front-edge",
        band.part_id,
        "y-",
        u=0,
        v=0,
        size_u=dims[0],
        size_v=dims[2] / 2,
        depth=1,
    )
    machined = _project((band,), (operation,)).resolved_space_model()
    shapes = materialize_model(machined)
    assembly = make_view_assembly(machined, shapes)
    assert len(assembly.objects[band.part_id].children) == 2

    full = Pocket(
        "remove-front-plane",
        band.part_id,
        "y-",
        u=0,
        v=0,
        size_u=dims[0],
        size_v=dims[2],
        depth=1,
    )
    removed = _project((band,), (full,)).resolved_space_model()
    with pytest.raises(ValueError, match="no remaining finished face"):
        make_view_assembly(removed, materialize_model(removed))
