# Sharpening stone jig

## Requirements

- Stone footprint: 170 x 75 mm, confirmed by the user.
- Stack: 1 mm sharpening plate on 5 mm firm foam. Little noticeable compression.
- Sharpening surface: about 1 mm above the holder rim.
- Printer: Bambu A1, 256 x 256 x 256 mm build volume.
- Approved initial envelope: 190 x 95 x 30 mm.
- Removable 15 and 20 degree guides, adjustable through SOMA parameters.
- Continuous flat support, removal notch, rounded outer corners, flat underside
  for non-slip pads.
- Holder and fit coupon: 0.5 mm chamfers on the top edges. Pocket dimensions
  below the edge relief are unchanged.
- All geometry and validation are scoped to this CAD project.
- Follow `.soma/skills/3d-printing.md`, `.soma/skills/tolerances.md`, and
  `.soma/skills/assemblies.md` for this FDM assembly. The confirmed A1 bed
  dimensions replace the app default. Bearing faces intentionally touch.

## Assumptions and limits

- (assumed) 0.3 mm clearance per side for the stone and guides. Confirm by print.
- (assumed) Firm foam is represented at its unloaded 5 mm thickness. Any
  compression reduces the nominal 1 mm exposure.
- (assumed) Straight rectangular stone with square corners and constant thickness.
- Guide feet bear on the rim. Their underside clears the nominal plate by
  0.4 mm; skirts locate outside the holder without a snap fit or clamps.
- The guides set the blade-face angle relative to the stone. They are removable
  setting aids, not an edge-following mechanism. Set the angle, then move the
  guide clear of the sharpening stroke. Blade grind can affect the actual
  edge angle; follow the knife maker's guidance.
- Filament, nozzle, and slicer settings are not fixed. No printed fit, friction,
  stiffness, or sharpening trial has been performed.
- The 3MF in `inputs/reference.3mf` is a visual reference, not executed code or
  the source of our dimensions. Its metadata names Masiosare_bb as designer and
  states Standard Digital File License. Keep its attribution with the reference.

## Validation

- Native SOMA build passed with holder, two guides, and two reference layers.
- 34 temporary parameter cases passed, including each numeric limit, display
  options, the fit coupon, combined limits, a mixed short-stone/long-guide case, and A1 print layouts.
- Independent checks cover the 190 x 95 x 30 mm envelope, pocket boundaries,
  5 mm depth, 1 mm exposure, guide bearing height, 0.4 mm plate gap, 0.3 mm
  side fit, actual guide face normals, and print-face orientation.
- Model assertions require one valid solid per printed part, no guide/holder
  or guide/stone interference, no print-part overlap, and A1 bed containment.
- Physical fit remains a prototype check. Start with the fit coupon.

## Parts and assembly

| Part | Count | Process or specification |
| --- | --- | --- |
| Holder | 1 | FDM, material to be selected |
| Angle guide | 2 | FDM, 15 and 20 degrees by default |
| Fit coupon | Optional 1 | FDM, tests width and depth, not full length |
| Foam-backed plate | 1 | User supplied, 170 x 75 x 6 mm |
| Non-slip pads | As needed | User supplied, on flat underside |

Fit pads first, place the stone from above, then lower a guide onto the rims.
All parts can be lifted off without tools. The guides are setting aids; no
loaded sliding motion is specified. Guide clearance is a prototype fit value.
