"""A bare insert and a complete cabinet inside one host cabinet."""

from cabineteer.hettich_eb20 import EB20_SLIDE_KEYS
from cabineteer.layout import CabinetRef, Row
from cabineteer.project import CabinetProject, SpaceModelSpec
from cabineteer.spaces import (
    AssemblyModule,
    AssemblyRef,
    Carcass,
    Divider,
    Door,
    DrawerBox,
    Fixed,
    Fr,
    Insets,
    Space,
    SpaceCabinetDefinition,
    Split,
)

variables = {
    "observations": ["Example dimensions are design inputs, not site measurements."],
    "assumptions": [
        "The nested cabinet's 480 mm Hettich Quadro V6 EB20 selection is illustrative.",
        "The host has 2 mm front gaps and reveal.",
        "Check the nested cabinet's mounting and support before construction.",
    ],
}
calculated = {}

_drawer_recipe = {
    "bottom_clearance": 30,
    "height": "fit",
    "slide_key": EB20_SLIDE_KEYS[480],
    "side_thickness": 16,
    "front_back_thickness": 18,
    "bottom_thickness": 12,
    "bottom_dado_depth": 6,
    "bottom_dado_inset": 13,
    "material": "plywood",
    "bottom_material": "plywood",
}

space_cabinets = (
    SpaceCabinetDefinition(
        name="complete-drawer-cabinet",
        carcass=Carcass(
            width=320,
            height=440,
            depth=520,
            side_thickness=18,
            bottom_thickness=18,
            top_thickness=18,
            back_thickness=6,
            door_gap=2,
            drawer_front_gap=2,
            outer_reveal=2,
            material="plywood",
            back_material="plywood",
        ),
        root=Space("root", content=DrawerBox("box", **_drawer_recipe)),
        fronts=(Door("nested-door", covers="/root", hinge_side="right"),),
    ),
)

space_modules = (
    AssemblyModule(
        name="bare-drawer-insert",
        root=Space(
            "insert-root",
            split=Split(
                axis="height",
                children=(
                    Space(
                        "drawer-space",
                        Fr(1),
                        content=DrawerBox("insert-box", **_drawer_recipe),
                    ),
                    Divider("insert-shelf", role="adjustable"),
                    Space("upper-space", Fr(1)),
                ),
            ),
        ),
        size_x=Fr(1),
        size_y=Fr(1),
        size_z=Fr(1),
        fronts=(),
    ),
    AssemblyModule(
        name="complete-cabinet-module",
        root=Row(
            name="complete-row",
            children=(
                CabinetRef(name="cabinet", definition="complete-drawer-cabinet"),
            ),
        ),
    ),
)

_host_root = Space(
    "host-root",
    split=Split(
        axis="width",
        children=(
            Space(
                "bare-slot",
                Fixed(300),
                content=AssemblyRef(
                    name="bare-insert-instance",
                    module="bare-drawer-insert",
                    insets=Insets(left=10, right=10, top=10, bottom=10),
                ),
            ),
            Space(
                "complete-slot",
                Fr(1),
                content=AssemblyRef(
                    name="complete-cabinet-instance",
                    module="complete-cabinet-module",
                    insets=Insets(left=10, right=10, front=20, top=10, bottom=10),
                ),
            ),
        ),
    ),
)

project = CabinetProject(
    name="space-nested-inserts",
    space_model=SpaceModelSpec(
        carcass=Carcass(
            width=900,
            height=700,
            depth=620,
            side_thickness=18,
            bottom_thickness=18,
            top_thickness=18,
            back_thickness=6,
            door_gap=2,
            drawer_front_gap=2,
            outer_reveal=2,
            material="plywood",
            back_material="plywood",
        ),
        root=_host_root,
    ),
    space_cabinets=space_cabinets,
    space_modules=space_modules,
)
