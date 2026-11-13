# Local validation

## Shared setup — 2026-11-13

The shared installation was checked on macOS Apple Silicon at SOMA fork commit
`c9ca52634df0d2b0622c268ae326e50350ecbf29` on `feat/open-folder`. CAD Lab's
wrapper tests, SOMA type checks and unit suite passed. A temporary model built
with the shared runtime and opened in the viewer without a setup dialog. An
isolated installation and replacement were also checked, including a project
package after a base-environment change. No unrelated project checks ran.

## Earlier worktree setup

Checked on 2026-11-05, macOS Apple Silicon, in this worktree.

| Tool | Global version |
| --- | --- |
| Node | 26.7.0 |
| npm | 11.19.0 |
| uv | 0.12.5; updated with Homebrew from 0.11.28 |
| Python | 3.14.6 |

No older toolchain was installed. `.venv` uses the global Python interpreter.
SOMA 0.11.0 and CadQuery 2.8.0 are installed from the pinned source and package
requirements. `pyamg` 5.3.0 built from source for this Python version.

Checks completed:

- SOMA TypeScript build and type checks passed.
- Upstream unit suite passed.
- Ruff checked the wrapper and example model.
- Native SOMA build produced STEP and GLB outputs for the example plate.
- Independent STEP import confirmed a valid 40 x 30 x 4 mm solid and the
  expected volume after subtracting a 6 mm through-hole.
- Source app launched through the wrapper. Its viewer displayed the plate.
- Open folder configured the saved example project.
- The app detected Codex from PATH. Its terminal opened in the example folder
  and `soma --version` returned `soma 0.11.0`.
- Independent Sol review found no actionable integration defects.

The pinned upstream npm dependency audit reported 9 advisories (7 moderate,
2 high). No automatic dependency upgrade was applied. CalculiX/FEM and the full
upstream GUI suite were not tested. Global tool upgrades remain allowed; rerun
doctor and the relevant checks after an upgrade.
