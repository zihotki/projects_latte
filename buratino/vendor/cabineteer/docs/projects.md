# Project inputs and saved data

`CabinetProject` is the durable Cabineteer input. It supports cabinet
configurations, a native Space model, recursive Space assemblies, and profile
assemblies. These inputs feed evaluation and the project-level output tools.
For authoring a Buratino project folder, use the
[Buratino design guide](../../../docs/designing.md).

## Choose an input model

| Input | Use it for | Main fields |
|---|---|---|
| `cabinets` | One or more parametric cabinet configurations with shared design tokens. | `shared`, `cabinets` |
| `space_model` | One rectangular carcass, a clear-space tree, and optional applied fronts. | `carcass`, `root`, `fronts` |
| Space assembly | Reusable cabinet and module definitions placed in a row, stack, or nested host. | `space_cabinets`, `space_modules`, `layout` |
| Profile assembly | A layout with profiled boxes, roof, frames, and optional faces, drawers, or shelves. | `layout`, `profile_assembly` |

`space_model` holds one carcass and root tree. It can share a project with
`space_cabinets` and `space_modules` definitions used by that tree. It cannot
be combined with cabinet configs, shared design, worktop, layout, or profile
input. A recursive Space assembly uses named definitions and a layout. A
`Space` can split into child spaces; a leaf can hold a drawer box or reference
a reusable module. `Row` and `Stack` arrange modules and cabinet references.
See the runnable examples in
[`buratino/projects`](../../../projects/) and the
[model guide](../../../docs/designing.md).

A profile assembly also uses a native layout. Its `ProfileAssemblySpec` names
the roof, profiled boxes, cap and lower owners, and frame; optional fields add
faces, drawers, shelves, and extra frames. The
[profile row example](../../../projects/profile-row-sloped/project.py) shows the
entry point.

## Canonical JSON

Saved snapshots use `input_schema_version: 2`. Use this version when sending a
complete project payload to `design_project` or rebuilding a saved payload.
Space inputs and profile dataclasses use tagged objects with a `type` field,
such as `{"type": "Space", "name": "root"}`. `layout` uses its own
serialized node format. The serializers and validators in `project.py`,
`spaces.py`, `profiles.py`, and `layout.py` define the exact shapes.

The Space model block has this shape:

```json
{
  "input_schema_version": 2,
  "name": "one-cabinet",
  "space_model": {
    "carcass": {"type": "Carcass", "width": 600, "height": 900, "depth": 500},
    "root": {"type": "Space", "name": "root"},
    "fronts": []
  }
}
```

Omitted dataclass fields use source defaults. Include all project blocks that
the selected model needs; do not infer types from field names.

## Save and update

`design_project` saves a new named snapshot. It refuses an existing name unless
`overwrite` is true. `list_projects`, `load_project`, `duplicate_project`,
`rename_project`, and `delete_project` manage snapshots under
`~/.cabineteer/projects/`.

`update_project` applies a patch to a saved snapshot. Cabinet config and shared
token patches merge at the field level. The native blocks `space_model`,
`space_cabinets`, `space_modules`, `layout`, and `profile_assembly` replace the
whole stored block; use `null` to remove a block. The completed payload is
validated before it is saved. Load the current payload first when you need to
edit part of a native block, then submit the full revised block.

The project tools work on both cabinet configs and native project inputs.
`evaluate_project` resolves and checks the project; project cutlists and
visualizations consume the saved project. See the
[MCP reference](mcp.md) for the tool names and schemas.

Profile assemblies can set `joinery=DominoJoinery()` for carcass contacts and
`corner_joinery=DominoJoinery(spacing=90)` for drawer box corners. Both recipes
are optional. They use the same row resolver and oval mortise cutters as Space
components. The recipe cuts the existing solids and retains stock sizes, grain,
profiles and placement frames.

Supported carcass contacts are walls against fixed bottoms, floors and tops,
and walls against a level roof cap. Drawer corners join each side to its inner
front and back. Back panels, adjustable shelves, facades and support frames do
not receive these cuts. Each paired mortise has one shared world center and
separate local stock L/W/T machining coordinates. The default 20 × 6 mm slot
uses 12 mm face depth and 28 mm end depth. Depth and finished-profile fit are
checked before cuts are accepted.

Sloped cap joints remain unverified. They require an oblique mating frame and
matched paired mortise centers; the axis-aligned recipe does not cut them. This
limit is recorded as `joinery.sloped_cap_unverified`. Modeled joints do not make
the draft assembly ready for manufacture.
