# CAD workspace

- Use `cadlab/bin/cadlab` and the [CAD Lab guide](README.md) for the shared SOMA runtime and project commands.
- Keep designs under `projects/`. Open the exact design in SOMA while working so the user can review it.
- Use global Node, npm, uv, and Python tools. Keep project dependencies in SOMA's project environment.
- Keep SOMA's project settings and agent guidance. Keep generated outputs out of Git.
- Add practical chamfers for printability and handling while preserving functional fits.
- Use fine quality for mesh exports. For native SOMA commands, pass `--detail fine`.
- Run CAD Lab's scoped checks only; repository-wide checks also validate other projects.
