"""Removable stone holder and rail-supported angle gauges. Units: mm, Z up."""

import cadquery as cq
from parts.geometry import fit_coupon, guide, holder, overlap, print_pose, valid_solid
from soma import add_part, param

# The measured stone drives the pocket. Its support plane stays horizontal;
# the rim stays EXPOSURE below the plate surface as stack dimensions change.
STONE_LENGTH = param(170.0, "Stone length", min=140, max=200, unit="mm", group="Stone")
STONE_WIDTH = param(75.0, "Stone width", min=60, max=90, unit="mm", group="Stone")
PLATE = param(
    1.0, "Plate thickness", min=0.8, max=2, step=0.1, unit="mm", group="Stone"
)
FOAM = param(
    5.0, "Firm foam thickness", min=3, max=7, step=0.1, unit="mm", group="Stone"
)
EXPOSURE = param(
    1.0, "Surface above rim", min=0.5, max=1.5, step=0.1, unit="mm", group="Fit"
)
FIT = param(
    0.3,
    "Stone clearance per side",
    min=0.15,
    max=0.6,
    step=0.05,
    unit="mm",
    group="Fit",
)
BASE_HEIGHT = param(30.0, "Base height", min=15, max=40, unit="mm", group="Holder")
RIM = param(9.7, "Rim width", min=6, max=12, step=0.1, unit="mm", group="Holder")
ANGLE_A = param(
    15.0, "Guide A angle per side", min=10, max=25, step=1, unit="deg", group="Guides"
)
ANGLE_B = param(
    20.0, "Guide B angle per side", min=10, max=25, step=1, unit="deg", group="Guides"
)
GUIDE_RUN = param(28.0, "Guide ramp length", min=20, max=35, unit="mm", group="Guides")
GUIDE_FIT = param(
    0.3,
    "Guide clearance per side",
    min=0.15,
    max=0.6,
    step=0.05,
    unit="mm",
    group="Guides",
)
LAYOUT = param("Assembly", "Layout", options=["Assembly", "Print"], group="Display")
REFERENCES = param(True, "Show stone and foam", group="Display")
COUPON = param(False, "Include fit coupon", group="Display")

POCKET_LENGTH = STONE_LENGTH + 2 * FIT
POCKET_WIDTH = STONE_WIDTH + 2 * FIT
POCKET_DEPTH = PLATE + FOAM - EXPOSURE
OUTER_LENGTH = POCKET_LENGTH + 2 * RIM
OUTER_WIDTH = POCKET_WIDTH + 2 * RIM
SUPPORT_Z = BASE_HEIGHT - POCKET_DEPTH
STONE_Z = BASE_HEIGHT + EXPOSURE
assert POCKET_DEPTH > 0, "Surface exposure must be less than the stone stack thickness"
assert SUPPORT_Z >= 3, "Increase base height to retain at least a 3 mm floor"
assert OUTER_LENGTH <= 256 and OUTER_WIDTH <= 256, "Holder exceeds the A1 build area"

base = holder(
    OUTER_LENGTH, OUTER_WIDTH, BASE_HEIGHT, POCKET_LENGTH, POCKET_WIDTH, POCKET_DEPTH
)
foam = cq.Workplane("XY", origin=(0, 0, SUPPORT_Z)).box(
    STONE_WIDTH, STONE_LENGTH, FOAM, centered=(True, True, False)
)
plate = cq.Workplane("XY", origin=(0, 0, SUPPORT_Z + FOAM)).box(
    STONE_WIDTH, STONE_LENGTH, PLATE, centered=(True, True, False)
)
gauges = [
    guide(OUTER_WIDTH, POCKET_WIDTH, EXPOSURE, GUIDE_FIT, GUIDE_RUN, a)
    for a in (ANGLE_A, ANGLE_B)
]
for name, shape in [("Holder", base), ("Guide A", gauges[0]), ("Guide B", gauges[1])]:
    valid_solid(shape, name)

if LAYOUT == "Print":
    guide_x = OUTER_WIDTH + GUIDE_FIT + 2.4 + 10
    placed = [
        print_pose(g, a, guide_x, y)
        for g, a, y in zip(
            gauges,
            (ANGLE_A, ANGLE_B),
            (-STONE_LENGTH / 4, STONE_LENGTH / 4),
            strict=True,
        )
    ]
else:
    placed = [
        g.translate((0, y, BASE_HEIGHT))
        for g, y in zip(gauges, (-STONE_LENGTH / 4, STONE_LENGTH / 4), strict=True)
    ]
    for g in placed:
        assert overlap(base, g) < 1e-5, "Guide intersects holder"
        assert overlap(plate, g) < 1e-5, "Guide intersects plate"
        assert overlap(foam, g) < 1e-5, "Guide intersects foam"

printed = [
    ("Holder", base),
    (f"Guide A {ANGLE_A:g} deg", placed[0]),
    (f"Guide B {ANGLE_B:g} deg", placed[1]),
]
if COUPON:
    coupon = fit_coupon(POCKET_WIDTH, POCKET_DEPTH, RIM)
    cb = coupon.val().BoundingBox()
    if LAYOUT == "Print":
        # Give the coupon a row below both guides, using their actual extents.
        y = min(g.val().BoundingBox().ymin for g in placed) - 10 - cb.ymax
        x = guide_x
    else:
        x, y = OUTER_WIDTH + 10, -cb.ylen / 2
    coupon = coupon.translate((x, y, 0))
    valid_solid(coupon, "Fit coupon")
    printed.append(("Fit coupon", coupon))

if LAYOUT == "Print":
    bounds = [shape.val().BoundingBox() for _, shape in printed]
    assert max(b.xmax for b in bounds) - min(b.xmin for b in bounds) <= 256, (
        "Print layout too wide for A1"
    )
    assert max(b.ymax for b in bounds) - min(b.ymin for b in bounds) <= 256, (
        "Print layout too long for A1"
    )
    assert all(abs(b.zmin) < 1e-5 for b in bounds), "A print part is off the bed"
    for i, (_, a) in enumerate(printed):
        for _, b in printed[i + 1 :]:
            assert overlap(a, b) < 1e-5, "Print parts overlap"

for name, shape in printed:
    add_part(name, shape)
if REFERENCES and LAYOUT == "Assembly":
    add_part("Firm foam", foam, color=(0.15, 0.15, 0.15), role="reference", alpha=1)
    add_part(
        "Sharpening plate", plate, color=(0.6, 0.65, 0.7), role="reference", alpha=1
    )
