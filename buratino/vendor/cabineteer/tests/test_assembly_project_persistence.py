import json

import pytest
from cabineteer.allocation import Fixed, Fr
from cabineteer.layout import CabinetRef, Row
from cabineteer.project import (CabinetProject, list_saved_projects, project_from_dict,
                                project_to_dict, save_project, update_saved_project)
from cabineteer.spaces import Carcass, Space, SpaceCabinetDefinition


def pair():
    definition = SpaceCabinetDefinition("base", Carcass(Fr(), 720, 560), Space("inside"))
    return CabinetProject("pair", space_cabinets=(definition,),
        layout=Row("run", (CabinetRef("left", "base"), CabinetRef("right", "base")), size_x=Fixed(1440)))


def test_tagged_roundtrip_retains_requests_and_allocations():
    project = pair()
    data = project_to_dict(project)
    assert data["input_schema_version"] == 2
    assert data["space_cabinets"][0]["carcass"]["width"] == {"type": "Fr", "weight": 1}
    restored = project_from_dict(data)
    assert restored == project
    assert [p["size"][0] for p in restored.resolved_space_assembly().placements] == [720, 720]
    for bad in (dict(data, input_schema_version=3), dict(data, layout={"type": "Row", "name": "x", "children": [], "unexpected": 1})):
        with pytest.raises(ValueError):
            project_from_dict(bad)


def test_update_validation_is_atomic_and_listing_resolves(monkeypatch, tmp_path):
    monkeypatch.setattr("cabineteer.project.project_dir", lambda: tmp_path)
    project = pair()
    path = save_project(project)
    before = path.read_text()
    with pytest.raises(ValueError, match="unknown cabinet"):
        update_saved_project({"name": "pair", "layout": {"type": "Row", "name": "run", "children": [{"type": "CabinetRef", "name": "bad", "definition": "missing"}]}})
    assert path.read_text() == before
    with pytest.raises(ValueError, match="unknown input type"):
        update_saved_project({"name": "pair", "profile_assembly": {"type": "BadProfile"}})
    assert path.read_text() == before
    (tmp_path / "broken.json").write_text(json.dumps({"name": "broken", "input_schema_version": 9, "space_cabinets": [{"type": "bad"}]}))
    entries = {e["name"]: e for e in list_saved_projects(include_all=True)}
    assert entries["pair"]["total_run_width_mm"] == 1440
    assert entries["pair"]["cabinet_names"] == ["/run/left", "/run/right"]
    assert "error" in entries["broken"]


def test_space_assembly_mcp_design_load_evaluate_and_cutlist(monkeypatch, tmp_path):
    import asyncio
    from cabineteer.server import call_tool

    monkeypatch.setattr("cabineteer.paths.data_dir", lambda: tmp_path)
    monkeypatch.setattr("cabineteer.server.data_dir", lambda: tmp_path)
    def call(name, args):
        return json.loads(asyncio.get_event_loop().run_until_complete(call_tool(name, args))[0].text)

    designed = call("design_project", project_to_dict(pair()))
    assert designed["cabinet_count"] == 2
    loaded = call("load_project", {"name": "pair"})
    assert loaded["project"]["layout"]["type"] == "Row"
    evaluated = call("evaluate_project", {"project_name": "pair"})
    assert evaluated["summary"]["pass"]
    cutlist = call("generate_project_cutlist", {"project_name": "pair"})
    assert cutlist["parts"]


def test_profile_tagged_bounds_and_strict_input():
    from cabineteer.layout import Bounds3D, LayoutLeaf
    from cabineteer.project import ProjectCabinet
    from cabineteer.cabinet import CabinetConfig

    project = CabinetProject("profile", cabinets=(ProjectCabinet("lower", CabinetConfig(width=100, height=100, depth=100)),),
        layout=Row("row", (LayoutLeaf("lower", 100, 100, 100, Bounds3D(0, -5, 0, 100, 100, 100)),)))
    data = project_to_dict(project)
    assert data["layout"]["type"] == "Row"
    assert data["layout"]["children"][0]["occupied_bounds_mm"]["type"] == "Bounds3D"
    assert project_from_dict(data) == project
    for bad in ({k: v for k, v in data.items() if k != "input_schema_version"},
                dict(data, typo=1), dict(data, layout={"type": "row", "name": "bad"})):
        with pytest.raises(ValueError):
            project_from_dict(bad)


def test_listing_isolates_missing_required_fields_and_invalid_profile(monkeypatch, tmp_path):
    monkeypatch.setattr("cabineteer.project.project_dir", lambda: tmp_path)
    save_project(pair())
    (tmp_path / "missing.json").write_text(json.dumps({"input_schema_version": 2, "space_model": {"root": {"type": "Space", "name": "x"}}}))
    (tmp_path / "invalid.json").write_text(json.dumps({"input_schema_version": 3, "name": "invalid", "layout": {"type": "row"}}))
    entries = {e["name"]: e for e in list_saved_projects(include_all=True)}
    assert "error" in entries["missing"] and "error" in entries["invalid"]
    assert entries["pair"]["cabinet_count"] == 2


def test_visualize_returns_records_when_cad_is_unavailable(monkeypatch):
    import asyncio
    import builtins
    from cabineteer.server import call_tool

    real_import = builtins.__import__
    def blocked(name, *args, **kwargs):
        if name == "cadquery":
            raise ImportError("CAD blocked")
        return real_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", blocked)
    response = asyncio.get_event_loop().run_until_complete(call_tool("visualize_project", {"project": project_to_dict(pair())}))
    data = json.loads(response[0].text)
    assert data["visualization_status"] == "cad_unavailable"
    assert data["records"]["viewer"]["parts"]
