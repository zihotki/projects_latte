"""A parent door covers two internal drawer boxes and an open space."""

from cabineteer.hettich_eb20 import EB20_SLIDE_KEYS
from cabineteer.project import CabinetProject, SpaceModelSpec
from cabineteer.spaces import Carcass, Door, DrawerBox, Fixed, Fr, Space, Split

variables = {
    "observations": ["Example dimensions are design inputs, not site measurements."],
    "assumptions": [
        "The 480 mm Hettich Quadro V6 EB20 selection is illustrative.",
        "Hinge mounting and door-to-drawer clearance are not checked in this example.",
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
                "middle", Fixed(360), content=DrawerBox("box-middle", **_drawer_recipe)
            ),
            Space("open", Fr(1)),
        ),
    ),
)

project = CabinetProject(
    name="spaces-covered-drawers",
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
        fronts=(Door("parent-door", covers="/root", material="plywood"),),
    ),
)
