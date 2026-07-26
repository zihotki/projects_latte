# Runtime and Catalog Foundation Implementation Plan

**Status:** Ready

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish the Phase 4 runtime, public API boundary, PostgreSQL catalog schema, migrations, health checks, and server observability without yet replacing the working video editor.

**Architecture:** Aspire 13.4 orchestrates host-run Svelte, Fastify, migration, and worker processes plus persistent Podman PostgreSQL and Qdrant containers. A new browser-safe contract package and a Kysely catalog boundary are added alongside the legacy JSON implementation so the next slice can cut over vertically instead of breaking the app mid-migration.

**Tech Stack:** Node.js 24, pnpm 11, TypeScript 5.9, Aspire 13.4 TypeScript AppHost, Podman 5+, PostgreSQL 18.4, Qdrant 1.18.3, Fastify 5, Kysely, `pg`, `pg-boss`, Zod 4, Cockatiel 4, OpenTelemetry.

**Depends on:** [Approved Phase 4 design](design.md)

## Global Constraints

- Keep every change under `projectslatte/cut_on_eight`; preserve both `AGENTS.md` files.
- Do not install Aspire, Podman, FFmpeg, PostgreSQL, or browser binaries system-wide. Report a missing prerequisite as a handoff.
- Use Podman only. `ASPIRE_CONTAINER_RUNTIME=podman` must be explicit in the root development script.
- Keep `~/cut-on-eight_data` as the default external data root; use `.local/` only for repository-local test and scratch data.
- Do not change current editor behavior or delete JSON code in this slice.
- Add dependencies by editing package manifests, then run one `pnpm -C cut_on_eight install`.
- Prefer feature-level Fastify tests against a real test database; add only one focused database/config test where it carries unique value.
- Public responses must be constructed through explicit mappers and validated by the new public Zod schemas.
- Never wrap PostgreSQL transactions, FFmpeg, or `pg-boss` work handlers in generic Cockatiel retries.

## File Map

```text
cut_on_eight/
  aspire.config.json
  aspire-apphost/
    apphost.mts
    package.json
    tsconfig.apphost.json
  packages/api-contracts/
    src/{common,problem-details,health,videos,fragments,workspace,index}.ts
    test/public-contracts.test.ts
  apps/server/src/
    catalog/{database,database-types,migrate,migrations/index,migrations/001-core-catalog}.ts
    jobs/{boss,job-contracts}.ts
    observability/{instrumentation,telemetry}.ts
    resilience/remote-call.ts
    api/{health-routes,public-mappers}.ts
```

The existing `packages/contracts` remains temporarily and is renamed
`@cut-on-eight/legacy-contracts`. It is deleted in Slice 4 after the web editor
has moved to application-owned models.

---

### Task 1: Scaffold Aspire and the Local Runtime

**Files:**
- Create through Aspire: `aspire.config.json`
- Create through Aspire: `aspire-apphost/apphost.mts`
- Create through Aspire: `aspire-apphost/package.json`
- Create through Aspire: `aspire-apphost/tsconfig.apphost.json`
- Modify: `.gitignore`
- Modify: `package.json`
- Modify: `pnpm-workspace.yaml`
- Modify: `apps/server/package.json`
- Modify: `apps/web/vite.config.ts`

**Interfaces:**
- Produces one root `pnpm dev` command.
- Injects `ConnectionStrings__catalog`, `QDRANT_HTTPURI`, and `QDRANT_APIKEY`.
- Injects `API_HTTP` into Vite for `/api` proxying.

- [ ] **Step 1: Run the environment preflight without installing anything**

```bash
aspire --version
ASPIRE_CONTAINER_RUNTIME=podman aspire doctor
podman version
```

Expected: Aspire 13.4.x and Podman 5+ are reported. Stop this task with a
prerequisite handoff if either is absent; do not install it.

- [ ] **Step 2: Generate the current TypeScript AppHost shape**

Run from `cut_on_eight`:

```bash
aspire init --language typescript --non-interactive
aspire add postgres
aspire add qdrant
```

Expected: the root `aspire.config.json` points to
`aspire-apphost/apphost.mts`, and generated SDK files live under
`aspire-apphost/.aspire/`.

Ensure `aspire-apphost` is included in `pnpm-workspace.yaml` so the generated
package participates in the pinned pnpm workspace.

Add these ignores:

```gitignore
aspire-apphost/.aspire/
.local/postgres-test/
```

- [ ] **Step 3: Add compact package scripts and dependencies**

Rename the legacy package to `@cut-on-eight/legacy-contracts` and update its
current server/web imports mechanically. Add `@cut-on-eight/api-contracts` as a
workspace dependency to both applications.

Add server dependencies:

```json
{
  "@fastify/otel": "^0.20.1",
  "@opentelemetry/api": "latest",
  "@opentelemetry/auto-instrumentations-node": "latest",
  "@opentelemetry/exporter-metrics-otlp-proto": "latest",
  "@opentelemetry/exporter-trace-otlp-proto": "latest",
  "@opentelemetry/sdk-metrics": "latest",
  "@opentelemetry/sdk-node": "latest",
  "@qdrant/js-client-rest": "latest",
  "cockatiel": "^4.0.0",
  "kysely": "latest",
  "pg": "latest",
  "pg-boss": "latest",
  "uuid": "latest"
}
```

Add `@types/pg` to server development dependencies. Let the lockfile record the
resolved current versions.

Replace root orchestration scripts with:

```json
{
  "dev": "ASPIRE_CONTAINER_RUNTIME=podman pnpm run aspire:start",
  "dev:legacy": "concurrently --kill-others-on-fail --names contracts,server,web \"pnpm --filter @cut-on-eight/legacy-contracts dev\" \"pnpm --filter @cut-on-eight/server dev\" \"pnpm --filter @cut-on-eight/web dev\"",
  "db:migrate": "pnpm --filter @cut-on-eight/server db:migrate",
  "aspire:check": "pnpm --dir aspire-apphost run aspire:build"
}
```

Update `predev`, `precheck`, `pretest`, and `test:contracts` so both
`@cut-on-eight/legacy-contracts` and `@cut-on-eight/api-contracts` build/test
exactly once. Replace every remaining `@cut-on-eight/contracts` package filter.

Add server scripts:

```json
{
  "db:migrate": "tsx src/catalog/migrate.ts",
  "dev": "tsx watch --import ./src/observability/instrumentation.ts src/server.ts",
  "dev:worker": "tsx watch --import ./src/observability/instrumentation.ts src/worker.ts"
}
```

Run the single dependency restore:

```bash
pnpm -C cut_on_eight install
```

Expected: one lockfile update and no package-local pnpm store.

- [ ] **Step 4: Define the AppHost topology**

Use the generated SDK and keep the tag call before the PostgreSQL volume call
because Aspire selects the PostgreSQL 18 mount layout from the tag:

```ts
import { createBuilder } from './.aspire/modules/aspire.mjs';

const builder = await createBuilder();

const postgres = await builder.addPostgres('postgres');
await postgres.withImageTag('18.4');
await postgres.withDataVolume('cut-on-eight-postgres-data');
await postgres.withPersistentLifetime();
await postgres.withContainerName('cut-on-eight-postgres');
const catalog = await postgres.addDatabase('catalog', 'cut_on_eight');

const qdrant = await builder.addQdrant('qdrant');
await qdrant.withImageTag('v1.18.3');
await qdrant.withDataVolume('cut-on-eight-qdrant-data');
await qdrant.withPersistentLifetime();

const migrations = await builder.addJavaScriptApp(
  'migrations',
  '../apps/server',
  'db:migrate',
);
await migrations.withPnpm(false);
await migrations.withReference(catalog);
await migrations.waitFor(catalog);

const api = await builder.addJavaScriptApp('api', '../apps/server', 'dev');
await api.withPnpm(false);
await api.withHttpEndpoint({ env: 'CUT_ON_EIGHT_PORT' });
await api.withExternalHttpEndpoints();
await api.withReference(catalog);
await api.withReference(qdrant);
await api.waitForCompletion(migrations);

const worker = await builder.addJavaScriptApp(
  'worker',
  '../apps/server',
  'dev:worker',
);
await worker.withPnpm(false);
await worker.withReference(catalog);
await worker.withReference(qdrant);
await worker.waitForCompletion(migrations);

const web = await builder.addViteApp('web', '../apps/web');
await web.withPnpm(false);
await web.withReference(api);
await web.waitFor(api);

await builder.build().run();
```

The initial `worker.ts` may start, log that no Phase 4 handlers are registered,
and remain alive until Slice 2.

- [ ] **Step 5: Use Aspire's Vite endpoint injection**

Keep the existing fixed-port fallback for direct development:

```ts
const backendUrl =
  process.env.API_HTTP ??
  `http://127.0.0.1:${process.env.CUT_ON_EIGHT_PORT ?? '4318'}`;

export default defineConfig({
  plugins: [svelte()],
  server: {
    host: '127.0.0.1',
    open: process.env.CI !== '1',
    port: 5173,
    strictPort: true,
    proxy: { '/api': backendUrl },
  },
});
```

- [ ] **Step 6: Validate the generated AppHost**

```bash
pnpm -C cut_on_eight aspire:check
```

Expected: TypeScript AppHost validation succeeds. Do not leave `aspire run`
running as part of automated verification.

- [ ] **Step 7: Commit the runtime scaffold**

```bash
git add cut_on_eight/aspire.config.json cut_on_eight/aspire-apphost cut_on_eight/.gitignore cut_on_eight/package.json cut_on_eight/pnpm-workspace.yaml cut_on_eight/pnpm-lock.yaml cut_on_eight/apps/server/package.json cut_on_eight/apps/web/package.json cut_on_eight/apps/web/vite.config.ts cut_on_eight/packages/contracts
git commit -m "build: add Aspire PostgreSQL and Qdrant runtime"
```

---

### Task 2: Create the Browser-Safe API Contract Package

**Files:**
- Create: `packages/api-contracts/package.json`
- Create: `packages/api-contracts/tsconfig.json`
- Create: `packages/api-contracts/src/common.ts`
- Create: `packages/api-contracts/src/problem-details.ts`
- Create: `packages/api-contracts/src/health.ts`
- Create: `packages/api-contracts/src/videos.ts`
- Create: `packages/api-contracts/src/fragments.ts`
- Create: `packages/api-contracts/src/workspace.ts`
- Create: `packages/api-contracts/src/index.ts`
- Create: `packages/api-contracts/test/public-contracts.test.ts`
- Modify: root scripts in `package.json`

**Interfaces:**
- Consumes only JSON-safe public values.
- Produces explicit request/response schemas for Slices 1 and 2.
- Does not export database rows, blob keys, file paths, job payloads, or
  processing internals.

- [ ] **Step 1: Define common scalar and Problem Details schemas**

```ts
export const entityIdSchema = z.string().uuid();
export const microsecondsSchema = z
  .number()
  .int()
  .nonnegative()
  .max(Number.MAX_SAFE_INTEGER);
export const revisionSchema = z.number().int().nonnegative();
export const timestampSchema = z.iso.datetime({ offset: true });

export const problemDetailsSchema = z.strictObject({
  type: z.string().url(),
  title: z.string().min(1),
  status: z.number().int().min(400).max(599),
  detail: z.string().min(1),
  code: z.string().regex(/^[a-z][a-z0-9_]*$/),
  instance: z.string().min(1).optional(),
  errors: z.record(z.string(), z.array(z.string().min(1))).optional(),
});
```

`ProblemDetails` is the only public error body. Do not retain the nested legacy
`{ error: ... }` shape in new routes.

- [ ] **Step 2: Define the video, fragment, preview, and workspace DTOs**

Use these public shapes:

```ts
export interface TagDto {
  id: string;
  name: string;
}

export type VideoStatus =
  | 'receiving'
  | 'queued'
  | 'processing'
  | 'ready'
  | 'failed'
  | 'deleting';

export interface VideoSummaryDto {
  id: string;
  title: string;
  description: string | null;
  originalFileName: string;
  durationUs: number | null;
  width: number | null;
  height: number | null;
  hasAudio: boolean | null;
  status: VideoStatus;
  revision: number;
  tags: TagDto[];
}

export interface FragmentPreviewDto {
  assetId: string;
  href: string;
  revision: number;
  sampleUs: number[];
  columns: number;
  rows: number;
  frameWidth: number;
  frameHeight: number;
}

export interface FragmentDto {
  id: string;
  videoId: string;
  startUs: number;
  endUs: number;
  title: string | null;
  description: string | null;
  exportSelected: boolean;
  revision: number;
  tags: TagDto[];
  previewState: 'pending' | 'ready' | 'failed';
  preview: FragmentPreviewDto | null;
}

export interface EditorStateDto {
  selectedFragmentId: string | null;
  pauseAfterCreation: boolean;
  timelineZoom: number;
  timelineOffsetUs: number;
}

export interface EditorVideoDto {
  video: VideoSummaryDto;
  source: { assetId: string; href: string } | null;
  fragments: FragmentDto[];
  playbackPositionUs: number;
  editor: EditorStateDto;
}

export interface WorkspaceDto {
  activeVideoId: string | null;
  openVideos: EditorVideoDto[];
  library: VideoSummaryDto[];
}
```

Add strict Zod schemas for every interface. The fragment schema must enforce
`endUs > startUs`, unique tag IDs, at most five preview samples, and a preview
grid that can contain every sample.

- [ ] **Step 3: Define task-oriented mutation contracts**

```ts
export const editorSaveRequestSchema = z.strictObject({
  expectedVideoRevision: revisionSchema,
  title: z.string().trim().min(1).max(240),
  description: z.string().trim().max(4_000).nullable(),
  tagIds: z.array(entityIdSchema),
  playbackPositionUs: microsecondsSchema,
  editor: editorStateSchema,
  fragments: z.array(
    z.strictObject({
      id: entityIdSchema,
      expectedRevision: revisionSchema.nullable(),
      startUs: microsecondsSchema,
      endUs: microsecondsSchema,
      title: z.string().trim().max(240).nullable(),
      description: z.string().trim().max(4_000).nullable(),
      exportSelected: z.boolean(),
      tagIds: z.array(entityIdSchema),
    }),
  ),
});

export const fragmentPatchRequestSchema = z.strictObject({
  expectedRevision: revisionSchema,
  startUs: microsecondsSchema,
  endUs: microsecondsSchema,
  title: z.string().trim().max(240).nullable(),
  description: z.string().trim().max(4_000).nullable(),
  exportSelected: z.boolean(),
  tagIds: z.array(entityIdSchema),
});

export const deletedFragmentSchema = z.strictObject({
  fragment: fragmentSchema,
  undoToken: z.string().min(32),
  undoUntil: timestampSchema,
});
```

Also define:

- `createTagRequestSchema`
- `uploadAcceptedSchema` with `{ video, workspace }`
- `closeVideoRequestSchema` with the latest playback/editor state
- `deleteFragmentRequestSchema` with `expectedRevision`
- `restoreFragmentRequestSchema` with `undoToken`
- `healthLiveSchema` and `healthReadySchema`

- [ ] **Step 4: Add compact contract tests**

Test only the high-risk public boundary:

```ts
it('rejects private persistence fields from public video responses', () => {
  expect(
    videoSummarySchema.safeParse({
      ...validVideo,
      sourceBlobKey: 'videos/private/source.mp4',
    }).success,
  ).toBe(false);
});

it('rejects unsafe or inverted fragment timings', () => {
  expect(fragmentSchema.safeParse({ ...validFragment, endUs: 1 }).success).toBe(
    false,
  );
  expect(
    fragmentSchema.safeParse({
      ...validFragment,
      startUs: Number.MAX_SAFE_INTEGER + 1,
    }).success,
  ).toBe(false);
});
```

- [ ] **Step 5: Build and test both contract packages**

```bash
pnpm -C cut_on_eight test:contracts
pnpm -C cut_on_eight --filter @cut-on-eight/api-contracts build
```

Expected: both transitional legacy tests and the new public-boundary tests pass.

- [ ] **Step 6: Commit the public API boundary**

```bash
git add cut_on_eight/packages/api-contracts cut_on_eight/package.json cut_on_eight/apps/server/package.json cut_on_eight/apps/web/package.json cut_on_eight/pnpm-lock.yaml
git commit -m "feat: define browser-safe catalog contracts"
```

---

### Task 3: Add Kysely, Core Migrations, and Catalog Configuration

**Files:**
- Create: `apps/server/src/catalog/database-types.ts`
- Create: `apps/server/src/catalog/database.ts`
- Create: `apps/server/src/catalog/migrations/001-core-catalog.ts`
- Create: `apps/server/src/catalog/migrations/index.ts`
- Create: `apps/server/src/catalog/migrate.ts`
- Create: `apps/server/src/jobs/boss.ts`
- Create: `apps/server/src/jobs/job-contracts.ts`
- Create: `apps/server/test/catalog-database.test.ts`
- Modify: `apps/server/src/config.ts`
- Modify: `apps/server/test/config.test.ts`

**Interfaces:**
- `createCatalogDatabase(config): Kysely<CatalogDatabase>`
- `migrateCatalog(db): Promise<void>`
- `closeCatalogDatabase(db): Promise<void>`
- Reads `ConnectionStrings__catalog`, falling back to `DATABASE_URL`.

- [ ] **Step 1: Extend server configuration**

```ts
export interface ServerConfig {
  dataRoot: string;
  databaseUrl: string;
  qdrantHttpUrl: string | null;
  qdrantApiKey: string | null;
  host: '127.0.0.1';
  port: number;
}
```

Resolve values in this order:

```ts
const databaseUrl =
  environment.ConnectionStrings__catalog ?? environment.DATABASE_URL;
const qdrantHttpUrl =
  environment.QDRANT_HTTPURI ?? environment.QDRANT_HTTP_URL ?? null;
const qdrantApiKey = environment.QDRANT_APIKEY ?? null;
```

Throw a concise startup error when no database URL is configured. Validate URL
syntax without logging credentials.

- [ ] **Step 2: Define server-only row types**

Use Kysely `Generated`, `ColumnType`, and `Selectable` types. Keep PostgreSQL
`bigint` values represented as strings in persistence rows and convert them
through:

```ts
export function safeMicroseconds(value: string): number {
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed < 0) {
    throw new Error('Catalog contains an invalid microsecond value');
  }
  return parsed;
}
```

The `CatalogDatabase` interface must include:

- `assets`
- `videos`
- `fragments`
- `tags`
- `video_tags`
- `fragment_tags`
- `fragment_previews`
- `workspace_state`
- `workspace_videos`
- `editor_state`
- `worker_heartbeats`

Do not include any `pg-boss` table in Kysely types.

- [ ] **Step 3: Implement the first code migration**

Create the records and checks from the approved design. Key constraints:

```sql
videos.status IN
  ('receiving', 'queued', 'processing', 'ready', 'failed', 'deleting')

fragments.start_us >= 0
fragments.end_us > fragments.start_us
fragments.revision >= 1

tags.name = lower(trim(tags.name))
UNIQUE(tags.name)

UNIQUE(workspace_videos.position)
editor_state.timeline_zoom >= 1
fragment_previews.columns * fragment_previews.rows >=
  cardinality(fragment_previews.sample_us)
fragment_previews.status IN ('pending', 'ready', 'failed')
```

Use `ON DELETE CASCADE` from fragments to videos and join records, but do not
add a database foreign key from `assets.owner_id`; asset ownership spans
multiple entity kinds and is enforced by catalog services.

Register migrations explicitly so development `.ts` and built `.js` execution
do not depend on filesystem-extension discovery:

```ts
export const catalogMigrations: MigrationProvider = {
  async getMigrations() {
    return { '001-core-catalog': coreCatalogMigration };
  },
};
```

- [ ] **Step 4: Initialize Kysely and pg-boss schemas in one migration command**

```ts
const db = createCatalogDatabase(getServerConfig());
const migrator = new Migrator({ db, provider: catalogMigrations });
const { error, results } = await migrator.migrateToLatest();
if (error !== undefined) throw error;

const boss = createBoss(getServerConfig());
await boss.start();
await createPhase4Queues(boss);
await boss.stop({ graceful: true });
await db.destroy();
```

`createPhase4Queues` declares stable names and queue policies but no workers:

```ts
export const jobNames = {
  inspectVideo: 'video.inspect.v1',
  generateFragmentPreview: 'fragment.preview.v1',
  projectFragment: 'fragment.project.v1',
  purgeFragment: 'fragment.purge.v1',
  deleteVideo: 'video.delete.v1',
  deleteAsset: 'asset.delete.v1',
} as const;
```

- [ ] **Step 5: Add one real-database migration test**

The test reads `CUT_ON_EIGHT_TEST_DATABASE_URL`, migrates a clean test database,
inserts a valid video/fragment, and proves invalid timing plus duplicate
lowercase tags are rejected. Run server database tests serially.

```bash
test -n "$CUT_ON_EIGHT_TEST_DATABASE_URL"
pnpm -C cut_on_eight test:server -- catalog-database.test.ts
```

Expected: PASS against PostgreSQL 18.4. If no test URL is configured, skip with
one explicit message rather than silently substituting JSON or an in-memory
database.

- [ ] **Step 6: Commit the catalog foundation**

```bash
git add cut_on_eight/apps/server/src/catalog cut_on_eight/apps/server/src/config.ts cut_on_eight/apps/server/test/catalog-database.test.ts cut_on_eight/apps/server/test/config.test.ts
git commit -m "feat: add PostgreSQL catalog migrations"
```

---

### Task 4: Add OpenTelemetry and the Remote-Call Resilience Boundary

**Files:**
- Create: `apps/server/src/observability/instrumentation.ts`
- Create: `apps/server/src/observability/telemetry.ts`
- Create: `apps/server/src/resilience/remote-call.ts`
- Create: `apps/server/test/remote-call.test.ts`
- Modify: `apps/server/src/server.ts`
- Create: `apps/server/src/worker.ts`

**Interfaces:**
- `telemetry.tracer`, `telemetry.meter`, and `shutdownTelemetry()`
- `ResilientCall.execute(operation)`
- `createRemoteCallPolicy(options)`

- [ ] **Step 1: Bootstrap telemetry before application imports**

`instrumentation.ts` starts one Node SDK at module load:

```ts
const fastifyInstrumentation = new FastifyOtelInstrumentation({
  registerOnInitialization: true,
  instrumentHooks: false,
});

const sdk = new NodeSDK({
  traceExporter: new OTLPTraceExporter(),
  metricReader: new PeriodicExportingMetricReader({
    exporter: new OTLPMetricExporter(),
  }),
  instrumentations: [
    getNodeAutoInstrumentations({
      '@opentelemetry/instrumentation-fastify': { enabled: false },
    }),
    fastifyInstrumentation,
  ],
});

sdk.start();
```

Read standard `OTEL_*` variables supplied by Aspire. Do not hardcode a dashboard
endpoint or include titles, tags, descriptions, SQL, or paths as attributes.

`telemetry.ts` exports named instruments:

```ts
export const tracer = trace.getTracer('cut-on-eight');
export const meter = metrics.getMeter('cut-on-eight');
export const jobDuration = meter.createHistogram('cut_on_eight.job.duration');
export const searchDuration = meter.createHistogram(
  'cut_on_eight.search.duration',
);
export const resilienceEvents = meter.createCounter(
  'cut_on_eight.resilience.events',
);
```

- [ ] **Step 2: Flush telemetry during API and worker shutdown**

API and worker signal handlers stop accepting work, close their resources, then
call `sdk.shutdown()`. Set `process.exitCode`; do not call `process.exit()`.

- [ ] **Step 3: Implement the Cockatiel boundary**

```ts
export interface ResilientCall {
  execute<T>(
    operation: (signal: AbortSignal) => Promise<T>,
    signal?: AbortSignal,
  ): Promise<T>;
}

export class RemoteCallError extends Error {
  constructor(
    readonly status: number | null,
    message: string,
  ) {
    super(message);
  }
}
```

Build one policy per remote client using:

```ts
const handled = handleWhen(
  (error) =>
    error instanceof RemoteCallError &&
    (error.status === null ||
      [429, 502, 503, 504].includes(error.status)),
);
const policy = wrap(
  retry(handled, {
    maxAttempts: 3,
    backoff: new ExponentialBackoff({
      initialDelay: 100,
      maxDelay: 1_000,
    }),
  }),
  circuitBreaker(handled, {
    breaker: new ConsecutiveBreaker(5),
    halfOpenAfter: 15_000,
  }),
  timeout(3_000, TimeoutStrategy.Aggressive),
  bulkhead(8, 32),
);
```

Expose policy events through low-cardinality OTel counters. Do not log request
payloads.

- [ ] **Step 4: Test only failure classification**

Use fake operations to prove:

- a transient remote failure is retried and then succeeds;
- a `400`-class remote failure is not retried;
- an abort signal stops the call.

Use minimal backoff/timeout options in tests; do not assert Cockatiel internals.

```bash
pnpm -C cut_on_eight test:server -- remote-call.test.ts
```

Expected: three behavior tests pass quickly.

- [ ] **Step 5: Commit observability and resilience**

```bash
git add cut_on_eight/apps/server/src/observability cut_on_eight/apps/server/src/resilience cut_on_eight/apps/server/src/server.ts cut_on_eight/apps/server/src/worker.ts cut_on_eight/apps/server/test/remote-call.test.ts cut_on_eight/apps/server/package.json cut_on_eight/pnpm-lock.yaml
git commit -m "feat: add server telemetry and resilience"
```

---

### Task 5: Add Liveness, Readiness, and the Slice Checkpoint

**Files:**
- Create: `apps/server/src/api/health-routes.ts`
- Create: `apps/server/src/api/public-mappers.ts`
- Create: `apps/server/test/health-integration.test.ts`
- Modify: `apps/server/src/app.ts`
- Modify: `apps/server/src/services.ts`
- Modify: `packages/api-contracts/src/health.ts`

**Interfaces:**
- `GET /api/health/live`
- `GET /api/health/ready`
- Legacy `GET /api/health` remains as an alias until Slice 4.

- [ ] **Step 1: Add explicit public mappers**

Begin the mapper boundary with health and dependency state:

```ts
export function toReadyDto(input: {
  postgres: 'ready' | 'unavailable';
  qdrant: 'ready' | 'degraded' | 'not-configured';
  worker: 'ready' | 'unavailable';
}): HealthReadyDto {
  return healthReadySchema.parse({
    status: input.postgres === 'ready' ? 'ready' : 'unavailable',
    dependencies: input,
  });
}
```

No route may send a service object, database row, or caught error directly.

- [ ] **Step 2: Implement health semantics**

- Liveness returns `200` whenever the Fastify process can serve.
- Readiness queries PostgreSQL with `select 1`.
- PostgreSQL failure returns `503`.
- Qdrant absence/failure sets `degraded` but does not change the HTTP status.
- Worker readiness is reported from a short-lived database heartbeat written
  by `worker.ts`; it does not block API readiness in this slice.

- [ ] **Step 3: Add a feature-level Fastify health test**

Use `Fastify.inject()` with the real test database and an injected Qdrant probe:

```ts
const ready = await app.inject({ method: 'GET', url: '/api/health/ready' });
expect(ready.statusCode).toBe(200);
expect(healthReadySchema.parse(ready.json()).dependencies.postgres).toBe(
  'ready',
);
```

Also stop the test database pool and verify the route returns a validated `503`
Problem Details response. Do not mock Kysely.

- [ ] **Step 4: Run the complete Slice 1 checkpoint**

```bash
pnpm -C cut_on_eight aspire:check
pnpm -C cut_on_eight verify
```

Then perform one bounded manual runtime check:

```bash
ASPIRE_CONTAINER_RUNTIME=podman pnpm -C cut_on_eight run aspire:start
```

Expected in the Aspire dashboard:

- persistent PostgreSQL 18.4 and Qdrant 1.18.3 resources;
- migrations complete successfully;
- API, worker, and web become running;
- `/api/health/ready` reports PostgreSQL ready;
- API and worker traces/logs appear.

Stop the AppHost after inspection. Existing editor routes may still use JSON in
this transitional slice.

- [ ] **Step 5: Commit the Slice 1 checkpoint**

```bash
git add cut_on_eight/apps/server/src/api cut_on_eight/apps/server/src/app.ts cut_on_eight/apps/server/src/services.ts cut_on_eight/apps/server/test/health-integration.test.ts cut_on_eight/packages/api-contracts/src/health.ts
git commit -m "feat: expose catalog dependency health"
```

## Slice 1 Exit Criteria

- `pnpm dev` uses a TypeScript AppHost and Podman explicitly.
- PostgreSQL and Qdrant use named persistent volumes.
- The catalog migration and `pg-boss` schema initialize before API/worker.
- The new public contract package contains no persistence or filesystem shape.
- PostgreSQL readiness is real; Qdrant is optional/degraded.
- API and worker emit correlated local telemetry.
- The old editor remains usable, ready for the Slice 2 vertical cutover.

## References

- [Aspire TypeScript AppHost structure](https://aspire.dev/app-host/typescript-apphost/)
- [Aspire PostgreSQL hosting integration](https://aspire.dev/integrations/databases/postgres/postgres-host/)
- [Aspire TypeScript `waitForCompletion`](https://aspire.dev/reference/api/typescript/aspire.hosting/waitforcompletion/)
- [Aspire JavaScript deployment and Vite proxying](https://aspire.dev/deployment/javascript-apps/)
- [pg-boss Kysely transaction adapter](https://github.com/timgit/pg-boss#orm-transaction-adapters)
- [OpenTelemetry Node.js setup](https://opentelemetry.io/docs/languages/js/getting-started/nodejs/)
- [Fastify OpenTelemetry instrumentation](https://www.npmjs.com/package/@fastify/otel)
