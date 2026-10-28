# Cabineteer in Buratino

This directory contains the tracked Cabineteer source used by Buratino. It is
an editable local dependency; Buratino's lock file and launcher select the
runtime used by the workspace.

Start with the [Buratino guide](../../README.md), then use the
[project authoring guide](../../docs/designing.md) and its runnable examples.
For Cabineteer internals, see [architecture](docs/architecture.md),
[project inputs and saved data](docs/projects.md), and the
[MCP reference](docs/mcp.md).

To set up the Buratino workspace, run `./buratino/bin/buratino setup` from the
repository root. This installs the locked runtime and viewing assets under
`buratino/.local/`. Use `./buratino/bin/buratino test-native` to run the
Cabineteer tests through that runtime. See [local setup](docs/local-setup.md)
and [contributing](CONTRIBUTING.md) for the current commands.

## Upstream and license

Cabineteer is based on [chemrich/cabineteer](https://github.com/chemrich/cabineteer).
The upstream project and contributors retain their attribution. This software
is licensed under the [Apache License 2.0](LICENSE); see [NOTICE](NOTICE) and
[ATTRIBUTIONS.md](ATTRIBUTIONS.md) for notices and source references.
