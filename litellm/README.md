# Local LiteLLM gateway

This project runs LiteLLM and PostgreSQL for local development. It is separate
from Cut on Eight. The API listens only on `127.0.0.1:4000`; apps use
`http://127.0.0.1:4000/v1`. Docker Desktop must be running. No host package
installation is required.

## First setup

Create four generic-password items in macOS Keychain. Run each command and
enter the secret at the prompt. The final `-w` is intentional: it prompts for
the value, so the value is absent from the command arguments and shell history.
Use long, distinct random values. The master key must start with `sk-`. Keep
the salt key safe: existing encrypted database data needs the same salt key.

```bash
security add-generic-password -a "$USER" -s projectslatte.litellm.master -w
security add-generic-password -a "$USER" -s projectslatte.litellm.salt -w
security add-generic-password -a "$USER" -s projectslatte.litellm.postgres -w
security add-generic-password -a "$USER" -s projectslatte.litellm.openrouter -w
```

These commands do not replace an existing item. Import the original salt key
when recovering an existing database. Start Docker Desktop, wait until its
engine is ready, then run the commands below from the repository root.

## Session commands

```bash
litellm/bin/litellm start
litellm/bin/litellm status
litellm/bin/litellm backup
litellm/bin/litellm restore-check
litellm/bin/litellm stop
```

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
`http://127.0.0.1:4000/v1`. The tracked aliases are `agent-cheap` and
`agent-strong` in [`config.yaml`](config.yaml). Changing a route there does
not change stored virtual keys. OpenRouter requests can spend provider credit;
the automated checks do not send one.

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
from your separate copy. Check it with `litellm/bin/litellm restore-check`
before `start`. If the repository cannot be recovered but the live database
volume is intact, preserve any old repository files elsewhere and run
`litellm/bin/litellm start --reinitialize-backup-repo`. This explicit command
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
litellm/bin/litellm stop
litellm/bin/litellm restore-check
export LITELLM_BACKUP_DIR="${LITELLM_BACKUP_DIR:-$HOME/.local/share/projectslatte/litellm-backups}"
image=projectslatte/litellm-postgres:18.6-trixie-pgbackrest-2.55.1
volume="$(docker compose -f litellm/compose.yaml config --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["volumes"]["postgres-data"]["name"])')"
docker volume create "$volume"
docker run --rm --volume "$volume:/var/lib/postgresql" --entrypoint sh "$image" -c \
  'mkdir -p /var/lib/postgresql/18/docker && chown -R postgres:postgres /var/lib/postgresql'
docker run --rm --user postgres --volume "$volume:/var/lib/postgresql" \
  --volume "$LITELLM_BACKUP_DIR:/var/lib/pgbackrest:ro" \
  --entrypoint pgbackrest "$image" --stanza=litellm restore
litellm/bin/litellm start
```

Use this sequence only when the named live volume is absent or empty. A full
Mac loss also requires a separate copy of the backup directory and the four
Keychain secrets. This project does not make that separate copy.
