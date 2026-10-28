# Contributing to Cabineteer in Buratino

Cabineteer is tracked source inside the Buratino workspace. Edit
`buratino/vendor/cabineteer/src/cabineteer` in place. The root
`buratino/pyproject.toml` points to this source as an editable dependency.

From the repository root, set up the locked runtime with:

```bash
./buratino/bin/buratino setup
```

Use the command that matches the changed area:

```bash
./buratino/bin/buratino check
./buratino/bin/buratino test-native tests/test_project.py
./buratino/bin/buratino test-native tests/test_space_assembly.py
./buratino/bin/buratino test-native tests/test_profile_consumers.py
```

Add focused test paths after `test-native`. Run it without a path when a full
Cabineteer suite is needed. `./buratino/bin/buratino test` runs Buratino's
tests. The Cabineteer eval harness is in `evals/`. Run it from the repository
root with Buratino's locked runtime when a change affects tool behavior covered
by prompt scenarios:

```bash
PYTHONPATH=buratino/vendor/cabineteer buratino/.local/venv/bin/python -m evals --list
PYTHONPATH=buratino/vendor/cabineteer buratino/.local/venv/bin/python -m evals --name <scenario>
```

The schema and dispatch for MCP tools live in `src/cabineteer/server.py`.
CabinetProject serialization and patch behavior live in
`src/cabineteer/project.py`. Native Space and profile inputs are defined in
`spaces.py`, `space_assembly.py`, `profiles.py`, and `layout.py`.

Keep source attribution with the fork. `NOTICE`, `LICENSE`, and
`ATTRIBUTIONS.md` record the upstream license and references for hardware and
joinery data.
