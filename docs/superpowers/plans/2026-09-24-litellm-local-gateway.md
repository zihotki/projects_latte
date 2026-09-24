# Local LiteLLM Gateway Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an on-demand LiteLLM gateway for several local apps, with Keychain secrets and a verified incremental backup before each session.

**Architecture:** A top-level `litellm/` Compose project runs a local-only LiteLLM proxy and PostgreSQL. A project command starts PostgreSQL, takes a pgBackRest backup, then starts the proxy; stop removes the containers but keeps the database and backup repository.

**Tech Stack:** Docker Compose, LiteLLM `v1.102.1`, PostgreSQL `18.6-trixie`, pgBackRest `2.55.1-1`, Bash, macOS Keychain.

**Spec:** `docs/superpowers/specs/2026-09-24-litellm-local-gateway-design.md`

## Global Constraints

- Keep this project separate from `cut_on_eight/` and bind the proxy only to `127.0.0.1:4000`.
- Keep model aliases in Git-tracked YAML and mutable keys, budgets, and spend in PostgreSQL.
- Keep all four long-lived secrets in macOS Keychain. Do not create a persistent plaintext `.env` or install host packages.
- Default backups to `~/.local/share/projectslatte/litellm-backups`, outside Docker's data store. Keep two full backup chains.
- Take a full backup first and after seven days without a full backup; otherwise take an incremental backup before the proxy starts.
- On backup failure, do not start LiteLLM. Stop any PostgreSQL container that this start command created.
- Run `./scripts/check.sh` and `./scripts/test.sh` before handoff; run `./scripts/integration.sh` when Docker is available.

## Review Focus

- Missing or empty Keychain item: fail before creating containers and print only the item name.
- Missing or unwritable backup directory: fail before starting the proxy; leave the database volume untouched.
- Repeated `start` while the gateway is running: report its state; do not create a second backup.
- Interrupted or failed backup: return nonzero, leave no proxy running, and keep the last valid backup chain.
- Restore check: use a new temporary volume and prove the live database volume and service remain unchanged.

## File map

| File | Responsibility |
| --- | --- |
| `litellm/compose.yaml` | Service, volume, health, and secret wiring. |
| `litellm/Dockerfile.postgres` | Pin PostgreSQL and install the compatible pgBackRest package. |
| `litellm/config.yaml` | Public model aliases and database/master-key references. |
| `litellm/pgbackrest.conf` | Local backup repository, retention, compression, and stanza. |
| `litellm/bin/litellm` | User commands: `start`, `status`, `backup`, `stop`, `restore-check`. |
| `litellm/bin/proxy-entrypoint` | Read mounted secrets and launch LiteLLM. |
| `litellm/lib/secrets.sh` | Read required Keychain items without printing values. |
| `litellm/lib/backup.sh` | Inspect backup history and select full or incremental backup. |
| `litellm/bin/restore-check` | Restore and check an isolated temporary database. |
| `litellm/tests/smoke.sh` | Docker-backed session, backup, and restore contract. |
| `litellm/README.md` | Setup, commands, virtual keys, recovery, and limits. |
| `README.md` | Link to the new project. |

### Task 1: Container and Keychain boundary

**Files:** Create `litellm/compose.yaml`, `litellm/Dockerfile.postgres`, `litellm/config.yaml`, `litellm/pgbackrest.conf`, `litellm/bin/proxy-entrypoint`, `litellm/lib/secrets.sh`; modify `README.md` only when the project guide exists in Task 3.

**Interfaces:** `lib/secrets.sh` exports `LITELLM_MASTER_KEY`, `LITELLM_SALT_KEY`, `POSTGRES_PASSWORD`, and `OPENROUTER_API_KEY` only in the calling process. Compose maps each host variable to a service-scoped secret; the proxy entrypoint reads `/run/secrets/*` and builds `DATABASE_URL` from the database password.

- [ ] **Step 1: Define the secret contract.** Use `security find-generic-password -a "$USER" -s "projectslatte.litellm.<name>" -w` for `master`, `salt`, `postgres`, and `openrouter`. Reject empty results. Keep `set -x` disabled, avoid secret arguments, and never print values. Test the missing-item path with a temporary empty Keychain name before using real items.
- [ ] **Step 2: Add the pinned container files.** Base PostgreSQL on `postgres:18.6-trixie`; install `pgbackrest=2.55.1-1` from Debian trixie. Pin the LiteLLM image to `ghcr.io/berriai/litellm:v1.102.1`. Use `POSTGRES_PASSWORD_FILE`, a named PostgreSQL volume, a host bind for backups, and `127.0.0.1:4000:4000` only on LiteLLM. Configure pgBackRest WAL archiving, compression, and `repo1-retention-full=2`.
- [ ] **Step 3: Add `config.yaml` and proxy entrypoint.** Expose `agent-cheap` through `openrouter/z-ai/glm-5.3-flash` and `agent-strong` through `openrouter/z-ai/glm-5.3`. Reference the master key, database URL, and OpenRouter key from the wrapper's environment. The wrapper must fail on an absent mounted secret and then `exec` the proxy.
- [ ] **Step 4: Verify the boundary.** Run `bash -n` on new shell files and `docker compose -f litellm/compose.yaml config --quiet` with disposable dummy host secrets. Inspect the rendered config for localhost binding and absence of inline secret values. Build the PostgreSQL image and check `pgbackrest version` reports `2.55.1`; confirm LiteLLM's pinned image supports the host architecture before continuing.
- [ ] **Step 5: Commit.** Commit the container and Keychain boundary as one reviewable change.

### Task 2: Session lifecycle and incremental backup

**Files:** Create `litellm/bin/litellm`, `litellm/lib/backup.sh`, `litellm/tests/smoke.sh`; adjust Compose and pgBackRest config from Task 1 as required by actual startup tests.

**Interfaces:** `bin/litellm start|status|backup|stop` is the public local command. `backup.sh` reads `pgbackrest --stanza=litellm info --output=json`, chooses `full` when no full backup exists or the newest full is at least seven days old, and chooses `incr` otherwise.

- [ ] **Step 1: Write the smoke contract.** In a disposable Compose project and backup directory, assert: first `start` makes a full backup before proxy readiness; `stop` leaves the volume; second `start` makes an incremental backup; a third `start` while running adds no backup; a missing Keychain item or unwritable backup path never starts the proxy. Exercise the seven-day full-backup choice with controlled backup metadata. Force one backup failure and confirm the last valid chain remains available. Use synthetic local secrets and no paid provider request.
- [ ] **Step 2: Implement `start`.** Load Keychain items, resolve the backup directory to an absolute path, require it to be private and writable, and check Docker. If the proxy is already running, report it and exit. Otherwise start PostgreSQL alone, wait for health, initialize/check the pgBackRest stanza, print the last successful backup, run the chosen backup, then start LiteLLM and wait for readiness. Use a trap to stop only containers started by this invocation on failure.
- [ ] **Step 3: Implement `backup`, `status`, and `stop`.** `backup` requires running PostgreSQL and uses the same full/incremental rule. `status` reports container state, backup path, and the newest successful backup time/type; use a one-off image to read pgBackRest metadata when the stack is stopped. `stop` uses `docker compose down` without `--volumes`; it must work even if Keychain access is unavailable.
- [ ] **Step 4: Run the smoke contract.** Verify the full and incremental backup labels in pgBackRest output, service ordering, failure cleanup, and no secret values in logs or `docker inspect` configuration. Record exact commands and observed output in the task review.
- [ ] **Step 5: Commit.** Commit the working lifecycle and backup flow.

### Task 3: Restore check and operating guide

**Files:** Create `litellm/bin/restore-check`, `litellm/README.md`; update `litellm/tests/smoke.sh` and root `README.md`.

**Interfaces:** `bin/litellm restore-check` invokes the isolated restore script and returns success only after the restored PostgreSQL instance accepts a query. It never changes the live Compose volume.

- [ ] **Step 1: Extend the smoke contract.** Create a virtual key through LiteLLM's local admin API, run `bin/litellm backup`, stop the stack, run `restore-check`, and verify that the restored database contains the key record. Confirm the live volume identity is unchanged, then start the normal stack again and confirm it still has the key. Keep the synthetic master key within the test process.
- [ ] **Step 2: Implement isolated restore.** Create a uniquely named temporary Docker volume and restore the latest pgBackRest backup into it. Start a temporary PostgreSQL container on the project network without publishing a port, check readiness and a database query, then remove the temporary container and volume in a trap. Never invoke `docker compose down --volumes` or target the live volume.
- [ ] **Step 3: Document setup and recovery.** Give exact Keychain creation commands that use `security add-generic-password ... -w` with `-w` last, so it prompts instead of putting a secret in the process arguments. Explain Docker Desktop startup, `start/status/backup/stop/restore-check`, per-app virtual keys, local-only access, backup location and retention, how to restore a lost live volume, and the need for a separate copy of the Keychain and backup directory for whole-Mac loss.
- [ ] **Step 4: Verify and commit.** Run the smoke contract, `./scripts/check.sh`, and `./scripts/test.sh`; run `./scripts/integration.sh` when Docker is available. Report any environment block exactly. Commit the guide and restore check.

## Self-review

- Spec coverage: Tasks 1–3 cover isolation, model aliases, Keychain secrets, session startup, incremental retention, and recovery.
- Interfaces: one public `bin/litellm` command owns lifecycle; the restore script is called only through it.
- Review focus: every listed failure condition has a smoke assertion in Task 2 or Task 3.
- Paid calls: no automated test sends a request to OpenRouter.
