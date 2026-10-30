# Local setup

This fork is part of the Buratino workspace. Use the repository launcher for
Buratino work. It creates the locked Python environment in `buratino/.venv/`
and viewing assets in `buratino/vendor/three/`.

Run from the repository root:

```bash
./buratino/bin/buratino setup
./buratino/bin/buratino doctor
./buratino/bin/buratino build projects/spaces-fixed-drawers
```

The launcher runs Buratino commands with the pinned Cabineteer source from
`buratino/vendor/cabineteer`. Use its test commands when you change this
source:

```bash
./buratino/bin/buratino check
./buratino/bin/buratino test-native tests/test_space_assembly.py
./buratino/bin/buratino test-native tests/test_space_integration.py
```

`test-native` runs pytest in the Cabineteer directory with Buratino's locked
Python environment. Add a focused test path after the command, or omit it to
run the full Cabineteer suite. `test` runs the Buratino tests.

## Standalone Cabineteer MCP

The package also has a standalone MCP entry point. This runs Cabineteer from
its own project environment, not Buratino's locked workspace runtime. From the
repository root, configure a client to use the vendored directory:

```bash
claude mcp add cabineteer -- uv --directory "$PWD/buratino/vendor/cabineteer" run cabineteer
```

For another MCP client, use the same `uv --directory ... run cabineteer`
command as its stdio server command. `cabineteer --http` starts its separate
HTTP/SSE transport. See [mcp.md](mcp.md) for tool groups and transport details.

## Source and attribution

Cabineteer source is editable in `buratino/vendor/cabineteer/src/cabineteer`.
The root `buratino/pyproject.toml` selects it as an editable dependency. Keep
the upstream notices and source references in `NOTICE`, `LICENSE`, and
`ATTRIBUTIONS.md` with the fork.
