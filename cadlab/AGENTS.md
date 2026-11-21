# CAD workspace

- Use `cadlab/bin/cadlab` and the [CAD Lab guide](README.md) for the shared SOMA runtime and project commands.
- Keep designs under `projects/`. Open the exact design in SOMA while working so the user can review it.
- Use global Node, npm, uv, and Python tools. Keep project dependencies in SOMA's project environment.
- Keep SOMA's project settings and agent guidance. Keep generated outputs out of Git.
- Add practical chamfers for printability and handling while preserving functional fits.
- Use fine quality for mesh exports. For native SOMA commands, pass `--detail fine`.
- Run CAD Lab's scoped checks only; repository-wide checks also validate other projects.

## SOMA skills

- Before modeling, read the target project's `AGENTS.md` and its `Always follow`
  skills. Use its `Read when relevant` list for the task at hand. Read the
  files in the project's `.soma/skills/` for active settings. For a new project,
  use the shared skill path from `cadlab paths` until SOMA initializes it.
- For printed parts, read `3d-printing.md` and `tolerances.md` before sizing gaps,
  engravings, and mating features. Use the selected nozzle, layer height, and
  print orientation. Use `analysis.md` when checking geometry for printability.
  See [Design for filament printing](FDM-DESIGN.md) for CAD Lab examples and
  source guidance.
- For locating features and fasteners, read `assemblies.md`, `joints.md`, and
  `tolerances.md`. Check the parts in their assembled positions, including
  locating contact, fastener access, and clearance.
