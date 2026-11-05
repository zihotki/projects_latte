# CAD workspace

- Use `bin/cadlab` from this folder, or `./cadlab/bin/cadlab` from the repo root.
- SOMA source is a pinned submodule in `vendor/soma`. Keep source changes in the fork.
- Keep designs under `projects/`. Open each design folder with SOMA's **Open folder**.
- Use global Node, npm, uv, and Python tools. Setup owns the base `.venv`;
  install extra model packages through SOMA's project environment.
- Keep SOMA's project settings and agent guidance. Keep generated outputs out of Git.
- Validate CAD Lab with `bin/cadlab doctor`, `bin/cadlab check`, and a named
  model build. Do not run repository-wide validation scripts for CAD Lab work;
  those scripts also validate other projects.
