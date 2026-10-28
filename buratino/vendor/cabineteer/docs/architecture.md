# Architecture

Cabineteer provides the design inputs and resolvers used by the Buratino
workspace. Its native Space and profile resolvers produce CAD-independent
plans. Buratino uses those plans for builds, reports, and previews. See the
[Buratino design guide](../../../docs/designing.md) for the user-facing flow.

A Space plan build creates CAD shapes and runs static physical validation.
Profile builds use native cap contact and overlap checks.

```text
cabinet / drawer / door ── project inputs ── evaluation and planning
                                   │
                                   ├── Space tree → allocation → physical-part plan
                                   ├── layout + profile spec → profile assembly
                                   └── cutlist / assembly documents / visualization
                                                │
                                      MCP tools and Cabineteer CLI

Buratino Space build: resolve → CAD geometry → physical validation → draft files
Buratino profile build: resolve → cap contact/overlap checks → draft files
```

## Main modules

| Module | Role |
|---|---|
| `cabinet.py`, `drawer.py`, `door.py` | Cabinet and component dimensions, openings, and face layout. |
| `spaces.py`, `allocation.py` | Clear-space input types and fixed/fractional allocation. |
| `space_assembly.py` | Resolve recursive Space trees, reusable cabinets, modules, and layouts into physical parts and diagnostics. |
| `profiles.py`, `layout.py` | Resolve profiled assemblies and their layout, frame, roof, and face inputs. |
| `project.py` | `CabinetProject` inputs, tagged JSON conversion, saved-project operations, and updates. |
| `evaluation.py`, `assembly.py`, `cutlist.py` | Design checks, assembly plans, cut and hardware lists, and output formats. |
| `server.py` | MCP tool schemas, handlers, and dispatch. |
| `cli.py` | Standalone Cabineteer command-line access to the tool handlers. |

## Data flow

`CabinetProject` can hold cabinet configurations, a native `space_model`, a
recursive Space assembly, or a profile assembly. The applicable resolver
validates inputs and returns a plan before downstream code creates output.
`resolve_space_assembly` is pure Python: it checks definitions and references,
allocates spaces, and derives placements, bounds, diagnostics, and physical
parts. Profile assembly resolution combines a native layout with a
`ProfileAssemblySpec`.

MCP handlers are ordinary Python functions registered in `server.py`. The
Cabineteer eval harness calls the same handlers through `TOOL_DISPATCH` without
starting an MCP transport. Buratino runs this source as an editable dependency
inside its locked runtime; its launcher and build flow are documented in the
[workspace README](../../../README.md).
