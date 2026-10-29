"""A maple drawer cabinet with explicit, CAD-independent machining records."""

from cabineteer.hettich_eb20 import EB20_SLIDE_KEYS
from cabineteer.operations import Bevel, Bore, DominoJoint, Pocket, Rabbet
from cabineteer.project import CabinetProject, SpaceModelSpec
from cabineteer.spaces import Carcass, DrawerBox, Space

variables = {
    "observations": ["All dimensions are example design inputs, not site measurements."],
    "assumptions": [
        "The 380 mm Hettich Quadro V6 EB20 slide is an illustrative selection.",
        "The resolved mortise dimensions describe one proposed loose-tenon pair.",
        "Confirm the stock, joinery, hardware fit, and installation before use.",
    ],
}
calculated = {}

project = CabinetProject(
    name="machined-drawer",
    space_model=SpaceModelSpec(
        carcass=Carcass(
            width=720,
            height=600,
            depth=420,
            side_thickness=18,
            bottom_thickness=18,
            top_thickness=18,
            back_thickness=6,
            material="maple",
            back_material="maple",
        ),
        root=Space(
            "root",
            content=DrawerBox(
                name="drawer",
                bottom_clearance=30,
                height=260,
                slide_key=EB20_SLIDE_KEYS[380],
                side_thickness=16,
                front_back_thickness=18,
                bottom_thickness=12,
                bottom_dado_depth=6,
                bottom_dado_inset=13,
                joinery_style="butt",
                material="maple",
                bottom_material="maple",
            ),
        ),
    ),
    operations=(
        Pocket(
            id="drawer-bottom-relief",
            part_id="/cabinet/root/drawer/bottom",
            face="z+",
            u=250,
            v=180,
            size_u=80,
            size_v=30,
            depth=2,
        ),
        Rabbet(
            id="rear-side-rabbet",
            part_id="/cabinet/carcass/side_left",
            face="x+",
            edge="y+",
            start=100,
            length=200,
            width=6,
            depth=4,
        ),
        Bevel(
            id="top-edge-bevel",
            part_id="/cabinet/carcass/side_right",
            face="x+",
            edge="z+",
            start=50,
            length=160,
            leg_a=6,
            leg_b=4,
        ),
        Bore(
            id="side-edge-bore",
            part_id="/cabinet/carcass/side_left",
            face="x-",
            u=300,
            v=250,
            diameter=5,
            depth=10,
        ),
        Bore(
            id="back-face-bore",
            part_id="/cabinet/carcass/back",
            face="y-",
            u=360,
            v=300,
            diameter=4,
            depth=6,
        ),
    ),
    joints=(
        DominoJoint(
            id="side-to-back",
            part_a="/cabinet/carcass/side_left",
            face_a="y+",
            part_b="/cabinet/carcass/back",
            face_b="y-",
            centre=(9, 414, 80),
            axis="z",
            length=40,
            width=8,
            depth_a=4,
            depth_b=4,
        ),
    ),
)
