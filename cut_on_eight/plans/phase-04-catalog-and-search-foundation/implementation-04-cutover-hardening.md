# Cutover Hardening Implementation Plan

**Status:** Ready

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the PostgreSQL/filesystem system recoverable and operable, remove obsolete JSON authority, document backup/restore and deployment configuration, and prove Phase 4 through one pragmatic browser flow.

**Architecture:** The worker reconciles interrupted catalog/filesystem transitions and resumes idempotent jobs. A host-side backup script streams `pg_dump` from the persistent Podman container into the external data root. Legacy routes, repositories, contracts, and tests are deleted only after the new vertical slices pass.

**Tech Stack:** Slice 3 stack plus Node process utilities, `pg_dump` from the PostgreSQL container, and Playwright using the user's installed Chrome.

**Depends on:** [Slice 3 — Collections and Search](implementation-03-collections-and-search.md)

## Global Constraints

- Keep changes inside `projectslatte/cut_on_eight`; preserve both `AGENTS.md` files.
- Never inspect, modify, migrate, or delete legacy JSON files under the external
  data root. They are simply no longer read.
- Recovery may delete only application-owned staged/orphaned files proven
  unreferenced by PostgreSQL.
- Backups must be written on the macOS host under
  `~/cut-on-eight_data/backups/postgres/`, not inside the Podman machine.
- Do not add Docker commands, Dockerfiles, or Docker-only test tooling.
- Use the browser smoke as a phase checkpoint, not as a large UI test suite.
- Use installed Chrome through Playwright's `channel: 'chrome'`; do not install
  a Playwright browser system-wide.
- Complete automated verification before claiming Phase 4 is done. Clearly
  report any environment-only checks that remain for the user.

## File Map

```text
apps/server/src/
  recovery/{catalog-reconciler,recovery-report}.ts
  jobs/processors/delete-asset.ts
  scripts/{backup-postgres,reset-test-catalog}.ts

apps/web/e2e/phase-04.spec.ts
apps/web/playwright.config.ts

cut_on_eight/
  .env.example
  README.md
```

---

### Task 1: Reconcile Interrupted Work and Missing Assets

**Files:**
- Create: `apps/server/src/recovery/recovery-report.ts`
- Create: `apps/server/src/recovery/catalog-reconciler.ts`
- Create: `apps/server/src/jobs/processors/delete-asset.ts`
- Create: `apps/server/test/recovery-integration.test.ts`
- Modify: `apps/server/src/blobs/blob-store.ts`
- Modify: `apps/server/src/blobs/local-blob-store.ts`
- Modify: `apps/server/src/jobs/worker-runtime.ts`
- Modify: `apps/server/src/worker.ts`
- Modify: relevant fragment/video/projector handlers

**Interfaces:**
- `CatalogReconciler.run(now): Promise<RecoveryReport>`
- `BlobStore.list(prefix): AsyncIterable<BlobKey>`
- Recovery report contains counts and stable codes, never paths or content.

- [ ] **Step 1: Extend BlobStore for controlled reconciliation**

```ts
export interface BlobStore {
  list(prefix: 'incoming/' | 'videos/'): AsyncIterable<BlobKey>;
}
```

Add this method to the complete `BlobStore` interface from Slice 2. The local
adapter does not follow symlinks. It yields only validated keys under the
configured data root and ignores the backup directory.

- [ ] **Step 2: Reconcile stale receiving imports**

For `receiving` records older than one hour:

- remove their staged `incoming/` blobs;
- remove a published source only when no `assets` row references its exact key;
- delete the incomplete video record;
- record `stale_receiving_removed`.

A newer receiving record is left alone because an upload may still be active.

- [ ] **Step 3: Reconcile catalog-to-filesystem divergence**

For each authoritative asset:

- missing source asset: mark its video `failed` with
  `managed_source_missing`;
- missing current preview: remove the preview reference, mark its projection
  unaffected, and enqueue preview regeneration at the current fragment
  revision;
- existing current asset: no action.

For each application-owned file not referenced by `assets`:

- staged files older than one hour are deleted;
- published derived previews older than one hour are queued for `asset.delete`;
- published source files are reported as `orphan_source_detected` and left
  untouched for manual inspection unless their parent video is a proven stale
  `receiving` record.

This conservative source rule avoids deleting user media because of a catalog
bug.

- [ ] **Step 4: Resume durable catalog transitions**

Re-enqueue idempotently:

- queued/processing videos without live inspection work;
- deleting videos;
- overdue soft-deleted fragments;
- missing/current preview records;
- pending/failed search projections.

Use the entity/revision as each `singletonKey`; do not create a second custom
job table.

- [ ] **Step 5: Run reconciliation before normal worker fetch**

Worker startup order:

1. connect database and start `pg-boss`;
2. run one reconciliation pass;
3. log safe count-only report;
4. register normal handlers;
5. start heartbeat.

An unavailable Qdrant records projection requeues/failures but does not prevent
media handlers from starting. A PostgreSQL failure makes the worker unready and
terminates the process for Aspire to report.

- [ ] **Step 6: Add one integration test for crash states**

In one real-database/filesystem test, seed:

- stale and current receiving imports;
- a missing current preview;
- an overdue deleted fragment;
- a deleting video;
- a pending projection;
- an unreferenced derived file;
- an unreferenced source file.

Run the reconciler twice. Verify the first run repairs/queues the specified
states and the second is idempotent. Confirm the orphan source remains.

```bash
test -n "$CUT_ON_EIGHT_TEST_DATABASE_URL"
pnpm -C cut_on_eight test:server -- recovery-integration.test.ts
```

- [ ] **Step 7: Commit recovery**

```bash
git add cut_on_eight/apps/server/src/recovery cut_on_eight/apps/server/src/blobs cut_on_eight/apps/server/src/jobs cut_on_eight/apps/server/src/worker.ts cut_on_eight/apps/server/test/recovery-integration.test.ts
git commit -m "feat: reconcile interrupted catalog work"
```

---

### Task 2: Add Host-Side PostgreSQL Backup

**Files:**
- Create: `apps/server/src/scripts/backup-postgres.ts`
- Modify: `apps/server/package.json`
- Modify: root `package.json`
- Modify: `README.md`

**Interfaces:**
- `pnpm -C cut_on_eight backup:postgres`
- Writes a custom-format dump atomically to the external backup folder.

- [ ] **Step 1: Implement the backup script without a host PostgreSQL install**

Use the fixed AppHost container name `cut-on-eight-postgres`. The script:

1. Resolves `CUT_ON_EIGHT_DATA_ROOT` with the same config helper.
2. Creates `backups/postgres/`.
3. Runs `podman inspect` and reads `POSTGRES_USER` without printing any
   password.
4. Spawns:

```ts
const args = [
  'exec',
  'cut-on-eight-postgres',
  'pg_dump',
  '--username',
  postgresUser,
  '--dbname',
  'cut_on_eight',
  '--format',
  'custom',
  '--no-owner',
  '--no-privileges',
];
```

5. Streams stdout to
   `cut-on-eight-YYYYMMDDTHHMMSSZ.dump.part`.
6. Waits for exit code zero, fsyncs, then renames to `.dump`.
7. Deletes only its own incomplete `.part` on failure.

Use `spawn()` argument arrays and `pipeline()`; do not build a shell command.

- [ ] **Step 2: Add compact scripts**

Server:

```json
{
  "backup:postgres": "tsx src/scripts/backup-postgres.ts"
}
```

Root:

```json
{
  "backup:postgres": "pnpm --filter @cut-on-eight/server backup:postgres"
}
```

- [ ] **Step 3: Document backup and restore**

Document:

- named volumes survive AppHost/container recreation but not Podman-machine
  deletion;
- backup output is on the host;
- Qdrant needs no backup because it is rebuilt;
- stop API/worker writes or use PostgreSQL's consistent snapshot semantics;
- restore only into an empty/test database first;
- use the container's `pg_restore`, then run migrations and Qdrant rebuild.

Do not provide a destructive one-command restore wrapper.

- [ ] **Step 4: Run one manual backup check**

With the AppHost running:

```bash
pnpm -C cut_on_eight backup:postgres
```

Expected: a non-empty `.dump` appears under the external backup folder and
`podman exec cut-on-eight-postgres pg_restore --list <dump>` can list it when
the file is streamed into the container or inspected with a compatible local
tool.

- [ ] **Step 5: Commit backup support**

```bash
git add cut_on_eight/apps/server/src/scripts/backup-postgres.ts cut_on_eight/apps/server/package.json cut_on_eight/package.json cut_on_eight/README.md
git commit -m "feat: add host-side PostgreSQL backups"
```

---

### Task 3: Remove JSON Authority and Legacy Contracts

**Files:**
- Delete: `packages/contracts/`
- Delete: `apps/server/src/services.ts`
- Delete: `apps/server/src/storage/`
- Delete: `apps/server/src/imports/import-service.ts`
- Delete: `apps/server/src/imports/source-picker.ts`
- Delete: `apps/server/src/imports/source-validator.ts`
- Delete: `apps/server/src/jobs/job-queue.ts`
- Delete: `apps/server/src/jobs/job-repository.ts`
- Delete obsolete routes under `apps/server/src/http/`
- Delete superseded thumbnail manifest/page code
- Delete superseded JSON-focused server tests
- Modify: all package manifests, TypeScript configs, lint config, and root scripts
- Modify: server/web imports that still mention legacy contracts

**Interfaces:**
- `@cut-on-eight/api-contracts` is the only cross-process/browser contract
  package.
- PostgreSQL, `pg-boss`, and BlobStore are the only authoritative persistence
  mechanisms.

- [ ] **Step 1: Prove the new routes are the active web dependency**

Before deletion:

```bash
rg -n "/api/(projects|imports/select|jobs|sources|thumbnails)" cut_on_eight/apps/web/src
rg -n "@cut-on-eight/legacy-contracts" cut_on_eight/apps/web/src cut_on_eight/apps/server/src
```

Expected: no matches. Fix remaining callers through Phase 4 APIs; do not keep
compatibility adapters in the browser.

- [ ] **Step 2: Delete obsolete authority in one focused change**

Remove:

- JSON atomic/repository/layout classes;
- backend native source picker/import flow;
- custom JSON queue/recovery/event routes;
- old project/workspace/source/thumbnail routes;
- old fragment-catalog response builder;
- old shared persistence-shaped package and migrations;
- tests whose only subject was deleted JSON authority.

Keep and relocate reusable FFmpeg/FFprobe/range/domain helpers when the Phase 4
code still imports them. Keep current web editing/keyboard/preview helpers.

- [ ] **Step 3: Remove unused dependencies and scripts**

Remove `wait-on` and any dependency used only by deleted legacy code. Retain
`concurrently` only if it is used by the bounded E2E runner in Task 5.

Root `verify` must build/check/test:

- `@cut-on-eight/api-contracts`;
- server;
- web;
- AppHost TypeScript;
- lint and format.

Database/Qdrant integration commands remain explicit checkpoint scripts because
they require running resources.

- [ ] **Step 4: Audit the authority boundary**

```bash
rg -n "atomic-json|ProjectRepository|WorkspaceRepository|JobRepository|catalogue\\.json|workspace\\.json|project\\.json" cut_on_eight/apps cut_on_eight/packages
rg -n "readFile|writeFile|JSON\\.parse|JSON\\.stringify" cut_on_eight/apps/server/src
```

Expected:

- no legacy repository/state matches;
- remaining JSON operations are HTTP/job serialization or explicitly
  non-authoritative configuration;
- no code enumerates old JSON documents under `CUT_ON_EIGHT_DATA_ROOT`.

Also verify no public schema exposes:

```text
blobKey | sourcePath | sha256 | jobPayload | processingFailure | undoTokenHash
```

- [ ] **Step 5: Run verification immediately after deletion**

```bash
pnpm -C cut_on_eight verify
```

Expected: PASS. Fix import/build/test gaps before any documentation-only work.

- [ ] **Step 6: Commit the authority cutover**

```bash
git add -A cut_on_eight/apps cut_on_eight/packages cut_on_eight/package.json cut_on_eight/pnpm-lock.yaml cut_on_eight/eslint.config.js
git commit -m "refactor: remove JSON catalog authority"
```

---

### Task 4: Update Operating Documentation and Configuration

**Files:**
- Create: `.env.example`
- Rewrite: `README.md`
- Modify: root repository `README.md` only if its Cut on Eight commands changed

**Interfaces:**
- One documented local entry point: `pnpm -C cut_on_eight dev`.
- One documented verification command: `pnpm -C cut_on_eight verify`.
- Explicit environment override path for a later mini-server.

- [ ] **Step 1: Document current prerequisites**

List:

- Node.js 24+;
- pinned pnpm through Corepack;
- Aspire CLI 13.4+;
- Podman 5+ and a running Podman machine on macOS;
- FFmpeg/FFprobe on `PATH`;
- installed Chrome only for the optional phase browser checkpoint.

State clearly that the project and Codex do not install these system-wide.

- [ ] **Step 2: Document runtime and storage**

Cover:

- `ASPIRE_CONTAINER_RUNTIME=podman`;
- Aspire dashboard behavior;
- named PostgreSQL/Qdrant volumes;
- external BlobStore tree;
- immutable source/preview assets;
- PostgreSQL authority and ignored old JSON;
- Qdrant as disposable/rebuildable projection;
- browser file picker and no application restart;
- background work continues after save-and-close.

- [ ] **Step 3: Add safe environment examples**

```dotenv
CUT_ON_EIGHT_DATA_ROOT=/Users/you/cut-on-eight_data
DATABASE_URL=postgresql://user:password@host:5432/cut_on_eight
QDRANT_HTTP_URL=http://127.0.0.1:6333
QDRANT_APIKEY=
CUT_ON_EIGHT_PORT=4318
OTEL_SERVICE_NAME=cut-on-eight-api
```

Explain that Aspire injects `ConnectionStrings__catalog`, `QDRANT_HTTPURI`,
`QDRANT_APIKEY`, and standard `OTEL_*` values automatically. Direct variables
are for non-Aspire/mini-server execution. `.env` files stay ignored.

- [ ] **Step 4: Document workflows, not implementation history**

Keep concise sections for:

- Start;
- Import and background processing;
- Editor and keyboard controls;
- Fragments;
- Collections;
- Search;
- Delete/Undo;
- Backup/rebuild;
- Verify;
- Workspace layout.

Remove obsolete phase-status prose, native macOS picker claims, per-project JSON
jobs, sprite-page manifests, and warnings about editing sidecar JSON.

- [ ] **Step 5: Check documentation formatting**

```bash
pnpm -C cut_on_eight format:file README.md
git diff --check
```

- [ ] **Step 6: Commit operating documentation**

```bash
git add cut_on_eight/README.md cut_on_eight/.env.example README.md
git commit -m "docs: describe catalog runtime and operations"
```

Do not stage the root README when it required no change.

---

### Task 5: Add One Pragmatic Browser Checkpoint

**Files:**
- Create: `apps/server/src/scripts/reset-test-catalog.ts`
- Create: `apps/web/playwright.config.ts`
- Create: `apps/web/e2e/phase-04.spec.ts`
- Modify: `apps/web/package.json`
- Modify: `apps/server/package.json`
- Modify: root `package.json`
- Modify: `aspire-apphost/apphost.mts`

**Interfaces:**
- Dedicated Aspire database resource `catalog-test` / database
  `cut_on_eight_test`.
- `pnpm -C cut_on_eight test:e2e`
- One serial test, installed Chrome, no downloaded Playwright browser.

- [ ] **Step 1: Add a dedicated test database resource**

In the AppHost:

```ts
const catalog = await postgres.addDatabase('catalog', 'cut_on_eight');
const catalogTest = await postgres.addDatabase(
  'catalog-test',
  'cut_on_eight_test',
);
```

Normal API/worker reference only `catalog`. The test database exists for
explicit integration/E2E commands and is never a fallback.

- [ ] **Step 2: Add a guarded catalog reset command**

The reset script accepts only `CUT_ON_EIGHT_TEST_DATABASE_URL`, parses it, and
refuses to run unless the database name ends in `_test`. It:

- starts/migrates Kysely and `pg-boss`;
- truncates application tables in dependency order;
- clears `pg-boss` jobs/queues through its public API where supported;
- deletes only the configured `.local/e2e-data` BlobStore root.

It must never accept `ConnectionStrings__catalog` or the production default.

- [ ] **Step 3: Add Playwright using installed Chrome**

Add `@playwright/test` as a web development dependency; do not run
`playwright install`.

```ts
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  use: {
    baseURL: process.env.CUT_ON_EIGHT_E2E_BASE_URL ?? 'http://127.0.0.1:5173',
    channel: 'chrome',
    trace: 'retain-on-failure',
  },
});
```

The command checks that `CUT_ON_EIGHT_TEST_DATABASE_URL` is present, resets the
test catalog/data, starts API, worker, and Vite with that database and a data
root resolved as `resolve('.local/e2e-data')`, runs the test, then shuts the
processes down. Keep this wiring in package scripts plus a small Node launcher
if shell quoting would become opaque.

- [ ] **Step 4: Cover one meaningful user flow**

The one serial test:

1. uploads `test/fixtures/tiny.mp4`;
2. waits for ready;
3. focuses the video, plays, and creates a fragment without losing video focus;
4. selects the fragment and verifies Space activates fragment-loop mode;
5. changes timing/title and creates a lowercase tag;
6. creates a collection, adds the fragment, adds it a second time, and reorders;
7. searches the mixed-case fragment title and verifies linked source context;
8. opens the result inline, then explicitly navigates to source editing;
9. deletes and restores the fragment through Undo;
10. closes the video and verifies background/catalog state remains available.

Use roles/labels and visible state, not CSS selectors or arbitrary sleeps.

- [ ] **Step 5: Run the browser checkpoint**

With the test database connection copied from the Aspire dashboard:

```bash
test -n "$CUT_ON_EIGHT_TEST_DATABASE_URL"
pnpm -C cut_on_eight test:e2e
```

Expected: one Playwright test passes in installed Chrome. If Chrome is absent,
report that single environmental prerequisite; do not download it.

- [ ] **Step 6: Commit the phase smoke**

```bash
git add cut_on_eight/apps/server/src/scripts/reset-test-catalog.ts cut_on_eight/apps/server/package.json cut_on_eight/apps/web/playwright.config.ts cut_on_eight/apps/web/e2e/phase-04.spec.ts cut_on_eight/apps/web/package.json cut_on_eight/package.json cut_on_eight/aspire-apphost/apphost.mts cut_on_eight/pnpm-lock.yaml
git commit -m "test: add Phase 4 browser checkpoint"
```

---

### Task 6: Final Verification and Phase Close

**Files:**
- Modify as needed only to fix verified defects.
- Modify: `plans/phase-04-catalog-and-search-foundation/design.md`
- Modify: all four Phase 4 implementation plans

- [ ] **Step 1: Run the complete automated suite**

```bash
pnpm -C cut_on_eight verify
```

Expected: build, type checks, pragmatic tests, lint, formatting, and AppHost
validation pass.

- [ ] **Step 2: Run resource-backed checkpoints**

With Aspire resources and explicit test connections:

```bash
pnpm -C cut_on_eight search:smoke
pnpm -C cut_on_eight test:e2e
pnpm -C cut_on_eight backup:postgres
```

Expected: Qdrant smoke, one browser flow, and host-side backup succeed.

- [ ] **Step 3: Inspect runtime behavior in Aspire**

Run `pnpm -C cut_on_eight dev` and confirm:

- API and worker are healthy;
- PostgreSQL is required and Qdrant degradation is visible;
- API request, enqueue, and worker spans correlate;
- job duration/outcome and search metrics appear;
- logs carry trace/span IDs;
- no sensitive content or paths appear in spans/logs;
- stopping/restarting API or worker resumes durable work.

- [ ] **Step 4: Run final authority and repository checks**

```bash
rg -n "@cut-on-eight/legacy-contracts|atomic-json|catalogue\\.json|workspace\\.json|project\\.json" cut_on_eight
git diff --check
git status --short
```

Expected: no legacy authority references, no whitespace errors, and only
intentional phase-close documentation changes.

- [ ] **Step 5: Mark plans complete only from evidence**

Set the design and implementation plan statuses to `Complete`. Tick only steps
whose commands/checks actually ran. If a resource-backed check remains for the
user, leave that step open and record the exact handoff instead of claiming
completion.

- [ ] **Step 6: Commit Phase 4 completion**

```bash
git add cut_on_eight/plans/phase-04-catalog-and-search-foundation
git commit -m "docs: complete catalog and search foundation"
```

## Phase 4 Exit Criteria

- One Aspire command starts the host applications and persistent Podman
  resources.
- PostgreSQL is the sole catalog authority; legacy JSON is ignored and
  untouched.
- Managed uploads, editor state, fragments, tags, collections, order, and
  workspace survive restart.
- Durable jobs continue after save-and-close and recover from interruption.
- Fragment-first PostgreSQL search and linked source context work without
  Qdrant.
- Qdrant is payload-only, idempotent, optional, and rebuildable.
- Host-side PostgreSQL backup works.
- Public contracts cannot expose server-only fields.
- The pragmatic server, worker, Qdrant, and browser checkpoints pass, or any
  environmental handoff is explicitly recorded.
