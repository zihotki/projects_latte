# Projects Latte

A repository for small, focused software projects.

## Projects

| Project | Description |
| --- | --- |
| [Cut on Eight](cut_on_eight/README.md) | Local browser-based dance-video segmentation and cataloguing. |
| [LiteLLM gateway](litellm/README.md) | Local AI model gateway with per-app keys and PostgreSQL backups. |
| [Buratino](buratino/README.md) | Furniture design harness with declarative cabinets, assemblies, and fronts. |
| [CAD Lab](cadlab/README.md) | Pinned SOMA source workspace for CadQuery designs with Codex. |

## Working with a project

Run project-owned commands from the repository root:

```bash
pnpm -C cut_on_eight install
pnpm -C cut_on_eight dev
pnpm -C cut_on_eight verify
```

Run the LiteLLM gateway from the repository root. The command prints the next
suggested action after each successful step:

```bash
./scripts/litellm.sh help
./scripts/litellm.sh start
./scripts/litellm.sh status
./scripts/litellm.sh backup
./scripts/litellm.sh restore-check
./scripts/litellm.sh stop
```

Set up and run a Buratino assembly example. See the
[design guide](buratino/docs/designing.md) to create furniture:

```bash
./buratino/bin/buratino setup
./buratino/bin/buratino build projects/space-assembly-fronts
./buratino/bin/buratino preview projects/space-assembly-fronts
```

Set up and run CAD Lab from pinned SOMA source:

```bash
git submodule update --init -- cadlab/vendor/soma
./cadlab/bin/cadlab setup
./cadlab/bin/cadlab run
```

Use **Open folder** in SOMA for designs under `cadlab/projects/`. Open the same
design folder in Codex. See the [CAD Lab guide](cadlab/README.md) for project
creation, commands, upgrades, and platform limits.

## Repository checks

Buratino uses `buratino/.venv/` for its Python environment,
`buratino/.cache/` for generated runtime data, and `buratino/vendor/` for
dependencies. See its [setup guide](buratino/README.md).

```bash
pnpm -C cut_on_eight install --frozen-lockfile
./buratino/bin/buratino setup
./scripts/check.sh       # TypeScript build/type/lint/format and Python static checks
./scripts/test.sh        # Unit tests
./scripts/integration.sh # Docker PostgreSQL, Qdrant, and media integration tests
./scripts/verify.sh      # Full local CI suite
```

`verify.sh` needs Docker and FFmpeg. GitHub Actions runs the same command on
pull requests and pushes to `main`.

Each project documents its own prerequisites, architecture, and workflows in its
README.

## License

This repository is licensed under the [Functional Source License 1.1, MIT Future
License](LICENSE.md) (`FSL-1.1-MIT`). Each release becomes available under the
MIT License two years after its release date.
