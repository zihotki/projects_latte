from itertools import combinations

import cadquery as cq
import pytest
from cabineteer.drawer import build_drawer

from buratino.engine import calculate, make_geometry
from buratino.project import load_project

BOX_COMPONENTS = {
    "side_left": "drawer_side_L",
    "side_right": "drawer_side_R",
    "inner_front": "drawer_sub_front",
    "back": "drawer_back",
    "bottom": "drawer_bottom",
}
CARCASS_COMPONENTS = {"side", "top", "bottom", "back", "divider", "shelf"}
OVERLAP_TOLERANCE_MM3 = 1e-5


def _world_shape(assembly, role):
    # Assembly objects include their applied location in toCompound().
    return assembly.objects[role].toCompound()


def _bbox(shape):
    bounds = shape.BoundingBox()
    return (
        bounds.xmin,
        bounds.xmax,
        bounds.ymin,
        bounds.ymax,
        bounds.zmin,
        bounds.zmax,
    )


def _bounds_overlap(left, right, tolerance=1e-7):
    return all(
        min(left[axis + 1], right[axis + 1]) - max(left[axis], right[axis]) > tolerance
        for axis in (0, 2, 4)
    )


def _assert_no_solid_overlap(left, right, context):
    if _bounds_overlap(_bbox(left), _bbox(right)):
        volume = left.intersect(right).Volume()
        assert volume <= OVERLAP_TOLERANCE_MM3, f"{context}: {volume:.6g} mm³"


def _drawer_record_by_component(calculation, drawer_id):
    return {
        part["component"]: part
        for part in calculation.result["parts"]
        if part.get("instance_id") == drawer_id
    }


def _native_expected_part(part, offset, world_position, cfg, component):
    shape = part.shape.val()
    if component == "back":
        relief = cfg.buratino_rear_corner_clearance_width_mm
        if relief:
            for x in (0, cfg.front_back_panel_length - relief):
                cutter = cq.Solid.makeBox(
                    relief,
                    cfg.front_back_thickness,
                    cfg.bottom_dado_inset,
                    cq.Vector(x, 0, 0),
                )
                shape = shape.cut(cutter)
    position = tuple(world_position[i] + offset[i] for i in range(3))
    return shape.translate(cq.Vector(*position))


def test_assembled_eb20_drawers_match_native_parts_and_clear_surroundings(root):
    calculation = calculate(load_project(root / "projects/drawer-cabinet"))
    assembly, _ = make_geometry(calculation)
    assert len(calculation.drawer_instances) == 4

    carcass = [
        _world_shape(assembly, part["role"])
        for part in calculation.result["parts"]
        if not part.get("instance_id") and part["component"] in CARCASS_COMPONENTS
    ]
    drawer_shapes = {}
    for item in calculation.drawer_instances:
        cfg = item["config"]
        drawer_id = item["drawer_id"]
        records = _drawer_record_by_component(calculation, drawer_id)
        _, native_parts = build_drawer(cfg)
        native_by_name = {part.name: part for part in native_parts}
        world_position = (
            calculation.result["cabinets"][0]["placement_mm"]["x"]
            + item["box_position"]["x"],
            calculation.result["cabinets"][0]["placement_mm"]["y"]
            + item["box_position"]["y"],
            item["box_position"]["z"],
        )

        assert cfg.box_depth == 450
        assert cfg.side_thickness == 16
        assert cfg.bottom_dado_depth == 6
        assert cfg.bottom_dado_inset in (12, 13)
        assert cfg.bottom_thickness == 12

        parts = {}
        for component, native_name in BOX_COMPONENTS.items():
            record = records[component]
            role = record["role"]
            actual = _world_shape(assembly, role)
            expected = _native_expected_part(
                native_by_name[native_name],
                item["offsets"][component],
                world_position,
                cfg,
                component,
            )
            assert actual.cut(expected).Volume() <= OVERLAP_TOLERANCE_MM3
            assert expected.cut(actual).Volume() <= OVERLAP_TOLERANCE_MM3
            parts[component] = actual

        # The bottom sits 12–13 mm above the side underside and reaches each
        # of the four 6 mm grooves. Its solid must not cross the groove walls.
        left = _bbox(parts["side_left"])
        right = _bbox(parts["side_right"])
        front = _bbox(parts["inner_front"])
        back = _bbox(parts["back"])
        bottom = _bbox(parts["bottom"])
        assert bottom[0] == pytest.approx(left[1] - 6)
        assert bottom[1] == pytest.approx(right[0] + 6)
        assert bottom[2] == pytest.approx(front[3] - 6)
        assert bottom[3] == pytest.approx(back[2] + 6)
        assert bottom[4] - left[4] == pytest.approx(cfg.bottom_dado_inset)

        # Check each placed solid. Mating faces may touch; only positive-volume
        # intersections are collisions.
        drawer_shapes[drawer_id] = parts
        for (left_name, left_shape), (right_name, right_shape) in combinations(
            parts.items(), 2
        ):
            _assert_no_solid_overlap(
                left_shape,
                right_shape,
                f"{drawer_id}.{left_name} intersects {drawer_id}.{right_name}",
            )
        for component, shape in parts.items():
            for carcass_shape in carcass:
                _assert_no_solid_overlap(
                    shape,
                    carcass_shape,
                    f"{drawer_id}.{component} intersects carcass",
                )

    for (left_id, left_parts), (right_id, right_parts) in combinations(
        drawer_shapes.items(), 2
    ):
        for left_name, left_shape in left_parts.items():
            for right_name, right_shape in right_parts.items():
                _assert_no_solid_overlap(
                    left_shape,
                    right_shape,
                    f"{left_id}.{left_name} intersects {right_id}.{right_name}",
                )
