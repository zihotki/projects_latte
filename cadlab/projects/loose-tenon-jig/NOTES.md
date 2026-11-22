# Loose-tenon jig

## Requirements

- Follow the two supplied jig screenshots. Screw the winged face plate and the
  narrow routing fence together at 90°. The blue plate's center tongue sits
  in the gray fence's matching seat. The tongue is 70 mm wide across its
  flat flanks and projects 12 mm. The seat gives 0.08 mm nominal clearance
  at each side and follows the four 0.60 mm upright corner chamfers.
  Check the seating faces for first-layer ridges before assembly.
- Use fixed 6 × 30 mm tenons in 18 mm stock. The width along the slot and
  the total insertion length are both 30 mm.
- The primary face and edge slots sit 9 mm from the inside corner. The face
  slots have 2 mm more travel than the snug edge slot. All three slot centers
  stay fixed when the bushing, cutter, or fit changes.
- Include recessed registration pins. Use the [separate mitre jig](mitre/NOTES.md)
  for bevelled stock.
- Fit the parts on the A1. Use separate print views for the face plate, edge
  fence and pins. Allow a 4 mm brim. Use a 0.4 mm nozzle and
  0.20 mm layers as design assumptions.
- Follow the shared SOMA 3D printing, tolerances, joints, assemblies, and
  analysis skills and the [CAD Lab FDM guide](../../FDM-DESIGN.md).

## SOMA views

| View setup | What it shows |
| --- | --- |
| Assembled jig | Face and edge guides with the tongue seated, wood screws, and registration pins |
| Face mortise / Edge mortise | Square jig against 18 mm stock with the bushing in the active slot |
| Print face plate / Print edge fence and pins | Two separate A1 layouts |

The 16 mm bushing diameter, 5 mm projection, and 6 mm cutter are preview
values. Enter the measured dimensions in SOMA. The projection limit reserves
clearance for the perpendicular slot and its alignment marks at the corner.
Use both assembled guides for the near slots.

## Registration and routing

- Clamp the large plate against the broad face of the board. Use the slot in
  the plate for a loose face mortise, or the slot in the attached fence for a
  snug edge mortise. Use the same board end reference for each half of a joint.
- Place a registration pin in the underside seat on the selected guide and
  board end. The pin tangent sets a 39.5 mm setback. The pin fit parameter
  changes the bore diameter. Check the actual printed fit.
- The face and edge alignment lines are V-grooves that are 0.60 mm wide at
  the surface and 0.60 mm deep at the center.
  The V-shaped marks inside the slots start 0.90 mm wide and 0.60 mm deep
  at the work face. They narrow and get shallower as each print layer rises,
  up to half the plate thickness or 0.10 mm below the bushing tip.
- The blue plate is 236 mm wide across the clamp wings. Print each plate with
  its workpiece face on the bed. Free outline corners use 3 mm radii. Free
  rims have 0.50 mm bed chamfers and 0.40 mm top chamfers. Both chamfers
  follow the full blue outline, including the wings, shoulders, and tongue.
  The gray seat follows the tongue profile. Slot lips and pin-seat entries
  have 0.45 mm lead-ins.
- Use the stepped notch on the blue plate's rear edge to set plunge depth.
  Rest the rear edge against the router base and center the bushing in the
  wide opening. Align the bit tip with the deep stop. The stop is 27 mm from
  the rear edge, so the bit extends 15 mm past the 12 mm jig. The mouth gives
  at least 0.4 mm clearance across the bushing and 0.5 mm beyond its projection.
  The notch has 0.75 mm corner radii and continuous chamfers on both rims.
  The center mark runs from the underside lip along the lower half of the
  stop wall. The straight throat is 30 mm wide. To register the jig, put
  the opening over the protruding tenon and bring the rear edge against
  the adjoining board. The straight sides set the lateral position.

## Hardware

Use two 4 × 30 mm wood screws with 90° countersunk heads about 8 mm across.
Seat the four tapered pads in their matching pockets before tightening. The
tongue sets the position from side to side. The pads set the height of the
fence. Drive the screws through the Ø4.3 mm clearance holes in the edge fence into the
smooth Ø3.2 × 20 mm pilot holes in the face plate. Check the pilot fit on
scrap printed in the same material and confirm that the screw heads sit
below the router surface. [Example screw dimensions](https://www.heco-schrauben.com/pdfexport/product/019c004f809670f9a99ad6a6e01d0b3f)
Print the two registration pins shown on the second plate. A 45° ramp under
each collar supports it as the layers rise.
