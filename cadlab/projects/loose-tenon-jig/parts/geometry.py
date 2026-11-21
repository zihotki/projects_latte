"""Guide geometry in millimetres. Each plate starts with its work face at Z = 0."""

from math import sqrt

import cadquery as cq

STOCK = 18.0
TENON_THICKNESS, TENON_WIDTH, TENON_LENGTH = 6.0, 30.0, 30.0
PLATE = 12.0
FACE_NEAR, FACE_MID = STOCK / 2, 99.0
EDGE_NEAR = -STOCK / 2
FACE_LENGTH_ALLOWANCE = 2.0
MAX_SLOT_ALLOWANCE = 0.50
BODY_HALF, WING_HALF, FACE_BACK = 82.0, 118.0, 180.0
FENCE_HALF, FENCE_BACK = 78.0, -116.0
TONGUE_HALF, TONGUE_CLEARANCE, TONGUE_CORNER_CHAMFER = 35.0, 0.08, 0.60

PIN_AXIS = 42.0
PIN_DIAMETER, PIN_PROJECTION = 5.0, 8.0
PIN_HEAD, PIN_HEAD_DEPTH, PIN_STEM = 8.0, 2.0, 5.0
PIN_HEAD_CLEARANCE = 0.25
DEPTH_GAUGE_REACH = PLATE + TENON_LENGTH / 2
DEPTH_GAUGE_DIAMETRAL_FIT, DEPTH_GAUGE_AXIAL_FIT = 0.4, 0.5
DEPTH_GAUGE_SHOULDER = 2.0
GAUGE_MARK_RUN = 3.0
GAUGE_CORNER_RADIUS = 0.75

L_JOINT_X = (-58.0, 58.0)
LOCATOR_SPACING = 12.0
LOCATOR_X = tuple(x + offset for x in L_JOINT_X for offset in (-LOCATOR_SPACING, LOCATOR_SPACING))
LOCATOR_DATUM_X = L_JOINT_X[-1] - LOCATOR_SPACING
LOCATOR_WIDTH, LOCATOR_LENGTH, LOCATOR_HEIGHT = 7.0, 6.0, 1.5
LOCATOR_FIT, LOCATOR_DEPTH_RELIEF, LOCATOR_SIDE_RELIEF = 0.08, 0.25, 0.25

A1, BRIM = 256.0, 4.0
BED_CHAMFER, CORNER_RADIUS = 0.50, 3.0
TOP_CHAMFER = 0.40
BED_SEAT_HALF_WIDTH, OPENING_CHAMFER = 0.80, 0.45
EDGE_RUNOUT = 6.0
CUT_MARGIN = 0.2
MARK_WIDTH, FACE_MARK_DEPTH = 0.60, 0.60
SLOT_MARK_WIDTH, SLOT_MARK_DEPTH = 0.90, 0.60
BARREL_MARK_CLEARANCE = 0.10
MIN_SEAM_MARK_WEB = 0.80
SCREW_DIAMETER, SCREW_LENGTH = 4.0, 30.0
SCREW_HEAD_DIAMETER, SCREW_HEAD_RECESS = 7.9, 0.20
SCREW_CLEARANCE_DIAMETER, SCREW_PILOT_DIAMETER = 4.3, 3.2
SCREW_PILOT_DEPTH = SCREW_LENGTH - PLATE + 2.0
SCREW_TIP_LENGTH = 3.0


def cylinder(diameter, x, y, start, depth):
    return cq.Workplane("XY", origin=(x, y, start)).circle(diameter / 2).extrude(depth)


def box(width, length, height, x, y, z):
    return (cq.Workplane("XY", origin=(x, y, z))
            .box(width, length, height, centered=(True, True, False)))


def slot_dimensions(bushing_diameter, cutter_diameter, allowance):
    offset = bushing_diameter - cutter_diameter + allowance
    return TENON_THICKNESS + offset, TENON_WIDTH + offset


def chamfered_slot(width, length, y):
    # Extend the bevels outside both faces so the cutters pass through the plate.
    relief = OPENING_CHAMFER + CUT_MARGIN
    sections = ((-CUT_MARGIN, relief), (OPENING_CHAMFER, 0),
                (PLATE - OPENING_CHAMFER, 0), (PLATE + CUT_MARGIN, relief))
    profiles = []
    for z, offset in sections:
        x_half, y_half = length / 2 + offset, width / 2 + offset
        wire = cq.Wire.makePolygon([(-x_half, y - y_half, z), (x_half, y - y_half, z),
                                    (x_half, y + y_half, z), (-x_half, y + y_half, z)], close=True)
        profiles.append(wire.fillet2D(2.5 + offset, wire.Vertices()))
    return cq.Solid.makeLoft(profiles, ruled=True)


def rounded_profile(points, square_corners, small_corners):
    wire = cq.Wire.makePolygon([(x, y, 0) for x, y in points], close=True)
    round_corners = [vertex for vertex in wire.Vertices()
                     if (vertex.X, vertex.Y) not in square_corners + small_corners]
    wire = wire.fillet2D(CORNER_RADIUS, round_corners)
    if small_corners:
        wire = wire.fillet2D(GAUGE_CORNER_RADIUS, [v for v in wire.Vertices() if (v.X, v.Y) in small_corners])
    return wire


def preserve_bed_seat(part, original, y, half_width, inward):
    end = half_width + EDGE_RUNOUT
    land = box(2 * end, 2 * BED_SEAT_HALF_WIDTH, BED_CHAMFER + CUT_MARGIN, 0, y, -CUT_MARGIN)
    part = part.union(original.intersect(land))

    # Restore the full seat, then taper into the perimeter bevel at both ends.
    profiles = []
    outside = y - inward * CUT_MARGIN
    for x, bevel in ((half_width, 0), (end, BED_CHAMFER), (end + CUT_MARGIN, BED_CHAMFER)):
        relief = bevel + CUT_MARGIN
        profiles.append(cq.Wire.makePolygon([(x, outside, -CUT_MARGIN),
                                            (x, y + inward * relief, -CUT_MARGIN),
                                            (x, outside, relief)], close=True))
    runout = cq.Solid.makeLoft(profiles, ruled=True)
    return part.cut(runout).cut(runout.mirror("YZ"))


def plate_blank(points, *, square_corners=(), small_corners=()):
    profile = rounded_profile(points, square_corners, small_corners)
    return cq.Workplane(obj=cq.Solid.extrudeLinear(profile, [], (0, 0, PLATE)))


def chamfer_rim(plate, mating_edge=None):
    beveled = plate.faces("<Z").edges().chamfer(BED_CHAMFER).faces(">Z").edges().chamfer(TOP_CHAMFER)
    if mating_edge is not None:
        beveled = preserve_bed_seat(beveled, plate, *mating_edge)
    return beveled


def outline(points):
    return chamfer_rim(plate_blank(points))


def edge_position(part):
    return part.rotate((0, 0, 0), (1, 0, 0), 90)


def edge_flat(part):
    return part.rotate((0, 0, 0), (1, 0, 0), -90)


def locator(x, y, clearance=0, side_relief=0, depth_relief=0):
    # The tapered sides center the joint and grow at 45° in the print direction.
    heights = (-CUT_MARGIN, LOCATOR_HEIGHT)
    if depth_relief:
        heights += (LOCATOR_HEIGHT + depth_relief,)
    profiles = []
    for height in heights:
        offset = clearance - min(height, LOCATOR_HEIGHT)
        profile = cq.Workplane("XY", origin=(x, y, height)).rect(LOCATOR_WIDTH + 2 * (offset + side_relief),
                                                                LOCATOR_LENGTH + 2 * offset).val()
        profiles.append(profile)
    return cq.Solid.makeLoft(profiles, ruled=True)


def locating_pockets(y, *, locate_x=False):
    # One snug pocket fixes X on the mitre jig. The tongue already fixes X on the square jig.
    return [locator(x, y, LOCATOR_FIT, 0 if locate_x and x == LOCATOR_DATUM_X else LOCATOR_SIDE_RELIEF,
                    LOCATOR_DEPTH_RELIEF) for x in LOCATOR_X]


def screw(x, y):
    # Nominal envelope of a 4 × 30 mm wood screw with a 90° countersunk head.
    top = PLATE - SCREW_HEAD_RECESS
    head_height = (SCREW_HEAD_DIAMETER - SCREW_DIAMETER) / 2
    neck = top - head_height
    point = top - SCREW_LENGTH
    tip = cq.Solid.makeCone(0, SCREW_DIAMETER / 2, SCREW_TIP_LENGTH, (x, y, point))
    shank = cylinder(SCREW_DIAMETER, x, y, point + SCREW_TIP_LENGTH,
                      neck - point - SCREW_TIP_LENGTH).val()
    head = cq.Solid.makeCone(SCREW_DIAMETER / 2, SCREW_HEAD_DIAMETER / 2, head_height, (x, y, neck))
    return shank.fuse(tip, head)


def screw_clearance(x, y):
    # The complete screw passes through the first plate. Only its head seats here.
    bore_radius = SCREW_CLEARANCE_DIAMETER / 2
    mouth_radius = SCREW_HEAD_DIAMETER / 2 + SCREW_HEAD_RECESS
    seat_depth = mouth_radius - bore_radius
    bore = cylinder(SCREW_CLEARANCE_DIAMETER, x, y, -CUT_MARGIN, PLATE + 2 * CUT_MARGIN).val()
    seat = cq.Solid.makeCone(bore_radius, mouth_radius + CUT_MARGIN,
                             seat_depth + CUT_MARGIN, (x, y, PLATE - seat_depth))
    return bore.fuse(seat)


def screw_pilot(x, y):
    return cylinder(SCREW_PILOT_DIAMETER, x, y, -SCREW_PILOT_DEPTH, SCREW_PILOT_DEPTH + CUT_MARGIN)


def hole_lead_in(diameter, x, y):
    height = OPENING_CHAMFER + CUT_MARGIN
    return cq.Solid.makeCone(diameter / 2 + height, diameter / 2, height, (x, y, -CUT_MARGIN))


def cut_pin_seats(plate, y, pin_fit):
    for x in (-PIN_AXIS, PIN_AXIS):
        seat_diameter = PIN_HEAD + PIN_HEAD_CLEARANCE
        plate = plate.cut(cylinder(PIN_DIAMETER + pin_fit, x, y, -CUT_MARGIN,
                                   PIN_HEAD_DEPTH + PIN_STEM + 0.35 + CUT_MARGIN))
        plate = plate.cut(cylinder(seat_diameter, x, y, -CUT_MARGIN, PIN_HEAD_DEPTH + 0.2 + CUT_MARGIN))
        plate = plate.cut(hole_lead_in(seat_diameter, x, y))
    return plate


def gauge_outline(bushing_diameter, bushing_projection):
    # Include the notch in the outer profile so its rim chamfer follows the entire opening.
    half_mouth = max((bushing_diameter + DEPTH_GAUGE_DIAMETRAL_FIT) / 2, TENON_WIDTH / 2 + DEPTH_GAUGE_SHOULDER)
    half_throat = TENON_WIDTH / 2
    shoulder = FACE_BACK - bushing_projection - DEPTH_GAUGE_AXIAL_FIT
    stop = FACE_BACK - DEPTH_GAUGE_REACH
    return ((half_mouth, FACE_BACK), (half_mouth, shoulder), (half_throat, shoulder), (half_throat, stop),
            (-half_throat, stop), (-half_throat, shoulder), (-half_mouth, shoulder), (-half_mouth, FACE_BACK))


def tongue_side(inset=0, clearance=0, overrun=0):
    # Offset the two 45° segments by the same normal distance as the flat flank.
    half = TONGUE_HALF + clearance - inset
    diagonal = (sqrt(2) - 1) * (clearance - inset)
    corner = TONGUE_CORNER_CHAMFER
    return ((half - corner + diagonal - overrun, -PLATE - overrun),
            (half, -PLATE + corner - diagonal), (half, -corner - diagonal),
            (half + corner + diagonal + overrun, overrun))


def face_blank(right_tongue, gauge):
    left_tongue = tuple((-x, y) for x, y in reversed(right_tongue))
    return plate_blank((*right_tongue, (WING_HALF, 0), (WING_HALF, 40),
                        (BODY_HALF, 64), (BODY_HALF, FACE_BACK), *gauge, (-BODY_HALF, FACE_BACK),
                        (-BODY_HALF, 64), (-WING_HALF, 40), (-WING_HALF, 0), *left_tongue),
                       square_corners=right_tongue + left_tongue, small_corners=gauge)


def make_face(slot_width, loose_length, bushing_diameter, bushing_projection, pin_fit):
    gauge = gauge_outline(bushing_diameter, bushing_projection)
    stock_half = TONGUE_HALF + TONGUE_CORNER_CHAMFER
    blank = face_blank(((stock_half, -PLATE), (stock_half, 0)), gauge)
    body = blank
    for x in LOCATOR_X:
        body = body.union(edge_position(locator(x, PLATE / 2)))
    body = body.cut(chamfered_slot(slot_width, loose_length, FACE_MID))
    body = cut_pin_seats(body, FACE_NEAR, pin_fit)
    for x in L_JOINT_X:
        body = body.cut(edge_position(screw_pilot(x, PLATE / 2)))
    finished = chamfer_rim(face_blank(tongue_side(), gauge))
    return body, blank.val().cut(finished.val())


def make_edge(pin_fit):
    blank = plate_blank(((-FENCE_HALF, FENCE_BACK), (FENCE_HALF, FENCE_BACK),
                         (FENCE_HALF, PLATE), (-FENCE_HALF, PLATE)))
    # Build the seat from the finished tongue sections, then turn it into the fence's print frame.
    sections = ((0, BED_CHAMFER), (BED_CHAMFER, 0), (PLATE - TOP_CHAMFER, 0), (PLATE, TOP_CHAMFER))
    profiles = []
    for z, inset in sections:
        side = tongue_side(inset, TONGUE_CLEARANCE, CUT_MARGIN)
        points = (*side, *((-x, y) for x, y in reversed(side)))
        profiles.append(cq.Wire.makePolygon([(x, y, z) for x, y in points], close=True))
    edge = blank.cut(edge_flat(cq.Solid.makeLoft(profiles, ruled=True)))
    for pocket in locating_pockets(PLATE / 2):
        edge = edge.cut(pocket)
    edge = cut_pin_seats(edge, EDGE_NEAR, pin_fit)
    for x in L_JOINT_X:
        edge = edge.cut(screw_clearance(x, PLATE / 2))
    mating_edge = (PLATE, FENCE_HALF - CORNER_RADIUS - EDGE_RUNOUT, -1)
    return edge, blank.val().cut(chamfer_rim(blank, mating_edge).val())


def join_guides(face, edge, slot_width, snug_length):
    # Machine both seam apertures in the assembled frame. At larger diameters
    # each half contributes a wall to the near slot of the other half.
    near_face = chamfered_slot(slot_width, snug_length + FACE_LENGTH_ALLOWANCE, FACE_NEAR)
    near_edge = edge_position(chamfered_slot(slot_width, snug_length, EDGE_NEAR))
    return face.cut(near_face).cut(near_edge), edge.cut(near_face).cut(near_edge)


def slot_mark_tool(height):
    # The triangular groove tapers to the slot wall (Y = 0) as the layers rise.
    # Extend its back into the slot and its base below the work face for the cut.
    wall_half_width = SLOT_MARK_WIDTH / 2
    base_half_width = wall_half_width * (1 + CUT_MARGIN / SLOT_MARK_DEPTH)
    tip_half_width = wall_half_width
    extra = CUT_MARGIN / height
    low_half_width = base_half_width + extra * (base_half_width - tip_half_width)
    low_depth = SLOT_MARK_DEPTH * (1 + extra)
    lower = cq.Wire.makePolygon([(-low_half_width, -CUT_MARGIN, -CUT_MARGIN),
                                 (low_half_width, -CUT_MARGIN, -CUT_MARGIN),
                                 (0, low_depth, -CUT_MARGIN)], close=True)
    upper = cq.Wire.makePolygon([(-tip_half_width, -CUT_MARGIN, height),
                                 (tip_half_width, -CUT_MARGIN, height),
                                 (0, 0, height)], close=True)
    return cq.Solid.makeLoft([lower, upper], ruled=True)


def alignment_groove(length):
    # The face is at Z = 0. Extend the V beyond it to cut cleanly through the surface.
    half_width = MARK_WIDTH / 2 * (1 + CUT_MARGIN / FACE_MARK_DEPTH)
    start = -length / 2
    profile = cq.Wire.makePolygon([(-half_width, start, CUT_MARGIN),
                                  (half_width, start, CUT_MARGIN),
                                  (0, start, -FACE_MARK_DEPTH)], close=True)
    return cq.Solid.extrudeLinear(profile, [], (0, length, 0))


def marking_tools(front, back, end_marks, rows, slot_width, slot_length, wall_height, omitted_wall=None):
    origin, up = (0, 0, 0), (0, 0, 1)
    top_line = alignment_groove(back - front + 2 * CUT_MARGIN)
    cuts = [top_line.translate((0, (front + back) / 2, PLATE))]
    upright_line = alignment_groove(PLATE + 2 * CUT_MARGIN).rotate(origin, (1, 0, 0), 90)
    for end, interior in end_marks:
        end_line = upright_line.rotate(origin, up, 90 * (1 - interior))
        cuts.append(end_line.translate((0, end, PLATE / 2)))

    mark = slot_mark_tool(wall_height)
    for y, half_width in rows:
        cross_line = alignment_groove(2 * (half_width + CUT_MARGIN)).rotate(origin, up, 90)
        cuts.append(cross_line.translate((0, y, PLATE)))
        for side in (-1, 1):
            side_line = upright_line.rotate(origin, up, 90 * side)
            cuts.append(side_line.translate((side * half_width, y, PLATE / 2)))
            cuts.append(mark.rotate(origin, up, -90 * side).translate((side * slot_length / 2, y, 0)))
            if (y, side) != omitted_wall:
                cuts.append(mark.rotate(origin, up, 90 * (1 - side)).translate((0, y + side * slot_width / 2, 0)))
    return cuts


def gauge_marks():
    # The lower stop mark wraps onto the underside, between the two flat shoulders.
    stop = FACE_BACK - DEPTH_GAUGE_REACH
    gauge_line_height = PLATE / 2 + CUT_MARGIN
    gauge_line = alignment_groove(gauge_line_height).rotate((0, 0, 0), (1, 0, 0), -90)
    underside_line = alignment_groove(GAUGE_MARK_RUN + 2 * CUT_MARGIN).rotate((0, 0, 0), (0, 1, 0), 180)
    return [gauge_line.translate((0, stop, gauge_line_height / 2 - CUT_MARGIN)),
            underside_line.translate((0, stop - GAUGE_MARK_RUN / 2, 0))]


def mark_guides(face, edge, slot_width, snug_length, projection):
    wall_height = min(PLATE / 2, PLATE - projection - BARREL_MARK_CLEARANCE)
    top_mark_end = FACE_BACK - DEPTH_GAUGE_REACH - MARK_WIDTH - CUT_MARGIN
    face_tools = marking_tools(-PLATE, top_mark_end, ((-PLATE, 1),),
                               ((FACE_NEAR, WING_HALF), (FACE_MID, BODY_HALF)),
                               slot_width, snug_length + FACE_LENGTH_ALLOWANCE, wall_height)
    face_tools.extend(gauge_marks())

    # Keep the thin rib at the tongue seat solid when a groove would weaken it.
    seam_web = -(EDGE_NEAR + slot_width / 2)
    omit_wall = (EDGE_NEAR, 1) if 1e-9 < seam_web < MIN_SEAM_MARK_WEB + SLOT_MARK_DEPTH - 1e-9 else None
    edge_tools = marking_tools(FENCE_BACK, PLATE, ((FENCE_BACK, 1),),
                               ((EDGE_NEAR, FENCE_HALF),),
                               slot_width, snug_length, wall_height, omitted_wall=omit_wall)
    tools = [*face_tools, *(edge_position(tool) for tool in edge_tools)]
    face = cq.Workplane(obj=face.val().cut(*tools))
    edge = cq.Workplane(obj=edge.val().cut(*tools))
    return face, edge


def make_pin():
    pin = cylinder(PIN_DIAMETER, 0, 0, -PIN_PROJECTION, PIN_PROJECTION + PIN_HEAD_DEPTH + PIN_STEM)
    # Grow the collar at 45° from the stem, then leave its seating shoulder flat.
    ramp_height = (PIN_HEAD - PIN_DIAMETER) / 2
    ramp = cq.Solid.makeCone(PIN_DIAMETER / 2, PIN_HEAD / 2, ramp_height)
    collar = cylinder(PIN_HEAD, 0, 0, ramp_height, PIN_HEAD_DEPTH - ramp_height)
    return pin.union(ramp).union(collar).faces("<Z").edges().chamfer(BED_CHAMFER)


def square_stock(end_x):
    return box(175, 155, STOCK, end_x + 175 / 2, 155 / 2, -STOCK)


def position_on_bed(part, x, y):
    bounds = part.val().BoundingBox()
    return part.translate((x - bounds.xmin, y - bounds.ymin, -bounds.zmin))
