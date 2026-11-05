<!-- soma:folder -->
# SOMA (written by the app, do not edit this section)

The SOMA app writes and replaces everything between the two `soma:folder` markers. The rest of this file belongs to the folder.

A person designs a 3D model with code in this folder, together with you. The model is written in Python with CadQuery, the entry point is `model.py`. The SOMA app shows the result in a 3D viewer next to the terminal.
## Project layout

| Path | Purpose |
|---|---|
| `model.py` | Entry point. Builds the model and registers every part. Small models live only here |
| `parts/` | Optional. Move parts into modules here when `model.py` gets long, import them from `model.py` |
| `inputs/` | Files the user brought (STEP, images, PDF). Never modify them, load them from `model.py`. Read PDFs with `pdfplumber` (text, lines and coordinates, `page.to_image()` for a picture) |
| `parameters.json` | Values the user set in the app's Parameters panel (rule 7). Written by the app |
| `output/model.step` | Main result with all parts, written by `soma build`. Never write it yourself |
| `exports/` | Single-part exports written by `soma export` |
| `animations/` | Optional. Motion, camera flights and captions in Python (`soma.anim`), one file per topic. The skill for animation explains them |
| `analyses/` | Optional. Load cases for `soma analyze fem` in Python (`soma.fem`), one file per load case. The skill for FEM explains them |
| `drawings/` | Optional. Technical drawings in Python (`soma.drawing`), one file per drawing or set of sheets. `soma drawing build` writes PDF and DXF to `output/drawings/`, all sheets together to `output/drawings.pdf`. The skill for technical drawings explains them |
| `renders/` | Pictures and videos written by `soma render`. Not in the version history and not in the saved .soma file |
| `.soma/` | App data (viewer cache, build status, feedback images, skills, built animations, analysis results, drawing pictures). Do not edit. Read the skills in `.soma/skills/` as the list at the end of this file says, and files in `.soma/feedback/` when the user points you to them |

## Rules for model.py

1. `from soma import add_part, param, import_step, import_assembly`
2. **Register every part**: `add_part("Name", workplane_or_shape)`. Unregistered geometry is invisible in the viewer and missing from exports.
3. Names are unique. Umlauts are fine, they are shown as written.
4. Group related parts with `group`: `add_part("Screw front", screw, group="Housing/Screws")` (nested with `/`). Groups show up in the part tree of the app and as sub-assemblies in `output/model.step`.
5. Mark a part the user brought (for example a circuit board) with `role="reference"`: it is shown semi-transparent and skipped by `soma export --all`. Cut clearances around it, but do not export it. Scenery for an animation or a video (a floor, a stand, a logo) is a reference too: give it `alpha=1` and a `color` to make it opaque.
6. Units are millimetres, Z is up, the front faces −Y (the front view looks from −Y), X points right. Put dimensions in named constants at the top of `model.py` so the user can ask for changes ("make the wall 3 mm"). Once parts live in `parts/`, the constants go to `parts/params.py`, and `model.py` and the part modules import them from there.
7. **Parameters for the user**: make the values the user would want to change themselves with `param()`: `BORE = param(38.0, "Cylinder bore", min=30, max=42, step=0.5, unit="mm", group="Crank train")`. They appear in the app's Parameters panel, where the user changes them without you. Good parameters are main dimensions, counts, options and positions (`CRANK = param(0, "Crank angle", min=0, max=360, unit="deg")`), usually 3 to 15 per model. Helper and derived values stay plain constants. Choose `min` and `max` so that the model builds and makes sense over the whole range. The default decides the field: `param(18, ...)` whole numbers, `param(True, ...)` a switch, `param("M3", ..., options=["M3", "M4"])` a choice. The user's values are kept in `parameters.json` and take the place of the defaults in the code, `soma build` lists them ("set by the user in the app"). So the number in the code is not always the one in the model. Do not edit `parameters.json` unless the user asks. If the user asks you for a new value of a parameter they set in the panel, change the default in the code and remove its entry from `parameters.json`, so that the code's value applies again.
8. Load user files with `import_step("inputs/board.step")`: this merges the whole file into one shape. If the file has several parts or sub-assemblies, keep them with `asm = import_assembly("inputs/board.step")` and `add_part("Board", asm, role="reference")`: every body becomes its own part with its name and color, the sub-assemblies become groups under "Board". Move an assembly with `asm.loc = cq.Location((x, y, z))`. STEP files often have their origin in a corner: check the bounding box and move the part deliberately.
9. Prefer simple, readable CadQuery. Check that operations produced solids. Do not use `show_object` or `cq_editor`.

## Commands

Run them in this terminal. They work without the app.

| Command | Purpose |
|---|---|
| `soma build` | Runs `model.py`, writes `output/model.step` and the viewer cache. **Run it after every change and read the result.** On errors it prints the file, line and message |
| `soma export <Part> --format stl` | Exports one part (formats: step, stl, 3mf, amf, brep, iges, obj, vrml, glb, gltf, dxf, svg) |
| `soma export --all --format step` | Exports all parts except references |
| `soma export <Part> --format glb --detail coarse` | Mesh formats (stl, 3mf, amf, obj, glb, gltf) take `--units mm\|cm\|m\|in`, `--up z\|y`, `--detail coarse\|normal\|fine` or `--tolerance <mm>`. Default: glb/gltf in m with Y up (game engines, Blender), the others in mm with Z up |
| `soma render` | Saves a picture of the current model to `renders/view-iso.png` (`--view top` or a direction `--view=1,-2,1`, `--hide`/`--only` parts or groups, `--fit` parts, `--zoom 2`, `--size 1280x800`, `--out`). **Open the picture and look at it** to check your work, also inside: hide what is in the way. Needs the app with this model open, it renders with the app's viewer |
| `soma analyze overhang` (or `thickness`, `clearance`) | Value at every spot of the surface with a summary per part. Details in the skill for analysis |
| `soma analyze fem analyses/x.py` | Stresses, safety and deflection under a load case described in `analyses/x.py`. Details in the skill for FEM |
| `soma anim build`, `soma anim info "Name"` | Animations from `animations/`. Details in the skill for animation |
| `soma drawing build`, `soma drawing info "Name"` | Technical drawings from `drawings/` as PDF, DXF and a picture to check. Details in the skill for technical drawings |

If `soma build` fails, fix the error before doing anything else. Keep the model buildable at all times.

## Version history (git)

SOMA does not manage Git in this folder. If the folder is a repository, the app shows its commits as a timeline under the 3D view, but it does not commit or restore anything here.

- Commit only when the user asks, and follow the conventions of this repository.
- Do not rewrite history unless the user asks for it explicitly.

## Environment

- Use the `python` and `pip` on your PATH. They belong to this app and already have CadQuery, numpy, scipy and more.
- If the model needs another package, run `pip install <package>`. It goes into this model's own environment, and `soma build` records it in `.soma/requirements.txt` (do not edit that file). Install only what the model really needs.
- **Do not create virtual environments** (`.venv`, `venv`), and do not use `--user`, `uv` or another Python to install packages.
- If pip refuses a package because it needs other versions of the app's libraries, pick another version or another package. The app's libraries stay as they are.
- Do not move or rename `model.py`, and do not create your own STEP writer: the app relies on `soma build`.

## Feedback from the user

The app pastes short notes into your input. The user adds their own words and sends them:

- `[Markup: .soma/feedback/markup-20260930-1405.png]`: a picture of the 3D view (or a blank sketch) with the user's drawings: arrows, circles, handwritten text, often with dimensions. **Open the image file and look at it**, compare it with the model, then change the code. If the note says `shows the older version <hash>`, the picture shows that older commit, not the current code (`git show <hash>:model.py`). Leave the images where they are.
- `[Selection: part "…", model.py line …]`: the part the user clicked, with the lines of its `add_part` call and the clicked face.
- `[Build error: …]`: the message of the last failed build.
- `[Parameter: "Cylinder bore" (BORE) = 40 mm, set in the app, code default 38 mm, model.py line 12]`: a parameter from the Parameters panel, with the user's value if they set one.
- `[Animation: "Name" (animations/x.py) at 1.50 s]`, `[Video: renders/x.mp4 at 00:03.20]`: a moment in an animation or a video. A markup can name it too (`drawn on renders/x.mp4 at 00:03.20`).
- `[Result: "Wall thickness" (.soma/results/…), part "…": 0.80 mm at (x, y, z) mm]`: a spot in the colours of an analysis.
- `[Skill: .soma/skills/<name>.md]`: the user points you to this rule set, switched it on or changed its settings (the note may list them, they are already written into the file). Read the file again now and follow it from here on. When the user switches a skill off, it disappears from the list below: stop applying it.

The user can also edit files directly in the app's editor. Read a file again right before you change it, do not rely on an older copy.

<!-- soma:skills -->
## Skills

### Always follow

The user switched these rule sets on for this model. **Read each file before you change the model and follow it.**
They take precedence over your general habits, but not over explicit wishes of the user. If a rule cannot be met, say so.

- `.soma/skills/design-workflow.md`: Design workflow
- `.soma/skills/cadquery.md`: Clean CadQuery modeling
- `.soma/skills/parametric.md`: Parametric models
- `.soma/skills/standard-parts.md`: Standard parts

### Read when relevant

These rule sets are available, but not switched on for every change. **Read one as soon as the conversation turns to
its topic** (for example the user wants the part 3D printed), not all of them up front. Follow it while the topic applies.

- `.soma/skills/cadquery-scripts.md`: CadQuery scripts. Read when `soma build` reports "Compatibility mode", the model came from an existing CadQuery script, the code calls show_object() or ocp_vscode, or a file contains a "soma-compat" block.
- `.soma/skills/shell-environment.md`: Shell environment. Read when `soma` or `pip` is not found, `soma build` says the shell lacks the environment of the app's terminals, or umlauts in files look garbled (Ã¤, Ã¼).
- `.soma/skills/soma-app.md`: Using the SOMA app. Read when the user asks how to do something in the SOMA app, cannot find a button or panel, or asks what a part of the window does.
- `.soma/skills/3d-printing.md`: 3D printing (FDM). Read when the parts will be 3D printed on a filament printer (FDM).
- `.soma/skills/resin-powder.md`: Resin and powder 3D printing (SLA, SLS, MJF). Read when the parts will be printed in resin (SLA, DLP) or powder (SLS, MJF).
- `.soma/skills/cnc.md`: CNC milling and turning. Read when parts will be CNC milled or turned.
- `.soma/skills/laser.md`: Laser cutting. Read when parts will be laser cut from flat sheets (plywood, MDF, acrylic).
- `.soma/skills/sheet-metal.md`: Sheet metal. Read when parts will be made from bent sheet metal.
- `.soma/skills/plasma.md`: Plasma cutting. Read when parts will be cut from metal plate on a CNC plasma table.
- `.soma/skills/tolerances.md`: Tolerances and fits. Read when parts must fit together: clearances, holes for screws, sliding or press fits.
- `.soma/skills/joints.md`: Joints and fasteners. Read when parts are joined: screws, snap fits, hinges, pins, magnets or glue.
- `.soma/skills/strength.md`: Strength and stiffness. Read when a part carries load or must be stiff, strong or light.
- `.soma/skills/assemblies.md`: Assemblies and motion. Read when several parts are assembled or move against each other.
- `.soma/skills/analysis.md`: Analysis. Read when you check printability, wall thickness or gaps between parts, or the user asks for an analysis.
- `.soma/skills/animation.md`: Animation and video. Read when the user wants to see parts move, an assembly sequence, a camera flight, a video or a presentation of the model.
- `.soma/skills/fem.md`: Strength with FEM. Read when a part carries a real load and the user wants to know whether it holds, where it is weakest or how far it bends.
- `.soma/skills/drawings.md`: Technical drawings. Read when the user wants a technical drawing, a manufacturing or assembly drawing, a PDF or DXF with dimensions, or a parts list.
<!-- /soma:skills -->
<!-- /soma:folder -->
