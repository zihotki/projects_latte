# CAD Lab

CAD Lab keeps model files in this repository. CAD Lab Viewer and the SOMA
Python engine run from a local [SOMA fork](https://github.com/zihotki/SOMA)
source checkout.

## Setup

On macOS, install Git, Node.js 22.13.0 or newer, npm, uv, and Python 3.11
or newer. Xcode Command Line Tools may be needed for Python packages. Set up
the source checkout once:

```sh
git clone https://github.com/zihotki/SOMA.git cadlab/soma-fork-work
git -C cadlab/soma-fork-work remote add upstream https://github.com/Kai-Jungsthoefel/SOMA.git
uv venv --python 3.11 cadlab/soma-fork-work/.venv
uv pip sync --python cadlab/soma-fork-work/.venv/bin/python cadlab/soma-fork-work/python/requirements-base.txt
uv pip install --python cadlab/soma-fork-work/.venv/bin/python --no-deps --editable cadlab/soma-fork-work/python
npm ci --prefix cadlab/soma-fork-work/app
node cadlab/soma-fork-work/app/node_modules/electron/install.js
./cadlab/bin/cadlab doctor
```

The wrapper accepts local source changes. Set `CADLAB_SOMA_SOURCE` to use a
different checkout with the same `.venv` layout. `cadlab paths` shows the
selected paths. Set `CADLAB_HOME` to change the location of viewer profiles.

## Open and create projects

Create a folder under `cadlab/projects/` with a `model.py` script. You can
copy `cadlab/projects/example/model.py` as a starting point. Open a design:

```sh
./cadlab/bin/cadlab run --project cadlab/projects/example
```

The wrapper builds the app, initializes the folder, and opens it in the viewer.
From a project folder, `cadlab run` selects that folder. Elsewhere, it opens the
viewer home page. The positional form `cadlab run PATH` also works.

Each canonical project path gets a separate profile under CAD Lab's home
directory. Use one viewer per project folder. The project settings select skills
from the source checkout's shared library:

```sh
./cadlab/bin/cadlab skill 3d-printing --project cadlab/projects/example
```

## Build, export, and validate

```sh
./cadlab/bin/cadlab soma build --project cadlab/projects/example --json
./cadlab/bin/cadlab soma export --all --format stl --project cadlab/projects/example
./cadlab/bin/cadlab soma render --project cadlab/projects/example
./cadlab/bin/cadlab check
```

The viewer for the target project must be open for rendering. The wrapper
selects its profile even if the shell has credentials for another viewer. Build
and export work with the viewer closed. Mesh exports default to **fine**; an
explicit `--detail` overrides this. STEP files retain CAD surfaces.

`cadlab python` runs the source checkout's CAD Python environment. For example:

```sh
./cadlab/bin/cadlab python cadlab/projects/sharpening-stone-jig/checks/validate.py
```

SOMA keeps project-only packages in `.soma/env` and records them in the project
requirements file. The wrapper refreshes an existing project environment and
installs recorded requirements before a headless build or export.

`cadlab check` runs the wrapper tests and SOMA's TypeScript and unit checks.
Use project-specific checks when they apply. The
[CAD Lab skill](../.agents/skills/cadlab/SKILL.md) explains the modeling and
review workflow.

## Files and troubleshooting

Keep model code, inputs, project instructions, `.soma/project.json`, and
project requirements in Git when they belong to the design. Keep generated
skills, outputs, exports, and `.soma/env` out of Git. App logs are under
`profiles/<project-id>/logs/` inside `CADLAB_HOME`. If a project reports a
stale `.soma-init.lock`, check that no initialization is running before
removing the lock. CalculiX is not configured. Linux and Windows operation has
not been validated here.
