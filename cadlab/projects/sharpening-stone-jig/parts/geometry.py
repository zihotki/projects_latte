"""Millimetres, Z up; stone length follows Y. No project parameter state here."""

import math

import cadquery as cq

TOP_CHAMFER = 0.5


def holder(length, width, height, pocket_length, pocket_width, pocket_depth):
    body = cq.Workplane("XY").box(width, length, height, centered=(True, True, False))
    body = body.edges("|Z").fillet(3.0)
    pocket = cq.Workplane("XY", origin=(0, 0, height - pocket_depth)).box(
        pocket_width, pocket_length, pocket_depth + 0.2, centered=(True, True, False)
    )
    body = body.cut(pocket)
    notch = (
        cq.Workplane("XZ", origin=(0, -pocket_length / 2 + 2, height))
        .circle(8)
        .extrude((length - pocket_length) / 2 + 4)
    )
    return body.cut(notch).faces(">Z").edges().chamfer(TOP_CHAMFER)


def guide(base_width, pocket_width, exposure, fit, run, angle):
    """A rail-supported angle gauge. Bearing feet at Z=0, skirts below it."""
    skirt, drop, air, skin = 2.4, 4.0, 0.4, 1.6
    inside = base_width + 2 * fit
    width = inside + 2 * skirt
    front, back = -run / 2, run / 2
    low = exposure + air + skin
    rise = run * math.tan(math.radians(angle))
    body = (
        cq.Workplane("YZ")
        .polyline([(front, -drop), (back, -drop), (back, low + rise), (front, low)])
        .close()
        .extrude(width)
        .translate((-width / 2, 0, 0))
    )
    # The wide opening clears the holder; two feet bear on the side rims.
    body = body.cut(
        cq.Workplane("XY", origin=(0, 0, -drop - 0.2)).box(
            inside, run + 0.4, drop + 0.2, centered=(True, True, False)
        )
    )
    # A higher central opening clears the plate, including lateral stone play.
    body = body.cut(
        cq.Workplane("XY", origin=(0, 0, -drop - 0.2)).box(
            pocket_width + 2 * fit,
            run + 0.4,
            drop + 0.2 + exposure + air,
            centered=(True, True, False),
        )
    )
    theta = math.radians(angle)
    normal = (0, -math.sin(theta), math.cos(theta))
    center = (0, 0, low + rise / 2)
    label_plane = cq.Plane(origin=center, xDir=(1, 0, 0), normal=normal)
    label = cq.Workplane(label_plane).text(f"{angle:g} deg", 6, -0.6, combine=False)
    return body.cut(label)


def fit_coupon(pocket_width, pocket_depth, rim):
    """A short pocket end that tests stone width and surface exposure."""
    length, floor = 30.0, 3.0
    width = pocket_width + 2 * rim
    body = cq.Workplane("XY").box(
        width, length, floor + pocket_depth, centered=(True, False, False)
    )
    pocket = cq.Workplane("XY", origin=(0, rim, floor)).box(
        pocket_width, length, pocket_depth + 0.2, centered=(True, False, False)
    )
    return body.cut(pocket).faces(">Z").edges().chamfer(TOP_CHAMFER)


def print_pose(shape, angle, x, y):
    """Put the guide's inclined top face on the bed, with its opening upwards."""
    shape = shape.rotate((0, 0, 0), (1, 0, 0), 180 - angle)
    bb = shape.val().BoundingBox()
    return shape.translate((x - bb.center.x, y - bb.center.y, -bb.zmin))


def valid_solid(shape, name):
    assert shape.val().isValid(), f"{name}: invalid geometry"
    assert len(shape.solids().vals()) == 1, f"{name}: expected one solid"
    assert shape.val().Volume() > 0, f"{name}: empty geometry"


def overlap(a, b):
    return sum(s.Volume() for s in a.val().intersect(b.val()).Solids())
