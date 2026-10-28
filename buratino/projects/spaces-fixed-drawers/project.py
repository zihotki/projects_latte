"""Two fixed-height drawer spaces with explicitly attached applied fronts."""

from cabineteer.hettich_eb20 import EB20_SLIDE_KEYS
from cabineteer.project import CabinetProject, SpaceModelSpec
from cabineteer.spaces import (
    AppliedDrawerFront,
    Carcass,
    Divider,
    DrawerBox,
    Fixed,
    Fr,
    Space,
    Split,
)

variables = {
    "observations": ["Example dimensions are design inputs, not site measurements."],
    "assumptions": [
        "The 480 mm Hettich Quadro V6 EB20 selection is illustrative.",
        "Applied fronts use a nominal 2 mm reveal. Confirm mounting and clearances.",
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
_root = Space(
    "root",
    split=Split(
        axis="height",
        children=(
            Space(
                "lower", Fixed(240), content=DrawerBox("box-lower", **_drawer_recipe)
            ),
            Space(
                "upper", Fixed(240), content=DrawerBox("box-upper", **_drawer_recipe)
            ),
            Divider("adjustable-shelf", role="adjustable", recess=3),
            Space("open", Fr(1)),
        ),
    ),
)

project = CabinetProject(
    name="spaces-fixed-drawers",
    space_model=SpaceModelSpec(
        carcass=Carcass(
            width=720,
            height=936,
            depth=550,
            side_thickness=18,
            bottom_thickness=18,
            top_thickness=18,
            back_thickness=6,
            material="plywood",
            back_material="plywood",
        ),
        root=_root,
        fronts=(
            AppliedDrawerFront(
                "lower-front",
                covers="/root/lower",
                attached_to="/root/lower/box-lower",
                thickness=18,
                material="plywood",
            ),
            AppliedDrawerFront(
                "upper-front",
                covers="/root/upper",
                attached_to="/root/upper/box-upper",
                thickness=18,
                material="plywood",
            ),
        ),
    ),
)
