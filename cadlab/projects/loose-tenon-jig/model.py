"""Flat-pack face and edge guides for 6 × 30 mm loose tenons in 18 mm stock."""

from soma import add_part, param

from parts import geometry as g

# Stock datums define slot centers. The tooling parameters change the apertures
# symmetrically about those centers and cannot change the mortise positions.
bushing_diameter = param(16.0, "Guide bushing outside diameter", min=12, max=30,
                         step=0.05, unit="mm", group="Tooling")
bushing_projection = param(5.0, "Bushing projection below router base", min=3, max=8,
                           step=0.1, unit="mm", group="Tooling")
cutter_diameter = param(6.0, "Mortise cutter diameter", min=5, max=6,
                        step=0.05, unit="mm", group="Tooling")
slot_allowance = param(0.25, "Total slot fit allowance", min=0.15, max=g.MAX_SLOT_ALLOWANCE,
                       step=0.05, unit="mm", group="Fit")
pin_fit = param(0.15, "Registration pin diametral clearance", min=0.05, max=0.30,
                step=0.05, unit="mm", group="Fit")
display = param("Assembled jig", "View setup",
                options=["Assembled jig", "Face mortise", "Edge mortise",
                         "Print face plate", "Print edge fence and pins"],
                group="Display")

slot_width, snug_length = g.slot_dimensions(bushing_diameter, cutter_diameter, slot_allowance)
loose_length = snug_length + g.FACE_LENGTH_ALLOWANCE

seam_intrusion = max(0.0, slot_width / 2 - g.STOCK / 2)
maximum = g.PLATE - seam_intrusion - g.SLOT_MARK_DEPTH - g.BARREL_MARK_CLEARANCE
if bushing_projection > maximum:
    raise ValueError(f"With these slot dimensions the bushing may project at most {maximum:g} mm.")

face, face_rim_cut = g.make_face(slot_width, loose_length, bushing_diameter, bushing_projection, pin_fit)
edge, edge_rim_cut = g.make_edge(pin_fit)
face, edge = g.join_guides(face, g.edge_position(edge), slot_width, snug_length)
face, edge = g.mark_guides(face, edge, slot_width, snug_length, bushing_projection)
# Use the original outlines to finish both rims after machining the assembled guides.
face = face.cut(face_rim_cut)
edge = edge.cut(g.edge_position(edge_rim_cut))
pin = g.make_pin()

for name, part in (("Face plate", face), ("Edge fence", edge), ("Registration pin", pin)):
    if len(part.solids().vals()) != 1 or not part.val().isValid():
        raise ValueError(f"{name} must be one valid solid.")

face_color = (0.30, 0.55, 0.72)
edge_color = (0.38, 0.44, 0.48)
pin_color = (0.92, 0.57, 0.26)
stock_color = (0.77, 0.58, 0.39)

if display.startswith("Print"):
    if display == "Print face plate":
        pieces = [("Face plate", g.position_on_bed(face, g.A1 / 2 - g.WING_HALF, 30), face_color)]
    else:
        pieces = [
            ("Edge fence", g.position_on_bed(g.edge_flat(edge), 14, 20), edge_color),
            ("Registration pin 1", g.position_on_bed(pin, 192, 28), pin_color),
            ("Registration pin 2", g.position_on_bed(pin, 208, 28), pin_color),
        ]
    for name, part, color in pieces:
        bounds = part.val().BoundingBox()
        if min(bounds.xmin, bounds.ymin) < g.BRIM or max(bounds.xmax, bounds.ymax) > g.A1 - g.BRIM:
            raise ValueError(f"{name} and its 4 mm brim must fit on the A1 plate.")
        add_part(name, part, color=color)
else:
    add_part("Face plate", face, color=face_color)
    add_part("Edge fence", edge, color=edge_color)
    for number, x in enumerate(g.L_JOINT_X, 1):
        add_part(f"4 × 30 mm wood screw {number}", g.edge_position(g.screw(x, g.PLATE / 2)),
                 role="hardware", group="Hardware")
    if display in {"Assembled jig", "Face mortise"}:
        add_part("Face registration pin", pin.translate((-g.PIN_AXIS, g.FACE_NEAR, 0)), color=pin_color)
    if display in {"Assembled jig", "Edge mortise"}:
        x = g.PIN_AXIS if display == "Assembled jig" else -g.PIN_AXIS
        add_part("Edge registration pin", g.edge_position(pin.translate((x, g.EDGE_NEAR, 0))), color=pin_color)
    if display in {"Face mortise", "Edge mortise"}:
        end = -g.PIN_AXIS + g.PIN_DIAMETER / 2
        add_part("18 mm board", g.square_stock(end), role="reference", color=stock_color, alpha=0.55)
    if display == "Face mortise":
        barrel = g.cylinder(bushing_diameter, 0, g.FACE_NEAR, g.PLATE - bushing_projection, bushing_projection)
        add_part("Active guide bushing", barrel, role="reference", color=pin_color, alpha=0.45)
    if display == "Edge mortise":
        barrel = g.cylinder(bushing_diameter, 0, g.EDGE_NEAR, g.PLATE - bushing_projection, bushing_projection)
        add_part("Active guide bushing", g.edge_position(barrel), role="reference", color=pin_color, alpha=0.45)
