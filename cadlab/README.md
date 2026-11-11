# CAD Lab

Run SOMA from pinned source and keep CAD designs in this repository.

## Setup and use

This setup is validated on macOS with Apple Silicon. Install global Node, npm,
uv, Python 3.11 or newer, and Git so that they are available on PATH. Source
builds of Python packages can also require Xcode Command Line Tools.

Use global Node, npm, uv, and Python from PATH. Setup creates a local Python
environment from the global Python. It installs SOMA's pinned Python packages
and uses `npm ci` for the app. It does not install global tool versions.

```sh
git submodule update --init -- cadlab/vendor/soma
./cadlab/bin/cadlab setup
./cadlab/bin/cadlab doctor
./cadlab/bin/cadlab run
```

In SOMA, select **Open folder** and open `cadlab/projects/example`. Use the same
folder in Codex. SOMA creates its project settings and agent guidance there.
Keep later designs under `projects/` too. Folder mode leaves Git management to
this repository. Use the global tools for orchestration and `.venv` for CAD
packages. CalculiX is optional and is not installed by this setup.

The wrapper selects the local Python with `SOMA_PYTHON`, stores application
state under `.cache/app-data` with `SOMA_USER_DATA`, and uses Electron's own
launcher for macOS. Setup also fixes the installed terminal helper's execute
permission, as upstream does when packaging the app.

From the repository root, run native SOMA commands through the wrapper:

```sh
./cadlab/bin/cadlab soma build --project cadlab/projects/example
./cadlab/bin/cadlab check
```

`setup` needs network access and can take several minutes. Close SOMA before
running it again because it replaces the app dependencies. It does not open
the app. `run` opens the source app; quit SOMA to stop it.

## Create and edit a project

1. Create a folder under `cadlab/projects/`, for example
   `mkdir -p cadlab/projects/my-part` from the repository root.
2. Start SOMA with `./cadlab/bin/cadlab run`.
3. On the start page, use the arrow beside **New model**, then **Open folder**.
   Select the new folder and accept the listed project-file changes. An empty
   folder gets SOMA's starter model. The separate **New model** action creates
   a model in the app's own workspace instead.
4. Open the same design folder in Codex. Ask Codex to read its `AGENTS.md`,
   then describe the parts, dimensions, and changes you need.
5. Check the viewer and Parameters panel after each change. Use **Export**
   for files you want to print or share.

You can also copy only `projects/example/model.py` into a new folder before
opening it. Do not copy an existing project's `.soma/` folder or Python
environment. SOMA will create fresh project settings and an environment.

The app watches model files and rebuilds them. It writes the latest combined
STEP file to `output/model.step`. Folder mode does not commit changes or
restore Git revisions. Use this repository's normal Git workflow.

## Use Codex and the command line

Use the [CAD Lab skill](.agents/skills/cadlab/SKILL.md) when you open CAD Lab
or a design folder in Codex. If the skill is absent from your session's
skill list, ask Codex to read
`cadlab/.agents/skills/cadlab/SKILL.md` relative to the repository root.

SOMA's terminal has `soma` and the model's Python environment on PATH. An
external Codex shell can have a different PATH. Use the wrapper from the
repository root, or this command from a design folder:

```sh
repo_root=$(git rev-parse --show-toplevel)
"$repo_root/cadlab/bin/cadlab" soma build
"$repo_root/cadlab/bin/cadlab" soma export --all --format stl
```

The wrapper defaults mesh exports (STL, 3MF, AMF, OBJ, GLB, GLTF) to **fine**
quality. An explicit `--detail` overrides this default. For native `soma`
commands in SOMA's terminal, add `--detail fine`; in the app's Export menu,
select **Mesh settings → Fine**. The app remembers this selection in its local
state. A fresh app profile needs the selection again. STEP exports retain
CAD surfaces and do not use mesh quality settings.

Other native SOMA arguments pass through unchanged. Add `--help` after
`soma`, `build`, or `export` to see the available options. Geometry builds and
exports work with the app closed. `soma render` needs the app running with the
same design open. For feedback from SOMA, use **Send to agent**, then paste the
copied note into this design's Codex chat.

Install extra model packages in SOMA's terminal with `pip install PACKAGE`.
SOMA places them in that model's `.soma/env` and records imported packages in
`.soma/requirements.txt`. Do not install them into the base `.venv`, because
setup restores its package set. The generated `AGENTS.md` and shell-environment
skill explain how an external agent can use the model environment.

## Files and storage

| Path | Purpose | Keep in Git |
| --- | --- | --- |
| `model.py`, `parts/` | Model code | Yes |
| `inputs/` | Original reference files | Yes, when part of the design |
| `parameters.json` | Parameter values set in the app | Yes, when present |
| `AGENTS.md`, `CLAUDE.md` | SOMA's agent guidance | Yes |
| `.soma/project.json`, `.soma/skills/`, `.soma/requirements.txt` | Project settings, copied skills, and extra packages | Yes, when present |
| `output/`, `exports/`, `renders/` | Generated files | No; copy selected deliverables elsewhere when needed |
| `.soma/env/` and other ignored `.soma/` files | Model environment and generated data | No |
| `cadlab/.venv/`, `cadlab/.cache/` | Base environment, app state, and downloads | No |

Keep custom agent guidance outside SOMA's marked section in `AGENTS.md`.
SOMA can refresh that section and its copied skills. Back up model code,
inputs, parameter values, and tracked project settings through Git before an
app upgrade. Local app state and feedback images are not part of that backup.

## Source pin and upgrades

SOMA is a submodule from <https://github.com/zihotki/SOMA.git>, pinned to
v0.11.0 commit `195c29c9a6d9cfcf20ecb03f678b6b11e7cd8999`. The wrapper checks
the source commit and rejects tracked source changes before running.

Update the fork, select a tested commit, then update the submodule pointer and
the wrapper's expected commit together. Run setup, checks, a model build, and
verify viewer and terminal operation before accepting an upgrade. Setup restores
the pinned Python package set, so install extra model packages through SOMA's
project environment. Keep each model's `.soma/requirements.txt` in Git.

Global tool upgrades are allowed. `doctor` reports the active versions. If the
global Python major/minor changes, recreate `.venv` deliberately and run setup;
the existing virtual environment continues to use its original Python.

To select another SOMA commit, fetch it inside `vendor/soma`, check it out,
and change `COMMIT` in `bin/cadlab` to its full SHA. Keep the commit available
in the fork so a fresh clone can fetch it. Run setup and validation, then
commit the submodule pointer and wrapper change together in this repository.
The wrapper rejects a different commit or a dirty source tree. Put permanent
SOMA source fixes in the fork; put workspace integration changes here.

## Validate CAD Lab only

Run these commands from the repository root:

```sh
./cadlab/bin/cadlab doctor
./cadlab/bin/cadlab check
./cadlab/bin/cadlab soma build --project cadlab/projects/example --json
```

`doctor` checks the SOMA pin, active tools, Python imports, and app build files.
`check` runs type checks and the unit suite only in `cadlab/vendor/soma/app`.
The model command builds only the named design. None of these commands runs
checks for Buratino, Cut on Eight, or LiteLLM.

For a CAD Lab change, use these scoped commands. Do not use the repository-wide
`scripts/check.sh`, `scripts/test.sh`, or `scripts/verify.sh`; they also validate
other projects. After a source or setup change, open the example in SOMA and
check its viewer and terminal as well.

## Troubleshooting and limits

- **Missing source:** run the submodule command from the setup section.
- **Missing runtime or app build:** close SOMA and run setup, then doctor.
- **After a global Python upgrade:** close SOMA, move `.venv` to a backup
  location, and run setup with the new global Python on PATH. Keep the backup
  until doctor and a model build pass. Clear a model's ignored `.soma/env`
  only if its environment needs to be recreated; retain its requirements file.
- **Package installation fails:** read the named package and error. The pinned
  requirements must support the global Python. Resolve that compatibility
  issue before changing the SOMA pin or installing a different Python.
- **Terminal or viewer fails:** check doctor first. App logs are under
  `.cache/app-data/logs/`. Setup applies the macOS terminal-helper permission
  fix. Do not edit tracked vendor files to repair installed dependencies.
- **Other platforms:** Linux and Windows wrapper operation is not validated.
  The wrapper currently uses POSIX virtual-environment paths.

CalculiX is not configured. FEM and the full upstream GUI suite are outside
the checks performed here. The pinned npm dependencies have audit advisories;
see the [validation record](validation.md) for the observed count and tool
versions. Setup does not run automatic audit fixes or update the source pin.

## Setup contract

The first setup must prove a native model build, STEP output, app startup, and
the upstream type and unit checks on this Mac. Global tools remain global;
SOMA's source, npm lockfile, and CAD package requirements are pinned. The source
runtime and generated app data stay local. See [validation.md](validation.md) for observed
versions and check results.
