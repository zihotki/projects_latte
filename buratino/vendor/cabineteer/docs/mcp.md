# Cabineteer MCP tools

`src/cabineteer/server.py` defines the MCP schemas, handlers, and
`TOOL_DISPATCH`. The server exposes cabinet design, evaluation, project,
visualization, and document-generation tools over stdio. It also supports
HTTP/SSE mode. This is the standalone Cabineteer interface; Buratino's locked
workspace launcher is separate. See [local setup](local-setup.md).

## Project workflow

| Tool | Purpose |
|---|---|
| `design_project` | Validate and save a project payload. Existing names need `overwrite: true`. |
| `list_projects` | Find saved projects. |
| `load_project` | Return the saved payload and resolved summary. |
| `update_project` | Patch a saved project and return the resolved summary and change log. |
| `duplicate_project`, `rename_project`, `delete_project` | Manage saved project names and copies. |
| `evaluate_project` | Resolve and evaluate project inputs. |
| `visualize_project` | Build a project visualization. |
| `generate_project_cutlist` | Generate project cutlist outputs. |
| `generate_assembly_instructions` | Generate assembly instructions for supported cabinet inputs. |

`design_project` and `update_project` accept the native Space and profile
blocks described in [projects.md](projects.md). Saved project JSON uses
`input_schema_version: 2`. `update_project` replaces a submitted native block
as a whole; it does not merge fields inside that block. Cabinet configs and
shared design tokens have their own field-level patch behavior.

## Cabinet tools

The server also provides focused tools for cabinet, drawer, door, leg, and pull
design; hardware and joinery discovery; proportion suggestions; evaluation
and description; cabinet visualization; and cutlist generation. Tool schemas
in `server.py` define current arguments, defaults, and output details.

## Run the standalone server

The standalone package entry point is `cabineteer`. Run it from
`buratino/vendor/cabineteer` with that package's uv environment:

```bash
uv run cabineteer
uv run cabineteer --http --port 3749
```

The default is stdio. HTTP mode exposes the SSE endpoint and can select a free
port if the requested port is occupied. The locked Buratino setup uses
`./buratino/bin/buratino setup` and does not use this command to build a
Buratino project. See [local setup](local-setup.md) for MCP client examples.
