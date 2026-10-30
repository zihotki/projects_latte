from copy import deepcopy

from buratino.engine import calculate
from buratino.grouping import group_cutting_blanks
from buratino.project import load_project


def test_reference_cabinet_groups_five_physical_parts_into_four_blanks(project):
    result = calculate(load_project(project)).result

    assert len(result["parts"]) == 5
    assert result["grouping_scope"] == "cutting_blank"
    groups = result["cutting_groups"]
    assert len(groups) == 4
    sides = next(group for group in groups if group["label"] == "Side panels")
    assert sides["quantity"] == 2
    assert sides["members"] == [
        "cabinet.carcass.left_side",
        "cabinet.carcass.right_side",
    ]
    bottom = next(group for group in groups if group["label"] == "Bottom panels")
    assert bottom["members"] == ["cabinet.carcass.bottom"]
    assert all(group["grouping_scope"] == "cutting_blank" for group in groups)
    assert all(group["machining_status"] == "unverified" for group in groups)
    assert sum(group["quantity"] for group in groups) == 5

    parts = {part["id"]: part for part in result["parts"]}
    assert parts["cabinet.carcass.top"]["grain_axis_local"] == "x"
    assert parts["cabinet.carcass.bottom"]["grain_axis_local"] == "x"
    assert parts["cabinet.carcass.left_side"]["grain_axis_local"] == "z"
    assert parts["cabinet.carcass.back"]["grain_axis_local"] == "z"
    assert all(part["grain_status"] == "assumed" for part in parts.values())

    grain_issues = [
        issue
        for issue in result["checks"]
        if issue["code"] == "grain.direction_assumed"
    ]
    assert len(grain_issues) == 1
    assert grain_issues[0]["severity"] == "unknown"
    assert all(part_id in grain_issues[0]["affected"] for part_id in parts)


def test_blank_variants_do_not_merge_and_group_ids_ignore_input_order(project):
    parts = calculate(load_project(project)).result["parts"]
    left, right = (
        deepcopy(next(part for part in parts if part["component"] == role))
        for role in ("left_side", "right_side")
    )
    baseline = group_cutting_blanks([left, right])
    assert len(baseline) == 1

    changed_dimension = deepcopy(right)
    changed_dimension["finished_mm"]["width"] += 1
    changed_material = deepcopy(right)
    changed_material["material"] = "different board"
    changed_grain = deepcopy(right)
    changed_grain["grain_direction"] = "width"
    changed_axis = deepcopy(right)
    changed_axis["grain_axis_local"] = "y"
    changed_grain_status = deepcopy(right)
    changed_grain_status["grain_status"] = "confirmed"
    changed_thickness = deepcopy(right)
    changed_thickness["finished_mm"]["thickness"] -= 1

    for variant in (
        changed_dimension,
        changed_material,
        changed_thickness,
    ):
        assert len(group_cutting_blanks([left, variant])) == 2
    for variant in (changed_axis, changed_grain, changed_grain_status):
        assert len(group_cutting_blanks([left, variant])) == 1
    mixed_status = group_cutting_blanks([left, changed_grain_status])[0]
    assert mixed_status["grain_status"] == "mixed"
    assert {member["grain_status"] for member in mixed_status["member_details"]} == {
        "assumed",
        "confirmed",
    }
    mixed = group_cutting_blanks([left, changed_grain])[0]
    assert mixed["grain_direction"] == "mixed"
    assert {member["grain_direction"] for member in mixed["member_details"]} == {
        "length",
        "width",
    }

    forward = group_cutting_blanks([left, right])
    reverse = group_cutting_blanks([right, left])
    assert reverse == forward


def test_equal_blanks_keep_member_profiles_and_finished_dimensions(project):
    parts = calculate(load_project(project)).result["parts"]
    left, right = (
        deepcopy(next(part for part in parts if part["component"] == role))
        for role in ("left_side", "right_side")
    )
    left["blank_mm"] = {"length": 780, "width": 400, "thickness": 18}
    right["blank_mm"] = dict(left["blank_mm"])
    left["component"] = left["role"] = "top"
    right["component"] = right["role"] = "bottom"
    left["finished_mm"] = {"length": 750, "width": 400, "thickness": 18}
    right["finished_mm"] = {"length": 720, "width": 400, "thickness": 18}
    left["profile"] = {
        "shape": "sloped",
        "angle_deg": 12,
        "points": [[0, 0], [780, 80]],
    }
    right["profile"] = {"shape": "square", "angle_deg": 0}

    groups = group_cutting_blanks([left, right])

    assert len(groups) == 1
    group = groups[0]
    assert group["blank_mm"] == {"length": 780, "width": 400, "thickness": 18}
    assert group["finished_mm"] == left["finished_mm"]
    assert [member["profile"] for member in group["member_details"]] == [
        left["profile"],
        right["profile"],
    ]
    assert [member["finished_mm"] for member in group["member_details"]] == [
        left["finished_mm"],
        right["finished_mm"],
    ]
    assert [member["label"] for member in group["member_details"]] == [
        "Top panels",
        "Bottom panels",
    ]


def test_drawer_components_group_with_useful_labels_and_keep_all_physical_ids():
    parts = []
    blanks = {
        "side_left": (450, 150, 16),
        "side_right": (450, 150, 16),
        "inner_front": (644, 150, 18),
        "back": (644, 150, 18),
        "bottom": (660, 450, 12),
        "face": (716, 230, 18),
    }
    for cabinet_id in ("left", "right"):
        for drawer_index in range(1, 3):
            instance_id = f"{cabinet_id}/column-0/opening-{drawer_index - 1}"
            for component, (length, width, thickness) in blanks.items():
                role = f"{cabinet_id}_drawer_{drawer_index}_{component}"
                parts.append(
                    {
                        "id": f"{cabinet_id}.{instance_id}.{component}",
                        "role": role,
                        "component": component,
                        "drawer_index": drawer_index,
                        "instance_id": instance_id,
                        "cabinet_id": cabinet_id,
                        "quantity": 1,
                        "finished_mm": {
                            "length": length,
                            "width": width,
                            "thickness": thickness,
                        },
                        "material": "MFC; measured stock unconfirmed",
                        "grain_direction": "length",
                        "grain_axis_local": "x",
                        "grain_status": "assumed",
                        "edge_treatment": "unconfirmed",
                    }
                )

    groups = group_cutting_blanks(parts)
    assert sum(group["quantity"] for group in groups) == 24
    assert len({member for group in groups for member in group["members"]}) == 24
    assert len({part["instance_id"] for part in parts}) == 4
    assert len({part["role"] for part in parts}) == 24
    quantities = {group["label"]: group["quantity"] for group in groups}
    assert quantities == {
        "Drawer sides": 8,
        "Drawer inner fronts and backs": 8,
        "Drawer bottoms": 4,
        "Overlay fronts": 4,
    }


def test_confirmed_grain_does_not_change_grouping(project):
    inputs = load_project(project)
    inputs.variables["grain_direction_confirmed"] = True
    result = calculate(inputs).result

    assert result["parts"]
    assert all(part["grain_status"] == "confirmed" for part in result["parts"])
    assert all(
        group["grain_status"] == "confirmed" for group in result["cutting_groups"]
    )
    assert sum(group["quantity"] for group in result["cutting_groups"]) == len(
        result["parts"]
    )
    assert not any(
        issue["code"] == "grain.direction_assumed" for issue in result["checks"]
    )
