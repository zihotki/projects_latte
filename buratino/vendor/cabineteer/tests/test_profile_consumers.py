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
        assert any(p["operations"] for p in expected["parts"])

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(run())
    finally:
        loop.close()
