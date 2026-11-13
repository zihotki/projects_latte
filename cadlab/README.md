# CAD Lab

CAD Lab keeps model files in this repository and uses one shared, source-based
SOMA installation. The initial source is your SOMA fork at branch
`feat/open-folder`, pinned by [soma-source.json](soma-source.json).

## Setup

On macOS, install global Git, Node, npm, uv, and Python 3.11 or newer. Xcode
Command Line Tools may be needed to build Python packages. Setup uses these
global tools; it does not install or pin their versions.

```sh
./cadlab/bin/cadlab install
./cadlab/bin/cadlab doctor
```

`setup` is an alias for `install`. The installation is shared by all CAD Lab
worktrees at `~/Library/Application Support/CAD Lab/SOMA`. A second install
reuses it. Set `CADLAB_HOME` to select another parent directory, for example in
a test. `cadlab paths` reports the source, Python environment, selected branch,
and exact installed commit. Setup does not require the old `vendor/soma`
submodule or `cadlab/.venv`.

## Open and create projects

Create a project folder under `cadlab/projects/` with a `model.py` script. You
can copy `cadlab/projects/example/model.py` as a starting point. From the
repository root, open a specific design:

```sh
./cadlab/bin/cadlab run --project cadlab/projects/example
```

CAD Lab initializes the folder with SOMA's headless command and opens that
exact folder in the viewer without a setup dialog. Existing SOMA project
settings and skills remain in the folder. SOMA backs up files it changes in the
project's shared app profile. Open the same folder in Codex and keep the viewer
open for review. From a project folder, `cadlab run` selects that folder; from
elsewhere, it opens the SOMA home page. The positional form `cadlab run PATH`
also works.

Each project path gets a separate profile under the shared CAD Lab directory.
This lets separate projects and worktrees use one installation at the same time.
Use one viewer per project folder. For `soma render`, use the SOMA terminal in
the viewer for the target project, so it has the correct connection.

## Build, export, and validate

From the repository root:

```sh
./cadlab/bin/cadlab soma build --project cadlab/projects/example --json
./cadlab/bin/cadlab soma export --all --format stl --project cadlab/projects/example
./cadlab/bin/cadlab check
```

The `soma` command passes native SOMA arguments through and defaults mesh
exports to **fine**. An explicit `--detail` overrides the default. In the app,
select **Export → Mesh settings → Fine** for each new app profile. STEP files
retain CAD surfaces and do not use mesh detail.

`cadlab python` runs the shared CAD Python environment. For example:

```sh
./cadlab/bin/cadlab python cadlab/projects/sharpening-stone-jig/checks/validate.py
```

SOMA keeps project-only packages in `.soma/env` and records them in the
project's requirements file. The wrapper refreshes an existing project
environment and installs its recorded requirements before a headless build or
export. It keeps project files and settings in place. SOMA also checks the
project environment when its viewer opens.

`cadlab check` runs SOMA's TypeScript and unit checks only. It does not run
checks for Buratino, Cut on Eight, or LiteLLM. Use the project-specific checks
when they apply. The [CAD Lab skill](.agents/skills/cadlab/SKILL.md) explains
the modeling workflow and how to find SOMA's skills.

## Select or update a source branch

The selected branch and installed commit are shared by all worktrees. Normal
launches do not fetch or update source. Close SOMA windows and finish builds
before replacing the installation:

```sh
./cadlab/bin/cadlab update                       # latest commit on selected branch
./cadlab/bin/cadlab update --branch feat/open-folder
./cadlab/bin/cadlab doctor
```

An update replaces the one shared installation and records its exact commit.
Use a fork branch containing CAD Lab's headless `init` and direct-open support.
If an update fails, the wrapper restores the prior installation when possible.
It does not delete project files or profiles. If an interrupted update leaves
`SOMA.previous` beside the installation, inspect it before retrying.

The repository's source file supplies the first install's known commit. It does
not force other worktrees to downgrade a shared installation after an explicit
update. To restore the original pin in a fresh location, set `CADLAB_HOME` to a
new directory and run `install`.

## Files and troubleshooting

Keep `model.py`, inputs, project instructions, `.soma/project.json`, copied
skills, and project requirements in Git when they belong to the design. Keep
outputs, exports, and `.soma/env` out of Git. The old `cadlab/.venv`,
`cadlab/.cache`, and `cadlab/vendor/soma` are no longer used by the wrapper;
they are left in place for the user to inspect or remove later.

If `doctor` reports a missing or incomplete installation, run `install` for a
new installation or `update` to replace an existing one. App logs are under
`profiles/<project-id>/logs/` inside `CADLAB_HOME`. If a project reports a
stale `.soma-init.lock`, check that no initialization is running before
removing the lock. CalculiX is not configured. Linux and Windows operation has
not been validated here.
