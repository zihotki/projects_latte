# Cabineteer eval harness

The eval harness in `evals/` runs tool handlers from `server.TOOL_DISPATCH`
without starting an MCP server. Use it for changes to tool behavior covered by
prompt scenarios. Run these commands from the repository root with Buratino's
locked runtime:

```bash
PYTHONPATH=buratino/vendor/cabineteer buratino/.venv/bin/python -m evals --list
PYTHONPATH=buratino/vendor/cabineteer buratino/.venv/bin/python -m evals --name <scenario>
PYTHONPATH=buratino/vendor/cabineteer buratino/.venv/bin/python -m evals --tag <tag>
PYTHONPATH=buratino/vendor/cabineteer buratino/.venv/bin/python -m evals --json
```

Scenario inputs and assertions live in `evals/scenarios.py`. The command lists
current scenario names and tags, so docs do not need a maintained count.

For changes to the tracked source, use `./buratino/bin/buratino test-native
<path>` from the repository root. See [contributing](../CONTRIBUTING.md).
