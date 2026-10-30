"""Runner selection across current general cabinet projects."""

from dataclasses import replace

import pytest

from buratino.engine import calculate, make_geometry
from buratino.project import InputError, load_project, native_snapshot

RUNNER_450 = "buratino_hettich_quadro_v6_eb20"
RUNNER_480 = "buratino_hettich_quadro_v6_eb20_480"


def _mixed_inputs(linked_row_project):
    inputs = load_project(linked_row_project)
    cabinets = []
    for cabinet in inputs.native_project.cabinets:
        opening = cabinet.config.openings[0]
        slide_key = RUNNER_480 if cabinet.name == "unit-b" else RUNNER_450
        cabinets.append(
            replace(
                cabinet,
                config=replace(
                    cabinet.config,
                    depth=506,
                    openings=[replace(opening, slide_key=slide_key)],
                ),
            )
        )
        drawer = inputs.drawer_configs[f"{cabinet.name}/column-0/opening-0"]
        drawer.opening_depth = 500
        drawer.slide_key = slide_key
    return replace(
        inputs, native_project=replace(inputs.native_project, cabinets=tuple(cabinets))
    )


def test_two_cabinets_keep_distinct_runner_profiles(linked_row_project):
    inputs = _mixed_inputs(linked_row_project)
    calculation = calculate(inputs)
    result = calculation.result
    assert result["hardware_profile"] is None
    assert set(result["hardware_profiles"]) == {RUNNER_450, RUNNER_480}
    assert {
        drawer["cabinet_id"]: drawer["box_mm"]["depth"] for drawer in result["drawers"]
    } == {
        "unit-a": 450,
        "unit-b": 480,
    }
    assert {
        item["length_mm"]
        for item in result["hardware"]
        if item["type"] == "drawer_runner"
    } == {450, 480}
    assembly, geometry = make_geometry(calculation)
    assert len(geometry) == len(result["parts"])
    assert {part["role"] for part in result["parts"]} <= set(assembly.objects)
    snapshot = native_snapshot(inputs)
    assert set(snapshot["hardware_profiles"]) == {RUNNER_450, RUNNER_480}


def test_unsupported_runner_profile_is_rejected(linked_row_project):
    inputs = _mixed_inputs(linked_row_project)
    inputs.drawer_configs["unit-a/column-0/opening-0"].slide_key = "unknown_slide"
    with pytest.raises(InputError) as error:
        calculate(inputs)
    assert error.value.code == "unsupported_drawer_profile"


def test_480_runner_checks_usable_cavity_depth(linked_row_project):
    inputs = _mixed_inputs(linked_row_project)
    cabinets = tuple(
        replace(cabinet, config=replace(cabinet.config, depth=498))
        for cabinet in inputs.native_project.cabinets
    )
    for drawer in inputs.drawer_configs.values():
        drawer.opening_depth = 492
    inputs = replace(
        inputs, native_project=replace(inputs.native_project, cabinets=cabinets)
    )
    with pytest.raises(InputError) as error:
        calculate(inputs)
    assert error.value.code == "invalid_drawer_config"
    assert "at least 493 mm" in str(error.value)
