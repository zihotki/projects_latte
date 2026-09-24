# Local LiteLLM Gateway Design

## Purpose and scope

Projects Latte will contain a standalone LiteLLM gateway for several apps on
one Mac. The user starts it for development or automation sessions and stops it
afterward. Apps use one local OpenAI-compatible endpoint and separate LiteLLM
virtual keys. OpenRouter is the first upstream provider. The project does not
change Cut on Eight or run as a permanent background service.

Success means the user can start the gateway, use a virtual key from an app,
stop it, and later recover its keys and spend state from a database backup.

## Components and data ownership

The new top-level `litellm/` project owns its Compose file, LiteLLM model
configuration, startup commands, backup commands, and operating guide. It has
no dependency on Cut on Eight's Aspire or PostgreSQL resources.

Compose runs one LiteLLM proxy and one PostgreSQL instance. The proxy listens
on `127.0.0.1:4000`. PostgreSQL has no published host port and uses a named
Docker volume. The PostgreSQL image includes pgBackRest so its archive command
and backup command use the same version and configuration. No Redis, UI model
storage, cloud backup service, or system-wide package installation is needed.
Images and backup-tool versions are pinned to tested releases.

`litellm/config.yaml` owns stable aliases `agent-cheap` and `agent-strong`.
Initially they route to OpenRouter's `z-ai/glm-5.3-flash` and `z-ai/glm-5.3`.
The model mapping is reviewed in Git. PostgreSQL owns virtual keys, their
access settings, budgets, and spend records. Each app has its own virtual key;
the master key is reserved for administration. Apps use
`http://127.0.0.1:4000/v1` and their virtual key. The Admin UI remains local.

## Secrets

The LiteLLM master key, salt key, PostgreSQL password, and OpenRouter API key
are macOS Keychain generic-password items with project-specific names. The
project creates no `.env` or other persistent plaintext secret file. A local start
command reads the items without printing them and provides them as host
environment-sourced Compose secrets. Compose grants only the required secrets
to each service. PostgreSQL reads its password from a secret file. A small
LiteLLM startup wrapper reads its mounted secrets and sets the environment
variables required by LiteLLM, then starts the proxy. Secret values are not
written to the Compose file, image, shell history, project logs, or container
configuration. Compose and Docker hold the secrets while the containers run.
A local user with Docker control or access to the running container can read
them.

Setup guides the user to create or import the Keychain items without putting
secret values on a command line. A missing or empty item stops startup before
any container is created. The salt key is stable for the lifetime of the
database; the setup path does not overwrite it silently.

## Session lifecycle

The project provides `start`, `status`, `backup`, and `stop` commands. If the
gateway is already running, `start` reports that state without taking another
backup. Otherwise, it loads Keychain secrets and verifies the backup path. It starts
PostgreSQL alone and waits for a healthy database. It reports the last
successful backup, takes a new backup, and starts LiteLLM only after that
backup succeeds. The first backup is full. Later starts use an incremental
backup unless the last full backup is at least seven days old, in which case
they use a new full backup. A failed backup stops the newly started PostgreSQL
container, leaves LiteLLM stopped, and reports the problem. `backup` permits a
manual backup while PostgreSQL is running.

`status` reports service state, the latest successful backup time and type,
and the backup repository path. `stop` stops and removes the Compose
containers without deleting the PostgreSQL volume or backup files. Nothing is
scheduled to run while the project is stopped. A database backup taken before
startup covers the previous session's state, but the current session is not
backed up until the next start or a manual `backup` command.

## Backups and recovery

pgBackRest stores compressed full and incremental backups with the WAL needed
to restore them. It keeps two full backup chains and expires dependent
incrementals with their full backup. The backup repository is a private local
host directory outside Docker's data store, defaulting to
`~/.local/share/projectslatte/litellm-backups`; the user can select another
absolute local directory. The project does not copy Keychain secrets into this
directory.

The project includes a documented restore procedure for loss or corruption of
the Docker database volume. Restore requires the backup repository and the
same Keychain secrets, especially the salt key. A restore-check command
restores the latest backup into an isolated temporary database volume and
checks database readiness without touching the live volume. The operating
guide states how to inspect backup age, run a manual backup, check a restore,
and recover from a failed backup or database start.

These local backups cover Docker data loss while the Mac and its Keychain remain
available. Recovery from loss of the Mac also requires the user's separate
backup of the local backup directory and Keychain items. This project does not
create an off-machine copy.

## Failure behavior and verification

Startup stops with an actionable error for unavailable Docker, missing
Keychain items, an unwritable backup path, an unhealthy database, or a failed
backup. Secrets are excluded from diagnostics. LiteLLM never starts with an
unverified backup failure. The model configuration remains usable without
changing the stored virtual keys when upstream model routes are edited.

Verification checks the rendered Compose configuration without printing secret
values, local-only network binding, health ordering, virtual-key access, a
full backup, a later incremental backup, and an isolated restore. The repo's
`./scripts/check.sh` and `./scripts/test.sh` run before handoff;
`./scripts/integration.sh` runs when Docker is available. A live OpenRouter
request is an optional manual check because it spends provider credit.

## Sources

- [LiteLLM Docker quickstart](https://docs.litellm.ai/docs/proxy/docker_quick_start)
- [LiteLLM virtual keys](https://docs.litellm.ai/docs/proxy/virtual_keys)
- [Docker Compose secrets](https://docs.docker.com/reference/compose-file/secrets/)
- [pgBackRest user guide](https://pgbackrest.org/user-guide.html)
