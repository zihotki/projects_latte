# Shared CAD Lab setup

**Status:** Historical design, 13 November 2026. The current implementation
and source-update workflow are described in [the CAD Lab guide](../../../cadlab/README.md).
The implementation allows an explicit branch update to select a new shared
commit without changing the repository's initial pin.

## Goal

Use one pinned SOMA installation for all CAD Lab worktrees. Work directly with
project files and the CLI, and show the active design in SOMA while Codex works.
Support one to three different designs open at the same time without installing
SOMA in each worktree.

The [SOMA guide](https://somacad.app/docs/#your-own-folder) describes **Open
folder** as the standard way to use a repository folder, including from the
Codex app. The folder is the model. We confirmed that a folder with only
`model.py` can be built and exported by the CLI without first opening SOMA.

## One installation

Keep one source-based installation at:

```text
~/Library/Application Support/CAD Lab/SOMA/
```

Use the pinned fork commit recorded by the repository. It must be possible to
use an already installed matching version without initializing a separate SOMA
submodule or installing dependencies in each worktree. The installation must
not depend on a checkout that the user might delete. Continue to use the user's
global Node, npm, Python and uv; keep the one CAD Python environment with the
shared installation.

`cadlab install` creates the installation if it is missing. It reports and
reuses a matching installation. `cadlab doctor` reports its location, pin,
runtime versions and readiness. The existing `cadlab setup` remains a
compatible entry point. Normal design work must not silently install SOMA or
replace it when a pin does not match.

For an update, close the SOMA windows, finish CLI builds and exports, and run
an explicit replacement command.
Replace the single installation rather than keeping several versions. A failed
or incomplete installation must be reported as such and be recoverable by
running installation again. Keep a readiness marker and the installed commit
outside project folders. Do not delete worktree environments, project data, or
profiles as an automatic part of migration or update. Document any old files
that the user may remove later.

The shared location is an installation, not a disposable cache. Keep the pin
and installation instructions in the repository so it can be restored after a
cleanup. Allow `CADLAB_HOME` to select another location for isolated tests.
Initial setup needs permission to write to the selected user location when the
execution environment does not already grant it.

## Projects and the viewer

Project files stay in the worktree. Preserve `model.py`, inputs, parameters,
project-specific dependencies, and existing SOMA skills and settings. Build
and export must work from project files with SOMA closed. Keep fine mesh export
as the wrapper default, while allowing explicit overrides.

When implementing a design, Codex should open that exact folder in SOMA, check
that it is visible, and leave the viewer available as the files change. The
agent may create or edit the model first; a UI action is not needed for the CLI
to work. If a viewer cannot be opened, say so and continue the file work rather
than claiming the model is visible.

SOMA 0.11.0 starts on its home page. Its documented production interface opens
a folder through **Open folder**, and later offers it under **Recent**. Neither
the latest release nor the checked upstream `main` supports choosing a folder
at startup. Add a focused `--open-folder <path>` launch argument to the user's
SOMA fork. This starts one new SOMA instance and opens that exact folder. Reuse
SOMA's existing folder validation, registration, entry-point selection, and
project setup behavior, including its file-change notice and confirmation when
needed. Wait for the renderer to be ready, then show the viewer and dismiss the
home screen only after a successful open.

If the path is invalid, initialization fails, or the user cancels setup, show a
useful message and leave the home page available. Never silently create a model
in another folder, skip confirmation, or change the existing picker/Recent
workflow. Pass paths as separate arguments so spaces work. Use normal production
startup, not `SOMA_TEST`. Do not add a running-instance controller or change
upstream SOMA; implement the feature in the user's fork and review it. Before
publishing the CAD Lab pin, ensure the resulting fork commit is reachable from
the configured source so a clean installation can retrieve it. Publishing is an
explicit step, never an automatic side effect of installation. First validate
it in a temporary location; do not install or update the user's shared copy
until the user has reviewed the change.

The current CAD Lab skill and guide must stop presenting **Open folder** as a
prerequisite for file-based modeling. They should tell the agent to use the
active project's SOMA skills when available and explain how to use the shared
pinned skill templates and their declared defaults before a project has SOMA
metadata; raw templates contain placeholders. Keep existing user
guidance and skill settings. The SOMA UI may add its normal project metadata
when the folder is opened.

## Multiple projects: the simple case

Use the same installation for every SOMA instance. `cadlab run` accepts an
explicit project path, or uses the current design folder when none is supplied.
Resolve the canonical path and use it to select a separate `SOMA_USER_DATA`
profile. Launch the instance with that folder as its working directory and
pass it to the fork's `--open-folder` argument. With no design selected, start
on SOMA's home page instead of guessing a project. Keep these small profiles
outside the project folders, alongside the shared installation. This supports multiple
projects in one worktree as well as copies of a project in different worktrees.

Each profile has its own recent list, app preferences and render bridge. This
is intentional: SOMA may rewrite a copied project's ID if a single profile
already knows that ID at another folder, and two app processes using one
profile can overwrite its bridge file. There is no need for a port manager or a
background supervisor. As an operating rule, open only one viewer for a given
project folder and use separate profiles for different projects. The wrapper
does not need a duplicate-instance controller. Do not switch away from unsaved
editor changes.

`render` needs the matching viewer and its connection. Use the SOMA terminal
or another supported connection to that particular instance; do not assume a
CLI shell has the app's environment variables. Keep tokens out of project files
and logs. When the viewer cannot be identified by full folder path, ask the
user to select it rather than claiming a similarly named project is correct.

SOMA's `.soma/env` remains project-specific for extra Python packages. Before
a headless build or UI use, check whether the project environment is stale after the initial move from a worktree base or a shared-base update. Use
the native environment workflow to refresh it and restore tracked requirements
when needed. Report incompatible packages; do not erase project files or put
project-only packages in the shared base. Existing projects and enabled or
disabled SOMA skills must continue to work.

## Compatibility and checks

Update the CAD Lab wrapper, skill and documentation together. Preserve
`cadlab soma`, `doctor`, `run`, and scoped CAD Lab checks. Replace documented
commands that rely on `cadlab/.venv/bin/python` with a supported shared-runtime
or project-environment command. The root README and the sharpening jig's guide
and validation runner are known callers. Avoid running unrelated project tests.

Before accepting an implementation:

1. Install into an isolated test location whose path contains spaces. Check the
   pin, global tool selection, CLI and app startup. A second worktree with the
   same pin must reuse the installation without downloading dependencies.
2. Build and export a folder containing only `model.py` with no UI. Open the
   same folder directly in SOMA using the production launch argument and verify
   the actual model, rather than the home screen, is visible and rebuilds after
   an edit. Verify paths with spaces, invalid paths, and cancellation of SOMA's
   file-change confirmation; no other project or model may be opened or changed.
3. Open two different project folders at once, including two copies with the
   same project ID, using one installation and separate profiles. Use direct
   folder opening and check that each viewer shows the right folder and neither
   ID changes. The research probe started two hidden app processes with different working directories
   and profiles; it did not yet open two models.
4. Check a project-only dependency and its recovery after replacing the shared
   base. Test a mismatched pin, a missing installation and an interrupted
   install. Do not overwrite model files or remove other project data.
5. Check fine-detail exports, CAD Lab's scoped checks, and the updated skill
   and guide. Review the design with the user before installing or updating
   their shared SOMA installation.

## Proposed addition: headless project initialization

The user wants a project to open without a setup popup. Add an explicit SOMA
fork command that initializes an existing folder without starting a window or
asking questions. It takes the project path and entry script as arguments.
The entry must already exist; the command must not replace model files. It
uses the same folder setup code as the UI, preserves existing instructions,
and backs up files before changes. It reports the changes or a clear error and
is safe to run again.

CAD Lab selects the project's profile, runs this command, and opens the folder
only after initialization succeeds. A prepared project then opens directly
without a setup notice. Manual **Open folder** keeps its existing confirmation
when setup changes are needed. The exact command spelling is an implementation
detail; the command must be callable from the shared source installation.

Verify initialization and repeated initialization on folders with existing
files, names containing spaces, invalid entries, and setup conflicts. Verify
that the normal production UI opens the prepared project without a setup
notice, shows and rebuilds its model, and that separate project profiles can
run concurrently. The shared installation still requires user review before
it is installed or updated.
