# Standalone mitre loose-tenon jig

## Requirements

- Set **Angle between bevel and board face** in SOMA. The range is 36° to
  90° and the default is 45°. The fence seats against the broad face at the
  short point of the bevel. Its lower end is square to that face. Use the
  wings to clamp across 18 mm stock below the router base.
- Use the same slot sizing and 12 mm guide thickness as the square jig.
  The tenon is fixed at 6 × 30 mm. The plunge is 15 mm in each piece.
- The slot center stays fixed when tooling dimensions change. The stock
  offset at each angle keeps at least 1 mm of wood at the mouth and bottom
  of the mortise. Use the same end reference on both boards.
- Put the workpiece face of the guide on the bed. Print the fence on its
  angled workpiece face, with the wings flat on the bed. Allow a 4 mm brim
  on the A1. The design assumes a 0.4 mm nozzle and 0.20 mm layers.
- Follow the SOMA 3D printing, tolerances, joints, assemblies, and analysis
  skills in `.soma/skills/` and the [CAD Lab FDM guide](../../../FDM-DESIGN.md).

## SOMA views

**Bevel and mortise** shows the stock and the nominal 15 mm cut envelope.
**Jig** shows the assembled tool. **Print jig** puts both pieces on the A1.
Use **Print guide plate** or **Print fence** to put one piece on the bed.

Keep the two projects in the same CAD Lab folder. They share the sizing and
engraving functions in `../parts/geometry.py`. Enter the same measured bushing
diameter, bushing projection, and cutter diameter in both models.

## Assembly and clamping

- Fit the four tapered fence pads into the guide pockets before tightening.
  Use two 4 × 30 mm wood screws with 90° countersunk heads about 8 mm across.
  Drive them through the Ø4.3 mm clearance holes into the smooth
  Ø3.2 × 20 mm pilots. At shallow angles, the screws and pads move together
  toward the rear to keep material under the pilots. Check the pilot fit on scrap and
  confirm that the heads sit below the router face. [Example screw dimensions](https://www.heco-schrauben.com/pdfexport/product/019c004f809670f9a99ad6a6e01d0b3f)
- Each wing extends 32 mm past the guide plate. Its parallel faces are
  8.49 mm apart. The fence has 0.50 mm rim chamfers.
  Grip the wing and the opposite board face with parallel jaws below the
  guide plate. The CAD setup with 12 mm-wide jaws needs about 26.5 mm of
  opening. The board in SOMA is 230 mm wide.

## Positioning and routing depth

Seat the guide plate flat on the bevel and the fence flat against the
short-point broad face. The centerline runs down the back of the fence and
across its base. A V-mark runs across the fence surface visible through the
guide slot and continues down the sloping face. Align a fence center mark
with your mark on the board. Use the
[square jig's depth gauge](../NOTES.md#registration-and-routing)
to set 27 mm of reach from the router base. This gives a 15 mm plunge past
the 12 mm mitre plate.
The guide uses 0.50 mm bed chamfers, 0.40 mm top chamfers, and 0.45 mm
chamfers on the slot lips. The face and edge alignment lines are
V-grooves that are 0.60 mm wide at the surface and 0.60 mm deep at the center.
The slot-wall marks start 0.90 mm wide and 0.60 mm deep at the work face
and taper with print height.

At 45°, a 15 mm plunge and a 6.50 mm cut leave 1.00 mm of wood at the mouth
by the blunt side and 1.80 mm at the bottom by the sharp side. Both dimensions
are perpendicular to the broad faces. Check seating, bushing fit, and plunge
on scrap before routing the joint.
