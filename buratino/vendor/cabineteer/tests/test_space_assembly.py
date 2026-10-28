from types import SimpleNamespace

import pytest

from cabineteer.space_assembly import resolve_space_assembly
from cabineteer.layout import CabinetRef, Row
from cabineteer.space_adapter import space_model_records
from cabineteer.spaces import (AssemblyModule, AssemblyRef, Carcass, Divider, Door,
                               Fixed, Fr, Insets, Space, SpaceCabinetDefinition, Split)


def project(*, layout=None, host=None, cabinets=(), modules=()):
    return SimpleNamespace(layout=layout, space_model=host, space_cabinets=cabinets, space_modules=modules)


def test_adjacent_cabinets_keep_instance_ids_and_front_seam():
    recipe = SpaceCabinetDefinition("base", Carcass(Fr(), 720, 560), Space("inside"), (Door("door", "inside"),))
    run = Row("run", (CabinetRef("left", "base"), CabinetRef("right", "base")), size_x=Fixed(1440))
    plan = resolve_space_assembly(project(layout=run, cabinets=(recipe,)))
    assert [f["origin"][0] for f in plan.fronts] == [2, 721]
    assert [f["size"][0] for f in plan.fronts] == [717, 717]
    assert len({p["id"] for p in plan.part_plan.parts}) == 12
    records = space_model_records(plan)
    assert {p["id"] for p in records["parts"]} == {p["id"] for p in plan.part_plan.parts}
    assert recipe.carcass.width == Fr()


def test_nested_bare_modules_and_host_door():
    module = AssemblyModule("shelves", Space("insert", split=Split("height", (Space("lower", Fr()), Divider("shelf"), Space("upper", Fr())))), Fr(), Fr(), Fr(), (Door("door", "insert"),))
    bays = tuple(Space(name, Fr(), content=AssemblyRef("insert", "shelves", Insets(front=20))) for name in ("a", "b"))
    root = Space("inside", split=Split("width", bays))
    host = SimpleNamespace(carcass=Carcass(400, 400, 400), root=root, fronts=(Door("door", "inside"),))
    plan = resolve_space_assembly(project(host=host, modules=(module,)))
    assert len(plan.part_plan.parts) == 10
    assert [p["size"] for p in plan.part_plan.parts if p["kind"] == "divider"] == [[182, 374, 18], [182, 374, 18]]
    assert [f["origin"][1] for f in plan.fronts] == [-18, 2, 2]
    assert len({p["id"] for p in plan.part_plan.parts}) == 10
    assert any(c["part_b"] == "/cabinet/carcass/back" or c["part_a"] == "/cabinet/carcass/back" for c in plan.part_plan.contacts)


def test_nested_complete_cabinet_needs_front_inset():
    recipe = SpaceCabinetDefinition("small", Carcass(100, 100, 100), Space("inside"), (Door("door", "inside"),))
    module = AssemblyModule("unit", Row("row", (CabinetRef("small", "small"),)))
    def resolve(inset):
        host = SimpleNamespace(carcass=Carcass(400, 400, 400), root=Space("inside", content=AssemblyRef("unit", "unit", Insets(front=inset))), fronts=())
        return resolve_space_assembly(project(host=host, cabinets=(recipe,), modules=(module,)))
    plan = resolve(20)
    inner = next(s for s in plan.spaces if s["id"].endswith("/small/inside"))
    assert inner["size"] == [64, 94, 64]
    with pytest.raises(ValueError, match="protrudes"):
        resolve(0)


def test_invalid_unused_module_reference_and_cycle():
    bad = AssemblyModule("bad", Space("inside", content=AssemblyRef("next", "missing")), Fr(), Fr(), Fr())
    host = SimpleNamespace(carcass=Carcass(400, 400, 400), root=Space("inside"), fronts=())
    with pytest.raises(ValueError, match="unknown module"):
        resolve_space_assembly(project(host=host, modules=(bad,)))
    cycle = AssemblyModule("loop", Space("inside", content=AssemblyRef("next", "loop")), Fr(), Fr(), Fr())
    with pytest.raises(ValueError, match="cyclic"):
        resolve_space_assembly(project(host=host, modules=(cycle,)))


def test_stock_axis_and_group_ids_are_stable():
    from cabineteer.spaces import PhysicalPartPlan, ResolvedModel
    def part(name, size, axis):
        return dict(id=name, kind="frame", material="wood", stock=dict(dimensions=size, thickness=18, thickness_axis=axis))
    one = part("a", [18, 18, 100], 0)
    second = part("b", [18, 20, 110], 0)
    def groups(parts):
        model = ResolvedModel([], [], [], [], [], PhysicalPartPlan(parts), {})
        return {g["members"][0]: g["id"] for g in space_model_records(model)["viewer"]["cutting_groups"]}
    assert groups([one])["a"] == groups([second, one])["a"]
    assert space_model_records(ResolvedModel([], [], [], [], [], PhysicalPartPlan([one]), {}))["parts"][0]["stock_mm"] == {"length": 100, "width": 18, "thickness": 18}


def test_wrapper_does_not_resize_a_fixed_root():
    recipe = SpaceCabinetDefinition("small", Carcass(200, 100, 100), Space("inside"))
    module = AssemblyModule("unit", Row("row", (CabinetRef("small", "small"),), size_x=Fixed(200)), Fixed(300), Fr(), Fr())
    host = SimpleNamespace(carcass=Carcass(400, 400, 400), root=Space("inside", content=AssemblyRef("unit", "unit")), fronts=())
    plan = resolve_space_assembly(project(host=host, cabinets=(recipe,), modules=(module,)))
    wrapper = next(p for p in plan.placements if p["kind"] == "assembly_ref")
    inner = next(p for p in plan.placements if p.get("definition") == "small")
    assert wrapper["size"][0] == 300
    assert inner["size"][0] == 200
    assert inner["origin"][0] == 18
    assert next(a for a in plan.allocations if a.get("scope") == "module_root" and a["axis"] == "x")["slack"] == 100


def test_authored_tiny_gap_stays_exposed():
    recipe = SpaceCabinetDefinition("base", Carcass(720, 720, 560), Space("inside"), (Door("door", "inside"),))
    run = Row("run", (CabinetRef("a", "base"), CabinetRef("b", "base")), gap_mm=0.0000001)
    plan = resolve_space_assembly(project(layout=run, cabinets=(recipe,)))
    assert [f["size"][0] for f in plan.fronts] == pytest.approx([716, 716])


def test_project_and_plan_round_trip_without_cad():
    import json
    import subprocess
    import sys

    code = '''
import importlib.abc, json, sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "cadquery" or fullname.startswith("OCP"):
            raise AssertionError("unexpected CAD import")
sys.meta_path.insert(0, Block())
from cabineteer.project import CabinetProject, project_to_dict, project_from_dict
from cabineteer.layout import Row, CabinetRef
from cabineteer.spaces import Carcass, Space, SpaceCabinetDefinition, Door, Fr, Fixed, ResolvedModel
from cabineteer.space_adapter import space_model_records
recipe = SpaceCabinetDefinition("base", Carcass(Fr(), 720, 560), Space("inside"), (Door("door", "inside"),))
project = CabinetProject("pair", space_cabinets=(recipe,), layout=Row("run", (CabinetRef("a", "base"), CabinetRef("b", "base")), size_x=Fixed(1440)))
payload = json.loads(json.dumps(project_to_dict(project)))
assert payload["input_schema_version"] == 2
project = project_from_dict(payload)
plan = project.resolved_space_assembly()
restored = ResolvedModel.from_dict(json.loads(json.dumps(plan.to_dict())))
assert restored.to_dict() == plan.to_dict()
assert space_model_records(restored) == space_model_records(plan)
assert isinstance(project.space_cabinets[0].carcass.width, Fr)
'''
    subprocess.run([sys.executable, "-c", code], check=True)


def test_unused_definition_front_references_are_validated_without_dimensions():
    from cabineteer.spaces import AppliedDrawerFront, DrawerBox
    host = SimpleNamespace(carcass=Carcass(400, 400, 400), root=Space("inside"), fronts=())
    def run(root, fronts):
        unused = SpaceCabinetDefinition("unused", Carcass(Fr(), 100, 100), root, fronts)
        return resolve_space_assembly(project(host=host, cabinets=(unused,)))
    with pytest.raises(ValueError, match="coverage reference.*missing.*unknown"):
        run(Space("inside"), (Door("bad", "missing"),))
    with pytest.raises(ValueError, match="drawer attachment reference.*missing.*unknown"):
        run(Space("inside", content=DrawerBox("box", 30)), (AppliedDrawerFront("bad", "inside", "missing"),))
    with pytest.raises(ValueError, match="duplicate front"):
        run(Space("inside"), (Door("same", "inside"), Door("same", "inside")))
    assert len(run(Space("inside"), (Door("valid", "inside"),)).part_plan.parts) == 5


def test_unused_module_front_must_resolve_in_its_own_space_tree():
    host = SimpleNamespace(carcass=Carcass(400, 400, 400), root=Space("inside"), fronts=())
    module = AssemblyModule("unused", Space("insert"), Fr(), Fr(), Fr(), (Door("bad", "inside"),))
    with pytest.raises(ValueError, match="coverage reference.*inside.*unknown"):
        resolve_space_assembly(project(host=host, modules=(module,)))
    module = AssemblyModule("unused", Space("insert"), Fr(), Fr(), Fr(), (Door("good", "insert"),))
    assert len(resolve_space_assembly(project(host=host, modules=(module,))).part_plan.parts) == 5
