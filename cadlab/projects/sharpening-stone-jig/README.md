# Sharpening stone jig

A parametric holder for a 170 x 75 mm sharpening plate with firm foam backing.
The default model has a 190 x 95 x 30 mm holder and separate 15 and 20 degree
angle gauges. The reference plate and foam are display parts; they are excluded
from `soma export --all`.

## Open and adjust

Start `./cadlab/bin/cadlab run --project cadlab/projects/sharpening-stone-jig`
from the repo root. Open the same folder in Codex.

The Parameters panel has 15 settings:

| Group | Parameters |
| --- | --- |
| Stone | Length 140-200 mm, width 60-90 mm, plate 0.8-2 mm, foam 3-7 mm |
| Fit | Exposure 0.5-1.5 mm, stone clearance 0.15-0.6 mm per side |
| Holder | Height 15-40 mm, rim width 6-12 mm |
| Guides | Two angles 10-25 degrees, ramp length 20-35 mm, side clearance 0.15-0.6 mm |
| Display | Assembly or Print layout, reference layers, optional fit coupon |

Outer dimensions follow the stone, clearance, and rim width. Pocket depth is
`plate + foam - exposure`: 5 mm by default. Increasing base height raises the
support floor while preserving this depth. Both guides follow the holder width
and plate exposure. Labels update with their angles. The holder and fit
coupon have 0.5 mm chamfers on their top edges, including the pocket lip.
The pocket walls below the chamfers retain the specified clearance.

## Print and use

1. Enable **Include fit coupon**. Export only **Fit coupon** as STL and print
   it first. It has the same pocket width, depth, and rim, with a 3 mm floor.
   Check the width fit and surface exposure. It does not test the full length.
2. Adjust **Stone clearance per side** if needed. **Guide clearance per side**
   controls the separate sliding fit; check that on the full holder.
3. Select **Print** layout. The holder stays bottom-down. The guides turn onto
   their inclined top faces so their openings face upwards. No long bridge is
   needed across the guide opening. The numerical angle labels face the bed.
4. Export the holder and guides as separate STL files using **Fine** mesh
   quality. The CAD Lab wrapper applies it by default; select Fine in SOMA's
   export menu or pass `--detail fine` to the export command. The print layout fits
   the A1 bed over the declared parameter ranges. Review the Bambu Studio
   preview and selected material profile before printing. Geometry checks do
   not prove a support-free slicer result or physical fit.
5. Add non-slip pads to the flat underside. Seat the foam-backed stone flat.
   Place a guide on the two rims, set the blade angle, then move it out of the
   sharpening stroke. The guides are not clamps.

Native commands from the repo root:

```sh
./cadlab/bin/cadlab soma build --project cadlab/projects/sharpening-stone-jig
./cadlab/bin/cadlab soma export --all --format stl --detail fine --project cadlab/projects/sharpening-stone-jig
```

Use Assembly layout to inspect the fit; use Print layout before exporting for
printing. Exports and generated viewer files are ignored by Git. A combined
build STEP can contain reference layers; export `--all --format step` for only
the printable parts. Print-layout geometry is positioned for the bed rather
than assembled use.

## Useful angles

Angles are **per side**, relative to the stone. A symmetric 15 degree edge has
a 30 degree included angle. Keep the knife's intended angle when known.

- **14 degrees:** WUSTHOF specifies this for its standard knife guide.
  [WUSTHOF Slider](https://wusthof.com/products/sharpening-guide-slider)
- **16 degrees:** Shun specifies this for its double-bevel knives.
  [Shun FAQ](https://shun.kaiusa.com/faq)
- **10-12 degrees:** possible settings for a knife whose maker specifies such
  a shallow angle. GLOBAL gives a 10-15 degree range for its knives.
  [GLOBAL knife care](https://www.globalcutleryusa.com/pages/knife-care)

The default 15/20 pair is retained from the requested design. Change either
angle to make another labelled guide; the 14/16 pair is also checked. These
guides do not replace a single-bevel knife's sharpening method.

## Check this design only

```sh
./cadlab/bin/cadlab python cadlab/projects/sharpening-stone-jig/checks/validate.py
```

The check uses a temporary source copy. It never writes test values into the
real `parameters.json`. It checks dimensions, clearances, face angles, print
poses, and 34 parameter combinations. It does not run other project suites.
See [NOTES.md](NOTES.md) for requirements, assumptions, and physical limits.
