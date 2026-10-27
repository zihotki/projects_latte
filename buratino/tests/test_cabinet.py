import shutil

import pytest

from buratino.engine import calculate, make_geometry
from buratino.project import load_project


def test_bare_native_cabinet_uses_native_panel_dimensions(root):
    calculation = calculate(load_project(root / "projects/simple-cabinet"))
    result = calculation.result
    parts = {part["component"]: part["finished_mm"] for part in result["parts"]}
    assert len(result["parts"]) == 5
    assert parts["left_side"] == {"length": 970, "width": 500, "thickness": 18}
    assert parts["bottom"] == {"length": 684, "width": 494, "thickness": 18}
    assert parts["top"] == {"length": 684, "width": 500, "thickness": 18}
    assert parts["back"] == {"length": 952, "width": 684, "thickness": 6}
    assert result["dimensions_mm"] == {"width": 720, "height": 970, "depth": 500}
    assert result["overall_dimensions_mm"] == {
        "width": 720,
        "height": 970,
        "depth": 500,
    }

    assembly, geometry = make_geometry(calculation)
    bounds = assembly.toCompound().BoundingBox()
    assert len(geometry) == 5
    assert [bounds.xlen, bounds.ylen, bounds.zlen] == pytest.approx([720, 500, 970])
    assert {
        issue["code"] for issue in result["checks"] if issue["severity"] == "error"
    } == set()
    assert any(
        issue["code"] == "cabineteer.domino_machining_unknown"
        for issue in result["checks"]
    )
    assert result["manufacturing_ready"] is False


def test_native_dimension_change_keeps_physical_ids_stable(root, tmp_path):
    path = tmp_path / "simple-cabinet"
    shutil.copytree(
        root / "projects/simple-cabinet", path, ignore=shutil.ignore_patterns("build")
    )
    first = calculate(load_project(path))
    source = (path / "project.py").read_text()
    (path / "project.py").write_text(
        source.replace('"width_mm": 720', '"width_mm": 700', 1)
    )
    second = calculate(load_project(path))
    assert [part["id"] for part in first.result["parts"]] == [
        part["id"] for part in second.result["parts"]
    ]
    assert first.result["input_identity"] != second.result["input_identity"]
    assert second.result["dimensions_mm"]["width"] == 700
    assert (
        next(part for part in second.result["parts"] if part["component"] == "top")[
            "finished_mm"
        ]["length"]
        == 664
    )
