# Local LiteLLM gateway

This project runs LiteLLM and PostgreSQL for local development. It is separate
from Cut on Eight. The API listens only on `127.0.0.1:4000`; apps use
`http://127.0.0.1:4000/v1`. Docker Desktop must be running. No host package
installation is required.

## First setup

Create five generic-password items in macOS Keychain. Run each command and
enter the secret at the prompt. The final `-w` is intentional: it prompts for
the value, so the value is absent from the command arguments and shell history.
Use long, distinct random values. The master key must start with `sk-`. Keep
the salt key safe: existing encrypted database data needs the same salt key.

```bash
security add-generic-password -a "$USER" -s projectslatte.litellm.master -w
security add-generic-password -a "$USER" -s projectslatte.litellm.salt -w
security add-generic-password -a "$USER" -s projectslatte.litellm.postgres -w
security add-generic-password -a "$USER" -s projectslatte.litellm.openrouter -w
security add-generic-password -a "$USER" -s projectslatte.litellm.mistral -w
```

These commands do not replace an existing item. Import the original salt key
when recovering an existing database. Start Docker Desktop, wait until its
engine is ready, then run the commands below from the repository root.

## Session commands

```bash
./scripts/litellm.sh help
./scripts/litellm.sh start
./scripts/litellm.sh status
./scripts/litellm.sh backup
./scripts/litellm.sh restore-check
./scripts/litellm.sh stop
```

Run these commands from the repository root. The wrapper shows available
commands with `help` or no arguments and suggests a next command after success.

`start` starts PostgreSQL, takes a backup, and then starts LiteLLM. It takes a
full backup first and after seven days without a full backup. Other starts take
an incremental backup. A failed backup prevents LiteLLM from starting. `backup`
takes a manual backup while PostgreSQL runs. Use it before `stop` to include
changes from the current session. `status` shows the latest successful backup
time and type. `restore-check` restores the latest backup into a temporary
Docker volume, runs a PostgreSQL query, and removes its temporary resources.
It does not modify the live database volume.
The session commands wait for one another. A second `start` cannot interrupt
the first command's backup or failure cleanup.

The backup repository defaults to
`~/.local/share/projectslatte/litellm-backups`, outside Docker's data store.
Set `LITELLM_BACKUP_DIR` to a private, writable absolute directory to use a
different location; use the same setting for every command. The directory
must be owned by your user and have mode `700`. pgBackRest keeps two full
backup chains and their dependent incremental backups.

If the database volume already exists, `start` requires the established
backup repository. It stops if that directory or its metadata is missing.
`status` only reads the repository; it does not create a missing directory.
First setup creates a new directory and repository when no database volume
exists.

## App keys and local access

Open the LiteLLM Admin UI at `http://127.0.0.1:4000/ui` while the gateway runs.
Use the Keychain master key only for administration. Create one virtual key
for each app, limit it to the required model aliases, and set a budget as
needed. Give the app its own key and the base URL
`http://127.0.0.1:4000/v1`. Grant the required task aliases from
[`config.yaml`](config.yaml) on that key. A config change does not change
stored virtual-key permissions. OpenRouter requests can spend provider
credit; the automated checks do not send one.

## Mistral native pass-through

Use the connection name `mistral-native` for clients and a dedicated virtual
key. This name identifies the connection; it is not a LiteLLM model alias.

| Setting | Value |
| --- | --- |
| Connection name / virtual-key alias | `mistral-native` |
| Client base URL | `http://127.0.0.1:4000/mistral/v1` |
| Chat Completions endpoint | `http://127.0.0.1:4000/mistral/v1/chat/completions` |
| Model ID | `zai-glm-5-3` |
| Reasoning effort | `low` (send `reasoning_effort` in each request) |
| Client authentication | LiteLLM virtual key |
| Provider key | Keychain item `projectslatte.litellm.mistral` |

The secret loader reads the provider key from Keychain. Compose mounts it as
`mistral_api_key`, and the entrypoint exports `MISTRAL_API_KEY` inside the
proxy process. No `.env` file or second copy in the UI is needed. The key is
required at startup, like the other gateway secrets.

The built-in `/mistral/*` route forwards native requests to Mistral without
LiteLLM model routing or format translation. Use Mistral's exact model ID in
the request. A model registration in the UI or `model_list` creates a separate
standard API route; it does not create an alias for native pass-through.
Existing OpenRouter routes and registrations are separate.

Set `reasoning_effort` to `low` in the client request defaults. Native
pass-through does not apply defaults from a LiteLLM model registration.
Clients must handle Mistral's native response format, including content
chunks when present.

Create a dedicated virtual key with alias `mistral-native` and
`allowed_routes: ["/mistral/*"]`. This permits native Mistral routes and blocks
the standard LiteLLM API. Check its access before giving it to a client. Do not
assume that permissions for the `agent-*` aliases grant native access or that
model restrictions have the same effect on both routes. LiteLLM documents
logging and streaming support for Mistral pass-through, but no cost tracking.
Do not rely on this route for cost-based budget enforcement.

After adding the Keychain item and changing Compose, recreate only the proxy
while PostgreSQL is running. Run this from the repository root with no other
session command in progress. It loads the current `config.yaml` too.

```bash
(
  set -e
  source litellm/lib/secrets.sh
  docker compose -f litellm/compose.yaml up -d --no-deps --force-recreate proxy
)
```

For a new session, use `./scripts/litellm.sh start` as usual. `start` does not
recreate a proxy that is already running.

Example native request (uses provider credit). Set `LITELLM_API_KEY` to the
client's virtual key before running it.

```bash
curl --fail-with-body --silent --show-error \
  http://127.0.0.1:4000/mistral/v1/chat/completions \
  -H "Authorization: Bearer $LITELLM_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"model":"zai-glm-5-3","messages":[{"role":"user","content":"Reply with OK."}],"reasoning_effort":"low","max_tokens":128}'
```

See [LiteLLM Mistral pass-through](https://docs.litellm.ai/docs/pass_through/mistral)
and [Mistral GLM 5.3](https://docs.mistral.ai/models/zai-glm-5-3).

## Model routing for agents

The gateway exposes five task aliases. Each has a different primary model
and one fallback. The roles are intended uses, not measured quality rankings.

| Alias | Intended use | Primary model | Fallback model |
| --- | --- | --- | --- |
| `agent-fast` | Extraction, classification, short text | Qwen 3.8 Flash | MiMo 2.6 Flash |
| `agent-code` | Python, SQL, code generation | DeepSeek V4 Flash 0731 | MiMo 2.6 Flash |
| `agent-tools` | Tool calls and agent workflows | MiMo 2.6 Flash | DeepSeek V4 Flash 0731 |
| `agent-review` | Code review and verification | GLM 5.3 Flash | DeepSeek V4 Flash 0731 |
| `agent-reasoning` | Complex analysis and planning | GLM 5.3 | GLM 5.3 Flash |

Each alias has two `model_list` entries with the same `model_name`. The
primary has `litellm_params.order: 1`; its fallback has `order: 2`. Backend
settings are shared through YAML anchors. kagent needs the gateway URL,
its virtual key, and one task alias. Model and provider selection stay in
LiteLLM.

All OpenRouter task routes require support for the request parameters and
limit input pricing to $0.23 per million tokens. There is no output-price cap. GLM 5.3
currently costs about $3.07-$3.40 per million output tokens on the approved
endpoints, so use `agent-reasoning` only when that cost is justified.
Prices can change; the input cap applies to each OpenRouter request.

Open-weight backends require FP8. Qwen uses Alibaba only, whose reported
precision is unknown; this is the one explicit precision exception.
Provider order and allowlists are defined in `config.yaml`. MiMo prefers
InferenceNet, then Xiaomi. DeepSeek prefers Baseten, then DeepInfra. GLM
Flash prefers Baseten, then NextBit. GLM 5.3 prefers Sail Research, then
Morph. These choices use current endpoint metadata and still need live
quality tests.

There are zero retries within a deployment and one fallback model per
alias. Fallback applies to errors other than HTTP 429 too. If both models
fail, the error returns to the app. OpenRouter may also try the second
approved provider for a model. Client-supplied routing or retry overrides
are not blocked by this configuration; use key restrictions and request
validation when a strict access boundary is required.

### Alias migration

The old aliases have been removed. Existing agents and their virtual-key
grants must be updated separately before they can use this catalog.
These mappings are starting points; choose the alias for the agent's task.

| Removed alias | Suggested task alias |
| --- | --- |
| `custodea-python-author`, `agent-author` | `agent-code` |
| `custodea-fast`, `agent-cheap`, `agent-qwen-flash` | `agent-fast` |
| `custodea-capable` | `agent-review` |
| `agent-strong` | `agent-reasoning` |
| `agent-mimo-flash-fp8` | `agent-tools` |

Do not put upstream model IDs, provider keys, or fallback lists in kagent.
After an edit to `config.yaml`, restart the proxy to load the file. Its
Compose configuration loads this file at startup and has no live reload
endpoint. A proxy restart leaves PostgreSQL and its data volume running.

The host port is bound to loopback. Other computers cannot reach it through
the host network. Anyone with local Docker control or access to the running
containers can read their secrets.

## Check and recover

Run `status` to inspect backup age. Run `backup` after important key or budget
changes. Run `restore-check` before relying on a backup for recovery. If a
backup fails, inspect `docker compose -f litellm/compose.yaml logs postgres`,
check that the backup directory is writable and has space, then retry `start`.
If PostgreSQL does not start, inspect the same logs and run `restore-check`
against the last backup before changing the live volume.

If the backup directory disappears, stop the gateway and restore that directory
from your separate copy. Check it with `./scripts/litellm.sh restore-check`
before `start`. If the repository cannot be recovered but the live database
volume is intact, preserve any old repository files elsewhere and run
`./scripts/litellm.sh start --reinitialize-backup-repo`. This explicit command
requires PostgreSQL to be stopped and the selected backup directory to be
absent or empty. It creates a new full backup from the live database. Earlier
backup points are unavailable from the new repository. If the first ever
backup failed and left an empty repository with a database volume, use the
same command to retry initialization.

To restore a **lost** live volume, stop the stack, confirm a recent backup with
`restore-check`, and use the commands below. They restore into a newly created
live volume. If the old volume still exists but is corrupt, preserve it for
investigation before removing it; `docker volume rm` deletes its data. Use the
same backup directory and Keychain items, especially the original salt key.

```bash
./scripts/litellm.sh stop
./scripts/litellm.sh restore-check
export LITELLM_BACKUP_DIR="${LITELLM_BACKUP_DIR:-$HOME/.local/share/projectslatte/litellm-backups}"
image=projectslatte/litellm-postgres:18.6-trixie-pgbackrest-2.55.1
volume="$(docker compose -f litellm/compose.yaml config --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["volumes"]["postgres-data"]["name"])')"
docker volume create "$volume"
docker run --rm --volume "$volume:/var/lib/postgresql" --entrypoint sh "$image" -c \
  'mkdir -p /var/lib/postgresql/18/docker && chown -R postgres:postgres /var/lib/postgresql'
docker run --rm --user postgres --volume "$volume:/var/lib/postgresql" \
  --volume "$LITELLM_BACKUP_DIR:/var/lib/pgbackrest:ro" \
  --entrypoint pgbackrest "$image" --stanza=litellm restore
./scripts/litellm.sh start
```

Use this sequence only when the named live volume is absent or empty. A full
Mac loss also requires a separate copy of the backup directory and the four
Keychain secrets. This project does not make that separate copy.
