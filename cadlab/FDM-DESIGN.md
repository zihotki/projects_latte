# Design for filament printing

Use the project's SOMA `3d-printing`, `tolerances`, and `analysis` skills for
active settings. Record the printer, nozzle, layer height, material, print
orientation, and critical fits in the project notes.

## Orientation and support

- Put a broad, stable face on the bed. Keep support away from surfaces that
  locate, slide, or guide other parts. Split a part when a simpler orientation
  improves the finish or reduces support. Where possible, keep the main
  tensile loads in the plane of the layers. [Prusa modeling guide](https://help.prusa3d.com/article/modeling-with-3d-printing-in-mind_164135), [Stratasys FDM guidelines](https://www.stratasys.com/siteassets/sdm/resources/design-guidelines/fdm/fdm_design_guidelines_2017-1.pdf)
- Start with 45° from vertical for unsupported slopes. Shape long roofs or
  transverse holes with slopes when the fit permits. Measure short bridges
  across their unsupported span and check them against the active SOMA limit.
  Nozzle, layer height, cooling, and material affect the result. [Prusa modeling guide](https://help.prusa3d.com/article/modeling-with-3d-printing-in-mind_164135)

## Corners and mating edges

- Use a 45° chamfer on exposed bed-facing edges where the first layer can
  spread. Start at 0.5 mm with a 0.4 mm nozzle. Use small lead-in chamfers
  where a part slides into a seat. Preserve the working flat beyond the
  chamfer. [Prusa modeling guide](https://help.prusa3d.com/article/modeling-with-3d-printing-in-mind_164135), [Prusa first-layer compensation guide](https://help.prusa3d.com/article/elephant-foot-compensation_114487)
- Check the outline in print orientation. Break sharp 90° corners that run
  through the layers. Match the corner breaks of mating parts and preserve
  their specified clearance. Apply edge finishing after the main features.
- Round accessible outline corners in the plane of the layers. Use a fillet
  at loaded internal transitions where it preserves wall thickness and can
  print without support. Check that radii leave the locating faces, stops,
  contact pads, and tool clearances intact. [Stratasys FDM design guide](https://www.stratasys.com/siteassets/sdm/content---website-storage/design-guides/dg_sdm_fdm_0725a.pdf?v=490918), [Prusa modeling guide](https://help.prusa3d.com/article/modeling-with-3d-printing-in-mind_164135)

## Walls, marks, and fits

- Size walls for the intended number of extrusion lines. The line width is
  profile-specific. Add material or a fillet where clamps, screws, or inserts
  transfer load. Keep broad walls reasonably uniform to reduce uneven
  shrinkage. [Prusa layers and perimeters guide](https://help.prusa3d.com/article/layers-and-perimeters_1748), [Stratasys FDM design guide](https://www.stratasys.com/siteassets/sdm/content---website-storage/design-guides/dg_sdm_fdm_0725a.pdf?v=490918)
- Give recessed marks enough width for the selected nozzle and enough depth
  for several layers when engraved on a flat top face. On a vertical wall,
  taper the recess with build height so each layer closes it a little. For
  these jigs, a 0.6 mm top engraving is three layers deep at 0.20 mm per layer.
  Keep the marks below or outside the bushing contact band. [Prusa modeling guide](https://help.prusa3d.com/article/modeling-with-3d-printing-in-mind_164135)
- A V-groove opens toward the marked surface and removes less material than
  a rectangular groove of the same width and depth. The narrow bottom can
  print shallower than the CAD section. Check the mark in its intended build
  orientation. [Stratasys scribe-line study, pp. 25–26](https://www.stratasys.com/siteassets/industries-and-applications/tooling/composite-tooling/design_guide_large-fdm_for_composite_tooling_2.0.pdf#page=25)
- Dimension fits from working faces. Give moving parts and holes clearance
  based on the mating hardware, print orientation, and material. Use the
  insert maker's bore size for a heat-set insert. Check critical sliding and
  press fits with a small print before making the full assembly. [Prusa modeling guide](https://help.prusa3d.com/article/modeling-with-3d-printing-in-mind_164135), [Stratasys FDM design guide](https://www.stratasys.com/siteassets/sdm/content---website-storage/design-guides/dg_sdm_fdm_0725a.pdf?v=490918)

## CAD Lab checks

- Inspect the model in its intended print orientation. Check solids, bed
  bounds including brims, overhangs, bridge spans, and thin walls. For a
  parametric model, also check the combinations that give the smallest
  clearance and the thinnest material.
- Verify fit in the assembly, including tool access and the full travel of
  moving parts. Record design assumptions and the checks that still need a
  physical print. The loose-tenon jigs use the A1's 256 × 256 mm bed, a 0.4 mm
  nozzle, 0.20 mm layers, and room for 4 mm brims. [Bambu Lab A1 specifications](https://cdn1.bambulab.com/documentation/quick-start-a75adcb1d5d5e/Quick%20Start%20Guide%20for%20A1.pdf)
