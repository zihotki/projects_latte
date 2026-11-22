# CAD workspace

- Use `cadlab/bin/cadlab` and the [CAD Lab guide](README.md) to run the viewer and CAD commands from the source checkout.
- Keep designs under `projects/`. Open the exact design in SOMA while working so the user can review it.
- Use global Node, npm, uv, and Python tools. Keep project dependencies in SOMA's project environment.
- Keep SOMA's project settings and agent guidance. Keep generated outputs out of Git.
- Add practical chamfers for printability and handling while preserving functional fits.
- Use fine quality for mesh exports. For native SOMA commands, pass `--detail fine`.
- Run CAD Lab's scoped checks only; repository-wide checks also validate other projects.
- Find the project and shared SOMA skill files in the
  [CAD Lab skill](../.agents/skills/cadlab/SKILL.md#soma-skills).
