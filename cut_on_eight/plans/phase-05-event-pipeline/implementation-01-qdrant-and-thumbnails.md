# Event Pipeline: Qdrant and Thumbnails Implementation Plan

**Status:** Implemented

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move Qdrant fragment projection and catalog thumbnail generation onto a PostgreSQL-outbox-to-JetStream pipeline, and serve reusable per-video thumbnail bundles from `thumbnails-service`.

**Architecture:** PostgreSQL remains the authoritative catalog and durable integration-event archive. A relay publishes committed immutable events to one JetStream stream; named durable pull consumers own delivery progress for the Qdrant projector and `thumbnails-service`. The service generates one reusable sprite bundle per video, then exposes it through its own read-only Fastify endpoint from a separate thumbnail root.

**Tech Stack:** PostgreSQL 18.4, Kysely, NATS Server 2.14.3 with JetStream file storage, `@nats-io/nats-core` and `@nats-io/jetstream`, Fastify 5, FFmpeg, Qdrant 1.18.3, TypeScript, Vitest, Aspire TypeScript AppHost.

**Depends on:** [Phase 4 — Collections and Search](../phase-04-catalog-and-search-foundation/implementation-03-collections-and-search.md)

## Global Constraints

- Keep all changes inside `projectslatte/cut_on_eight`; do not alter root-level agent configuration.
- PostgreSQL catalog rows remain the write-model authority. This is an integration-event archive and projection pipeline, not full event sourcing.
- Each catalog mutation writes its state change and immutable integration event in the same PostgreSQL transaction.
- `integration_events` rows are never modified or deleted by normal delivery. Publication state belongs in a separate table.
- JetStream is an operational stream with 30-day / 1 GiB bounded retention. PostgreSQL remains the source for a full replay after JetStream retention expires or is lost.
- Events contain only compact metadata and immutable IDs; never put video bytes, thumbnail bytes, local paths, checksums, secrets, or API keys into an event.
- Use versioned event types and JSON payloads. Consumers reject unknown `schemaVersion` values and acknowledge only events they successfully understand.
- All consumers are idempotent. Qdrant and thumbnail effects must tolerate an event being delivered more than once.
- Keep `pg-boss` for inspection, preview, purge, and deletion work in this slice. Remove only the `fragment.project.v1` job path after its JetStream replacement is proven.
- Do not migrate legacy JSON projects or legacy thumbnail files. The catalog runtime is the only target for this work.
- Thumbnail output is one WebP sprite bundle plus a JSON manifest per video/source/profile. Store it below `~/cut-on-eight_thumbnails` by default, never below `~/cut-on-eight_data`.
- Fragments reuse the video manifest and select their nearest five in-range samples. They have no thumbnail jobs, assets, records, or cleanup.
- `thumbnails-service` binds only to `127.0.0.1` in local development. The mini-server deployment can place a reverse proxy/CDN in front of it later.
- Run `./scripts/check.sh` and `./scripts/test.sh`; run `./scripts/integration.sh` once it starts PostgreSQL, Qdrant, and NATS.

## Event and Delivery Contract

```ts
export interface IntegrationEvent<TType extends string, TPayload> {
  readonly eventId: string;
  readonly position: bigint;
  readonly type: TType;
  readonly schemaVersion: 1;
  readonly aggregate: {
    readonly type: 'fragment' | 'video';
    readonly id: string;
    readonly revision: number;
  };
  readonly occurredAt: string;
  readonly correlationId: string | null;
  readonly causationId: string | null;
  readonly payload: TPayload;
}

export type CatalogEvent =
  | IntegrationEvent<'fragment.changed.v1', FragmentProjectionPayload>
  | IntegrationEvent<'fragment.deleted.v1', FragmentDeletedPayload>
  | IntegrationEvent<'video.thumbnails.requested.v1', ThumbnailRequestPayload>;
```

`fragment.changed.v1` contains the full current Qdrant projection payload: fragment/video IDs, aggregate revision, title, description, tags, start/end microseconds, and source title/description/tags. `fragment.deleted.v1` contains the fragment ID and revision. `video.thumbnails.requested.v1` contains `videoId`, `sourceAssetId`, and `thumbnailProfileVersion`; the worker resolves the media asset by ID from PostgreSQL.

## File Map

```text
apps/server/src/
  catalog/migrations/003-event-pipeline-and-thumbnails.ts
  catalog/{database-types,migrations/index}.ts
  events/{contracts,event-store,outbox-relay,jetstream,topology,replay-command}.ts
  jobs/{job-contracts,worker-runtime}.ts
  jobs/processors/{project-fragment,inspect-video}.ts
  search/{fragment-projection,qdrant-client,rebuild,rebuild-command}.ts
  thumbnails/{thumbnail-bundle-store,thumbnail-generator,thumbnails-service-app}.ts
  thumbnails/processors/generate-video-thumbnails.ts
  thumbnails-service.ts
  runtime.ts
  worker.ts
  config.ts
  services.ts
  api/public-mappers.ts

apps/server/test/
  event-store.test.ts
  outbox-relay.test.ts
  jetstream-topology.test.ts
  qdrant-jetstream.integration.test.ts
  thumbnail-bundle-store.test.ts
  thumbnails-service.test.ts
  thumbnail-jetstream.integration.test.ts

apps/server/package.json
apps/server/src/app.ts
apps/web/src/lib/api.ts
packages/api-contracts/src/{videos,index}.ts
packages/api-contracts/test/public-contracts.test.ts
aspire-apphost/apphost.mts
scripts/integration.sh
README.md
docs/architecture.md
plans/phase-05-event-pipeline/implementation-01-qdrant-and-thumbnails.md
```

---

### Task 1: Add the Immutable Event Archive and Thumbnail-Set Write Model

**Files:**
- Create: `apps/server/src/catalog/migrations/003-event-pipeline-and-thumbnails.ts`
- Modify: `apps/server/src/catalog/migrations/index.ts`
- Modify: `apps/server/src/catalog/database-types.ts`
- Create: `apps/server/src/events/contracts.ts`
- Create: `apps/server/src/events/event-store.ts`
- Create: `apps/server/test/event-store.test.ts`

**Consumes:** PostgreSQL catalog mutations through Kysely transactions.

**Produces:** `appendEvent(transaction, event)` and `claimPublicationBatch(database, destination, limit)`, used by the API transaction code and the outbox relay.

- [ ] **Step 1: Write the migration test around the required durable tables**

```ts
expect(await database.introspection.getTables()).toEqual(
  expect.arrayContaining([
    expect.objectContaining({ name: 'integration_events' }),
    expect.objectContaining({ name: 'event_publications' }),
    expect.objectContaining({ name: 'video_thumbnail_state' }),
    expect.objectContaining({ name: 'event_replay_runs' }),
  ]),
);
```

- [ ] **Step 2: Add migration `003-event-pipeline-and-thumbnails.ts`**

Create these tables and indexes:

```sql
create table integration_events (
  position bigint generated always as identity primary key,
  event_id uuid not null unique,
  event_type text not null check (event_type ~ '^[a-z][a-z0-9_.]+v[0-9]+$'),
  schema_version smallint not null check (schema_version = 1),
  aggregate_type text not null check (aggregate_type in ('fragment', 'video')),
  aggregate_id uuid not null,
  aggregate_revision integer not null check (aggregate_revision >= 1),
  occurred_at timestamptz not null default now(),
  correlation_id uuid,
  causation_id uuid,
  payload jsonb not null
);

create index integration_events_aggregate_order_idx
  on integration_events (aggregate_type, aggregate_id, aggregate_revision);

create table event_publications (
  event_id uuid not null references integration_events(event_id) on delete restrict,
  destination text not null check (destination = 'jetstream-primary'),
  status text not null check (status in ('pending', 'leased', 'published', 'failed')),
  attempts integer not null default 0 check (attempts >= 0),
  available_at timestamptz not null default now(),
  locked_until timestamptz,
  published_at timestamptz,
  broker_stream text,
  broker_sequence bigint,
  last_error text,
  primary key (event_id, destination)
);

create index event_publications_pending_idx
  on event_publications (destination, status, available_at, event_id);
```

Create `video_thumbnail_state` with `video_id` as primary key, `source_asset_id`, `profile_version`, opaque `storage_key`, `status` (`pending`, `generating`, `ready`, `failed`), `manifest jsonb`, `failure_code`, and timestamps. It represents exactly one current thumbnail bundle for a video/source/profile. Also create `event_replay_runs` with UUID primary key, bounded start/end positions, destination stream name, purpose, status, `published_through_position`, timestamps, and safe error text.

- [ ] **Step 3: Define exact event schemas and the append-only store**

```ts
export async function appendEvent<T extends CatalogEvent>(
  transaction: Transaction<CatalogDatabase>,
  event: Omit<T, 'eventId' | 'position' | 'occurredAt'>,
): Promise<IntegrationEvent<T['type'], T['payload']>>;

export async function claimPublicationBatch(
  database: Kysely<CatalogDatabase>,
  now: Date,
  leaseUntil: Date,
  limit: number,
): Promise<PublishedEvent[]>;
```

`appendEvent` inserts an event and its `jetstream-primary` publication record in the caller transaction. It serializes the validated discriminated-union event payload, generates the UUIDv7 event ID, and returns the identity `position`. `claimPublicationBatch` uses `FOR UPDATE SKIP LOCKED`, marks only eligible pending or expired leases as `leased`, increments attempts, and returns them in ascending event position.

- [ ] **Step 4: Prove atomic creation and safe leasing**

```ts
await database.transaction().execute(async (tx) => {
  await appendEvent(tx, changedEvent);
  throw new Error('rollback');
});
expect(await events()).toHaveLength(0);

await appendEventInCommittedTransaction(database, changedEvent);
const [first, second] = await Promise.all([
  claimPublicationBatch(database, now, leaseUntil, 1),
  claimPublicationBatch(database, now, leaseUntil, 1),
]);
expect([...first, ...second]).toHaveLength(1);
```

- [ ] **Step 5: Run focused verification**

Run: `pnpm -C cut_on_eight --filter @cut-on-eight/server test -- event-store.test.ts`

Expected: event rows roll back with the catalog transaction; only one relay lease claims a publication.

---

### Task 2: Provision JetStream and Implement the Relay Boundary

**Files:**
- Modify: `apps/server/package.json`
- Modify: `apps/server/src/config.ts`
- Create: `apps/server/src/events/jetstream.ts`
- Create: `apps/server/src/events/topology.ts`
- Create: `apps/server/src/events/outbox-relay.ts`
- Create: `apps/server/src/events/relay.ts`
- Create: `apps/server/test/jetstream-topology.test.ts`
- Create: `apps/server/test/outbox-relay.test.ts`
- Modify: `aspire-apphost/apphost.mts`
- Modify: `scripts/integration.sh`

**Consumes:** Task 1's `PublishedEvent` and `event_publications` lease records.

**Produces:** a running NATS service, `JetStreamPublisher`, stream/consumer provisioning, and an independently restartable relay process.

- [ ] **Step 1: Add the supported Node client and configuration**

Add the current `@nats-io/nats-core` and `@nats-io/jetstream` npm packages to `apps/server`. Add the required configuration:

```ts
interface ServerConfig {
  readonly natsUrl: string;
  readonly thumbnailRoot: string;
  readonly thumbnailOriginUrl: string;
  readonly thumbnailOriginPort: number;
}
```

Default to `nats://127.0.0.1:4222`, `~/cut-on-eight_thumbnails`, `http://127.0.0.1:4320`, and port `4320`. Require absolute `CUT_ON_EIGHT_THUMBNAIL_ROOT`; accept `NATS_URL`, `CUT_ON_EIGHT_THUMBNAIL_ORIGIN_URL`, and `CUT_ON_EIGHT_THUMBNAIL_ORIGIN_PORT`; validate URL protocol and port exactly as the existing API configuration does.

- [ ] **Step 2: Create an idempotent topology**

`ensurePipelineTopology(manager)` creates or validates:

```ts
export const pipelineStream = 'CUT_ON_EIGHT_EVENTS';
export const pipelineSubjects = ['cut_on_eight.>'];
export const qdrantProjectorConsumer = 'qdrant-projector-v1';
export const thumbnailGeneratorConsumer = 'thumbnail-generator-v1';
```

The stream uses file storage, limits retention, `max_age: 30 days`, `max_bytes: 1 GiB`, and duplicate-window protection. Both durable pull consumers use explicit acknowledgements. The Qdrant consumer filters `cut_on_eight.fragment.>` and has `max_ack_pending: 1`; the thumbnail consumer filters `cut_on_eight.video.thumbnails.requested.v1`, has `max_ack_pending: 1`, and uses a 120-second acknowledgement window plus retry backoff appropriate for FFmpeg.

- [ ] **Step 3: Implement the outbox relay**

```ts
export interface JetStreamPublisher {
  publish(event: PublishedEvent): Promise<{
    stream: string;
    sequence: number;
  }>;
}

export class OutboxRelay {
  async publishAvailable(): Promise<number>;
}
```

Publish the JSON event body on a subject derived from its type, for example `cut_on_eight.fragment.changed.v1`. Include `eventId`, `sourcePosition`, `aggregateId`, `aggregateRevision`, and W3C trace context in headers. Pass `eventId` as JetStream's message ID. Only mark `event_publications` as `published` after JetStream returns its publish acknowledgement; a publish failure records the bounded error text and releases the record for backoff retry.

- [ ] **Step 4: Run NATS as an Aspire-owned persistent container**

Add a generic Aspire NATS container pinned to `nats:2.14.3-alpine`, with arguments `-js`, `-sd`, `/data`, a persistent `cut-on-eight-nats-data` volume, an internal endpoint on port 4222, and persistent lifetime. Inject `NATS_URL` into the relay, Qdrant projector, and thumbnails-service processes and make all three wait for NATS after migrations. Add `dev:relay`, `dev:qdrant-projector`, and `dev:thumbnails-service` to the server package and register them as Aspire JavaScript applications.

Extend `scripts/integration.sh` to start an ephemeral NATS 2.14.3 container with a named temporary volume, export `NATS_URL`, wait for JetStream health, and clean up the container and volume in its existing trap.

- [ ] **Step 5: Test broker acknowledgement and relay retry**

```ts
await relay.publishAvailable();
expect(await publication(event.eventId)).toMatchObject({
  status: 'published',
  broker_stream: 'CUT_ON_EIGHT_EVENTS',
});

publisher.publish.mockRejectedValueOnce(new Error('broker unavailable'));
await relay.publishAvailable();
expect(await publication(event.eventId)).toMatchObject({ status: 'pending' });
```

The real NATS topology test asserts that re-running `ensurePipelineTopology` preserves the named stream and consumers rather than creating duplicates.

- [ ] **Step 6: Run focused verification**

Run: `pnpm -C cut_on_eight --filter @cut-on-eight/server test -- outbox-relay.test.ts jetstream-topology.test.ts`

Expected: broker-acknowledged events are published once operationally; relay crash/retry remains safe.

---

### Task 3: Publish Catalog Facts and Replace the Qdrant pg-boss Projector

**Files:**
- Modify: `apps/server/src/fragments/fragment-service.ts`
- Modify: `apps/server/src/videos/video-service.ts`
- Modify: `apps/server/src/jobs/processors/inspect-video.ts`
- Modify: `apps/server/src/search/fragment-projection.ts`
- Modify: `apps/server/src/search/qdrant-client.ts`
- Modify: `apps/server/src/search/rebuild.ts`
- Modify: `apps/server/src/search/rebuild-command.ts`
- Modify: `apps/server/src/jobs/job-contracts.ts`
- Modify: `apps/server/src/jobs/worker-runtime.ts`
- Modify: `apps/server/src/runtime.ts`
- Modify: `apps/server/src/worker.ts`
- Create: `apps/server/src/events/consumers/qdrant-projector.ts`
- Create: `apps/server/src/events/replay-command.ts`
- Create: `apps/server/test/qdrant-jetstream.integration.test.ts`

**Consumes:** Task 1 event store and Task 2's `qdrant-projector-v1` consumer.

**Produces:** eventually consistent Qdrant documents projected only by durable JetStream delivery; a Postgres-backed replay command for isolated rebuilds.

- [ ] **Step 1: Write the end-to-end event-to-Qdrant test**

```ts
await fragments.patch(fragmentId, revisionOnePatch);
await relay.publishAvailable();
await qdrantWorker.processOne();
expect(await qdrant.get(fragmentId)).toMatchObject({
  payload: { fragment_title: 'opening turn', fragment_revision: 2 },
});
```

Extend it with a deletion and an intentional duplicate message. The deletion removes the Qdrant point; processing the duplicate leaves the final document unchanged.

- [ ] **Step 2: Emit self-contained fragment events in every relevant transaction**

Replace `markFragmentProjectionPending(transaction, boss, fragmentId)` with `appendFragmentChangedEvent(transaction, fragmentId)` and `appendFragmentDeletedEvent(transaction, fragmentId)`. Build the changed-event payload from the transaction-visible fragment, video, tag, and timing rows after the mutation.

Emit a changed event for every visible fragment when a video title, description, or tag change alters its inherited projection fields. Emit delete events for all visible fragments when a video enters deletion. Keep the event helper in `search/fragment-projection.ts`; it is the single place that defines the Qdrant payload shape.

- [ ] **Step 3: Implement an idempotent JetStream Qdrant consumer**

```ts
export async function processQdrantEvent(
  message: JsMsg,
  event: FragmentChangedEvent | FragmentDeletedEvent,
): Promise<void>;
```

Retain `search_projection_state`, adding `last_event_id`, `last_aggregate_revision`, and `last_source_position`. In a short PostgreSQL transaction, lock the fragment state and skip an event whose aggregate revision is not newer. For a newer changed event, upsert its payload to Qdrant; for deletion, delete its point. Persist the successful revision state and acknowledge only afterward. If the process dies after the Qdrant call but before state/acknowledgement, redelivery repeats an idempotent upsert or delete.

Run one Qdrant consumer message at a time. This keeps catalog source-position order simple while aggregate revision checks protect against replay and duplicate delivery.

- [ ] **Step 4: Remove the old projection job path without disturbing other jobs**

Remove `projectFragment` from `jobNames`, `createPhase4Queues`, and `worker-runtime`. Delete the pg-boss projection processor only after the JetStream integration test passes. Keep all other pg-boss processors and their existing queues intact.

- [ ] **Step 5: Add explicit replay and rebuild commands**

Add:

```text
pnpm -C cut_on_eight pipeline:replay -- --from 1 --to 82410 --stream CUT_ON_EIGHT_REPLAY_20260726
pnpm -C cut_on_eight search:rebuild
```

`pipeline:replay` inserts a `event_replay_runs` record, publishes the immutable selected Postgres event range in ascending `position` to a newly named replay stream, and records `published_through_position`. It never publishes historic messages to `CUT_ON_EIGHT_EVENTS`.

Keep `search:rebuild` as the fast operational recovery: recreate Qdrant from a PostgreSQL catalog snapshot, rather than replaying every historic fragment edit. Document that replay is for testing new consumers, audits, and reproducible processing behaviour.

- [ ] **Step 6: Run real integration verification**

Run: `./scripts/integration.sh`

Expected: the suite starts Postgres, NATS, and Qdrant; a fragment mutation reaches Qdrant through the relay and durable consumer; deletion and duplicate delivery are safe.

---

### Task 4: Generate One Reusable Video Thumbnail Bundle from JetStream

**Files:**
- Create: `apps/server/src/thumbnails/thumbnail-bundle-store.ts`
- Create: `apps/server/src/thumbnails/thumbnail-generator.ts`
- Create: `apps/server/src/thumbnails/processors/generate-video-thumbnails.ts`
- Modify: `apps/server/src/jobs/processors/inspect-video.ts`
- Modify: `apps/server/src/catalog/database-types.ts`
- Modify: `apps/server/src/config.ts`
- Create: `apps/server/test/thumbnail-bundle-store.test.ts`
- Create: `apps/server/test/thumbnail-jetstream.integration.test.ts`

**Consumes:** `video.thumbnails.requested.v1`, the inspected source asset, FFmpeg, and the separate thumbnail root.

**Produces:** a ready `video_thumbnail_state` row and one atomically published WebP sprite bundle reusable by every fragment of that video.

- [ ] **Step 1: Write thumbnail bundle tests before the FFmpeg consumer**

```ts
await store.publish(set, generatedPages, manifest);
expect(await store.open(set.id, 'manifest.json')).toEqual(expect.objectContaining({
  contentType: 'application/json',
}));
expect(await store.open(set.id, '../source.mp4')).toBeNull();
```

Test that a failed staging run does not expose a partial set, that a ready set is immutable, and that only `manifest.json` plus declared `sprite-###.webp` files can be opened.

- [ ] **Step 2: Implement a separate, atomic thumbnail bundle store**

```ts
export interface ThumbnailBundleStore {
  createStaging(bundleKey: string): Promise<ThumbnailStagingArea>;
  publish(staging: ThumbnailStagingArea, manifest: ThumbnailManifest): Promise<void>;
  open(bundleKey: string, fileName: string): Promise<ThumbnailFile | null>;
  deleteBundle(bundleKey: string): Promise<void>;
}
```

The local layout is intentionally opaque to clients:

```text
~/cut-on-eight_thumbnails/
  staging/<random>/manifest.json
  staging/<random>/sprite-001.<content-hash>.webp
  published/<opaque-bundle>/manifest.json
  published/<opaque-bundle>/sprite-001.<content-hash>.webp
```

Generate under `staging/<random>` in the same filesystem, validate the manifest and every WebP page, `fsync` files and directory handles, then rename the completed directory to `published/<opaque-bundle>`. The public service never exposes this internal key.

- [ ] **Step 3: Request thumbnail work only after inspection completes**

In the successful inspection transaction, append:

```ts
{
  type: 'video.thumbnails.requested.v1',
  aggregate: { type: 'video', id: videoId, revision: inspectedRevision },
  payload: {
    videoId,
    sourceAssetId,
    thumbnailProfileVersion: 'overview-webp-v2',
  },
}
```

Do not emit this event when inspection failed or the video is deleting. The thumbnail consumer creates or locks the video’s `video_thumbnail_state` row, skips a matching ready source/profile, marks it `generating`, reads the source via `LocalMediaFiles.withLocalPath`, runs the existing FFmpeg sprite generator, fingerprints each generated WebP filename, publishes the bundle, switches the row’s opaque storage key and manifest, and marks the row `ready`. It removes the prior bundle after a one-hour grace period.

- [ ] **Step 4: Make processing restart-safe and bounded**

The consumer sends `working()` periodically while FFmpeg runs. On a retryable FFmpeg or disk error, it records the failure code, leaves the event unacknowledged with delayed negative acknowledgement, and removes only the staging directory. On terminal delivery exhaustion, it marks the set `failed`, records the safe failure code, and terminates the JetStream message so it cannot loop forever. A subsequent source reinspection or explicit administrative retry creates a new request event.

- [ ] **Step 5: Prove the full thumbnail pipeline**

```ts
await publishThumbnailRequestedEvent();
await relay.publishAvailable();
await thumbnailWorker.processOne();
expect(await thumbnailState(videoId)).toMatchObject({ status: 'ready' });
expect(await thumbnailStore.open(bundleKey, 'sprite-001.abc123.webp')).not.toBeNull();
```

Use the existing small FFmpeg media fixture. Assert that the data root contains source media only and the thumbnail root contains the generated manifest/pages.

- [ ] **Step 6: Run focused verification**

Run: `pnpm -C cut_on_eight --filter @cut-on-eight/server test -- thumbnail-bundle-store.test.ts thumbnail-jetstream.integration.test.ts`

Expected: thumbnails are generated once per source/profile, stored away from managed video data, safely retried after a worker interruption, and reusable by all fragment ranges.

---

### Task 5: Serve Thumbnail Bundles through `thumbnails-service` and Expose Them to the SPA

**Files:**
- Create: `apps/server/src/thumbnails/thumbnails-service-app.ts`
- Create: `apps/server/src/thumbnails-service.ts`
- Create: `apps/server/test/thumbnails-service.test.ts`
- Modify: `apps/server/src/api/public-mappers.ts`
- Modify: `apps/server/src/api/video-routes.ts`
- Modify: `packages/api-contracts/src/videos.ts`
- Modify: `packages/api-contracts/src/index.ts`
- Modify: `packages/api-contracts/test/public-contracts.test.ts`
- Modify: `apps/web/src/lib/api.ts`
- Modify: `apps/web/src/lib/thumbnail-renderer.ts`
- Modify: `aspire-apphost/apphost.mts`

**Consumes:** Task 4 ready thumbnail bundles and `video_thumbnail_state` metadata.

**Produces:** one separate Aspire thumbnails-service process and typed URLs used by the Svelte application.

- [ ] **Step 1: Extend the public video DTO with thumbnail availability**

```ts
export interface VideoThumbnailDto {
  readonly state: 'unavailable' | 'pending' | 'generating' | 'ready' | 'failed';
  readonly manifestUrl: string | null;
  readonly assetBaseUrl: string | null;
}
```

Map the video’s current thumbnail state. Only a `ready` state exposes URLs. Existing video and workspace responses remain valid when `thumbnail` is `unavailable`.

- [ ] **Step 2: Implement the read-only thumbnails-service HTTP endpoint**

Register only these routes in `createThumbnailsServiceApp`:

```text
GET /thumbnail-cdn/v1/videos/:videoId/manifest.json
GET /thumbnail-cdn/v1/videos/:videoId/:fileName
```

Validate `videoId` as UUID and `fileName` as either `manifest.json` or `sprite-` plus exactly three digits, a content hash, and `.webp`. Resolve the current video thumbnail state, then open only the declared manifest/page from its opaque bundle key; never concatenate unvalidated path fragments. Return `404` for missing/not-yet-ready thumbnails, `application/json` plus `ETag` and `Cache-Control: no-cache` for manifests, and `image/webp` plus `Cache-Control: public, max-age=31536000, immutable` for fingerprinted pages.

- [ ] **Step 3: Wire the origin as a separate Aspire process**

`thumbnails-service` is the same process that consumes thumbnail events and serves HTTP. Aspire starts it on the configured external HTTP endpoint after migrations, passes `CUT_ON_EIGHT_THUMBNAIL_ORIGIN_URL` to the API/web runtime, and gives it the same configured thumbnail root. Keep the API free of thumbnail file-serving routes in catalog mode; remove only catalog-mode reliance on the legacy `/api/projects/:id/thumbnails/*` routes.

- [ ] **Step 4: Update the SPA thumbnail client without changing editor behavior**

Make `thumbnail-renderer.ts` load the stable `manifestUrl` from `VideoThumbnailDto`, then resolve the manifest’s fingerprinted page names against `assetBaseUrl`. For every fragment, choose the nearest five samples inside its time range. If thumbnails are pending/generating/failed/unavailable, preserve the current no-thumbnail fallback; do not poll aggressively. The next normal workspace refresh obtains the ready manifest URL.

- [ ] **Step 5: Test origin isolation and browser contract**

```ts
const page = await origin.inject({
  method: 'GET',
  url: `/thumbnail-cdn/v1/videos/${videoId}/sprite-001.abc123.webp`,
});
expect(page.statusCode).toBe(200);
expect(page.headers['cache-control']).toBe('public, max-age=31536000, immutable');

expect((await origin.inject({
  method: 'GET',
  url: `/thumbnail-cdn/v1/videos/${videoId}/../../source.mp4`,
})).statusCode).toBe(404);
```

Run: `pnpm -C cut_on_eight test:web && pnpm -C cut_on_eight --filter @cut-on-eight/server test -- thumbnails-service.test.ts`

Expected: the browser receives typed thumbnails-service URLs, fragments reuse their video’s five in-range samples, and the service cannot expose source media or arbitrary thumbnail-root files.

---

### Task 6: Operational Hardening, Replay Verification, and Documentation

**Files:**
- Modify: `scripts/integration.sh`
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `apps/server/package.json`
- Modify: `package.json`
- Modify: `plans/phase-05-event-pipeline/implementation-01-qdrant-and-thumbnails.md`

**Consumes:** completed relay, consumers, thumbnails-service, and integration tests.

**Produces:** a reproducible local operation model and documented recovery paths.

- [ ] **Step 1: Add operational scripts**

```json
{
  "pipeline:relay": "tsx src/events/relay.ts",
  "pipeline:replay": "tsx src/events/replay-command.ts",
  "pipeline:status": "tsx src/events/status-command.ts",
  "thumbnails:rebuild": "tsx src/thumbnails/rebuild-command.ts"
}
```

`pipeline:status` prints the pending publication count plus JetStream durable consumer pending/acknowledgement state. `thumbnails:rebuild -- --video <uuid>` appends a new thumbnail request event; it never mutates an existing ready bundle.

- [ ] **Step 2: Document normal operation and recovery**

Document these exact rules:

```text
Catalog edit committed, but no Qdrant update yet  → inspect relay/consumer status; do not edit Qdrant manually.
JetStream stream lost                            → recreate topology, run search:rebuild, then replay only consumers that need history.
Qdrant lost                                      → run search:rebuild; PostgreSQL is authoritative.
Thumbnail bundle missing/corrupt                 → run thumbnails:rebuild for its video; the current bundle is atomically replaced.
PostgreSQL restored                              → recreate JetStream from retained integration_events before enabling dependent workers.
```

State that Postgres event retention and thumbnail-root backups are required for recovery; NATS retention is operational and bounded.

- [ ] **Step 3: Run the complete quality gate**

Run:

```text
./scripts/check.sh
./scripts/test.sh
./scripts/integration.sh
pnpm -C cut_on_eight aspire:check
```

Expected: type/lint/format checks pass; unit suites pass; real Postgres/NATS/Qdrant integration covers fragment projection and thumbnail generation; Aspire validates every declared host process and persistent service.

## Plan Self-Review

- **Spec coverage:** Tasks 1–3 implement the durable Postgres outbox, JetStream delivery, Qdrant index projection, replay, and consumer heads. Tasks 4–5 implement thumbnail generation, separate storage, and a separate serving endpoint. Task 6 documents operation and recovery.
- **Boundary check:** PostgreSQL remains authoritative and retains immutable integration events; JetStream holds active durable consumer state and bounded retained messages; Qdrant and thumbnail bundles are derived outputs.
- **Failure check:** The plan covers transaction rollback, relay crash, broker retry, duplicate delivery, stale Qdrant revisions, FFmpeg interruption, partial bundles, origin traversal, and stream-loss recovery.
- **Scope check:** It intentionally excludes embeddings, user-facing Qdrant query UX, Temporal workflows, migration of legacy JSON projects, and multi-node NATS high availability.
