import asyncio
import builtins
import json

import pytest

from cabineteer.project import CabinetProject, SpaceModelSpec, project_from_dict, project_to_dict
from cabineteer.spaces import Carcass, Space, Split, Divider, Fr, DrawerBox, Door
from cabineteer.space_adapter import space_model_records, materialize_model, validate_model


def project():
    return CabinetProject(name="spaces", space_model=SpaceModelSpec(
        Carcass(600, 936, 500), Space("root", split=Split("height", [
            Space("low", Fr(), content=DrawerBox("box", bottom_clearance=30)),
            Divider("shelf", role="adjustable"), Space("high", Fr())])),
        (Door("door", "root"),)))


def test_project_roundtrip_and_records():
    p = project()
    payload = project_to_dict(p)
    assert payload["space_model"]["root"]["type"] == "Space"
    model = p.resolved_space_model()
    assert project_from_dict(json.loads(json.dumps(payload))).resolved_space_model().to_dict() == model.to_dict()
    records = space_model_records(model)
    assert [x["id"] for x in records["parts"]] == [x["id"] for x in model.part_plan.parts]
    assert {x["cabinet_id"] for x in records["parts"]} == {"cabinet"}
    assert next(x for x in records["parts"] if x["kind"] == "door").get("instance_id") is None
    assert all(x.get("instance_id") == "/root/low/box" for x in records["parts"] if x["kind"].startswith("drawer_"))
    with pytest.raises(ValueError, match="cannot be combined"):
        CabinetProject(name="mixed", cabinets=(object(),), space_model=p.space_model)


def test_materialization_and_diagnostics_do_not_change_model():
    pytest.importorskip("cadquery")
    model = project().resolved_space_model()
    before = model.to_dict()
    shapes = materialize_model(model)
    assert set(shapes) == {p["id"] for p in model.part_plan.parts}
    for part in model.part_plan.parts:
        bb = shapes[part["id"]].val().BoundingBox()
        assert [bb.xmin, bb.ymin, bb.zmin] == pytest.approx(part["bounds"][0])
        assert [bb.xmax, bb.ymax, bb.zmax] == pytest.approx(part["bounds"][1])
    result = validate_model(model)
    assert result == {"status": "passed", "diagnostics": []}
    assert model.to_dict() == before


def test_mcp_roundtrip_and_cutlist(tmp_path, monkeypatch):
    from cabineteer import project as project_module, server
    monkeypatch.setattr(project_module, "project_dir", lambda: tmp_path / "projects")
    monkeypatch.setattr(server, "data_dir", lambda: tmp_path)
    payload = project_to_dict(project())
    def call(handler, args):
        return json.loads(asyncio.get_event_loop().run_until_complete(handler(args))[0].text)
    designed = call(server._tool_design_project, payload)
    loaded = call(server._tool_load_project, {"name": "spaces"})
    evaluated = call(server._tool_evaluate_project, {"project_name": "spaces"})
    cutlist = call(server._tool_generate_project_cutlist, {"project_name": "spaces"})
    assert designed["space_model"] == loaded["space_model"] == evaluated["space_model"]
    assert [p["id"] for p in cutlist["parts"]] == [p["id"] for p in designed["records"]["parts"]]
    assert evaluated["summary"]["physical_validation"]["status"] == "not_requested"


def test_missing_cad_reports_unavailable(monkeypatch):
    real_import = builtins.__import__
    def blocked(name, *args, **kwargs):
        if name == "cadquery":
            raise ImportError("blocked")
        return real_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", blocked)
    model = project().resolved_space_model()
    assert validate_model(model)["status"] == "unavailable"
    assert space_model_records(model)["parts"]


def test_static_validation_detects_overlap_and_missing_contact():
    pytest.importorskip("cadquery")
    model = project().resolved_space_model()
    part = next(p for p in model.part_plan.parts if p["id"] == "/carcass/top")
    part["transform"]["translation"][0] += 1000
    before = model.to_dict()
    diagnostics = validate_model(model)["diagnostics"]
    assert any(d["code"] == "missing_contact" and "/carcass/top" in d["part_ids"] for d in diagnostics)
    assert model.to_dict() == before
    part["transform"]["translation"] = [18, 0, 0]
    diagnostics = validate_model(model)["diagnostics"]
    assert any(d["code"] == "overlap" and "/carcass/top" in d["part_ids"] for d in diagnostics)


def test_visualize_space_model(tmp_path):
    pytest.importorskip("cadquery")
    from cabineteer import server
    result = json.loads(asyncio.get_event_loop().run_until_complete(server._tool_visualize_project({
        "project": project_to_dict(project()), "output_dir": str(tmp_path), "open_browser": False
    }))[0].text)
    assert len(result["records"]["parts"]) == result["parts"]
    assert (tmp_path / "spaces.glb").exists()


def test_fresh_process_mcp_never_imports_cad(tmp_path):
    import os
    import subprocess
    import sys
    code = r'''
import asyncio, builtins, json, sys
from pathlib import Path
real_import = builtins.__import__
def blocked(name, *args, **kwargs):
    if name == "cadquery" or name.startswith("cadquery.") or name == "OCP" or name.startswith("OCP."):
        raise AssertionError("CAD import attempted: " + name)
    return real_import(name, *args, **kwargs)
builtins.__import__ = blocked
from cabineteer.project import CabinetProject, SpaceModelSpec, project_to_dict
from cabineteer.spaces import Carcass, Space
from cabineteer import project, server
root = Path(sys.argv[1])
project.project_dir = lambda: root / "projects"
server.data_dir = lambda: root
p = CabinetProject("lite", space_model=SpaceModelSpec(Carcass(600, 936, 500), Space("root")))
def run(fn, args):
    return json.loads(asyncio.run(fn(args))[0].text)
design = run(server._tool_design_project, project_to_dict(p))
load = run(server._tool_load_project, {"name": "lite"})
evaluate = run(server._tool_evaluate_project, {"project_name": "lite"})
cutlist = run(server._tool_generate_project_cutlist, {"project_name": "lite"})
assert design["space_model"] == load["space_model"] == evaluate["space_model"]
assert cutlist["parts"] and "cadquery" not in sys.modules
'''
    subprocess.run([sys.executable, "-c", code, str(tmp_path)], check=True, env=os.environ.copy())


@pytest.mark.parametrize("style", ["butt", "qqq", "half_lap", "drawer_lock"])
def test_drawer_recipe_geometry(style):
    pytest.importorskip("cadquery")
    model = CabinetProject("recipe", space_model=SpaceModelSpec(
        Carcass(600, 936, 500), Space("root", content=DrawerBox("box", bottom_clearance=30, joinery_style=style)))).resolved_space_model()
    assert validate_model(model) == {"status": "passed", "diagnostics": []}


def test_mcp_requested_physical_validation_unavailable(monkeypatch):
    from cabineteer import server
    real_import = builtins.__import__
    def blocked(name, *args, **kwargs):
        if name == "cadquery":
            raise ImportError("blocked")
        return real_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", blocked)
    result = json.loads(asyncio.get_event_loop().run_until_complete(server._tool_evaluate_project({
        "project": project_to_dict(project()), "physical_validation": True
    }))[0].text)
    assert result["summary"]["numeric_status"] == "passed"
    assert result["summary"]["physical_validation"]["status"] == "unavailable"
    assert result["summary"]["pass"] is False


@pytest.mark.parametrize("wall, severity, passed", [(500, "error", False), (700, "info", True)])
def test_space_project_wall_fit(wall, severity, passed):
    from dataclasses import replace
    from cabineteer import server
    from cabineteer.project import check_project_consistency
    p = replace(project(), wall_width_mm=wall)
    issues = check_project_consistency(p)
    assert [(i["check"], i["severity"], i["value"], i["limit"]) for i in issues] == [
        ("project_wall_fit", severity, 600, wall)]
    result = json.loads(asyncio.get_event_loop().run_until_complete(server._tool_evaluate_project({
        "project": project_to_dict(p)
    }))[0].text)
    assert result["project_issues"] == issues
    assert result["summary"]["pass"] is passed
