# Video and Fragment Vertical Slice Implementation Plan

**Status:** Ready

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move import, library, workspace, editor state, fragments, tags, previews, playback, and deletion to PostgreSQL plus the managed filesystem while preserving the established editor UX.

**Architecture:** New Phase 4 routes use focused video, workspace, fragment, asset, and job modules composed in `runtime.ts`. PostgreSQL transactions own catalog state and enqueue `pg-boss` work atomically through its Kysely adapter. The Svelte application keeps its proven seconds-based editor model internally and maps it to public microsecond DTOs at the API boundary.

**Tech Stack:** Slice 1 stack plus `@fastify/multipart`, local filesystem streams, SHA-256, UUIDv7, FFprobe, FFmpeg, Svelte 5.

**Depends on:** [Slice 1 — Runtime and Catalog Foundation](implementation-01-runtime-and-catalog-foundation.md)

## Global Constraints

- Keep changes inside `projectslatte/cut_on_eight`; preserve both `AGENTS.md` files.
- PostgreSQL is authoritative for every new route. Do not dual-write to JSON and do not fall back to JSON after a database failure.
- Leave old JSON files untouched. Obsolete code is removed only in Slice 4.
- Copy uploads into the managed data root before enabling fragment creation.
- Save catalog changes and enqueue background work in one database transaction,
  then return without waiting for FFprobe, FFmpeg, or Qdrant.
- Keep the current focus state machine: creating a fragment retains video focus;
  clicking a fragment only selects it; Space starts/stops the selected fragment
  loop; video focus makes Space and seek keys control the full video.
- Preserve keyboard boundary editing, fast seek, multi-video tabs, explicit
  save-and-close, inline fragment playback, confirmation for video deletion,
  and no confirmation for fragment deletion.
- Keep all physical paths, blob keys, checksums, undo-token hashes, job payloads,
  and processing failures server-only.
- Use feature-level Fastify tests with real PostgreSQL and real filesystem I/O.
  Keep pure unit tests only for timing overlap and key validation.

## File Map

```text
apps/server/src/
  runtime.ts
  api/
    asset-routes.ts
    fragment-routes.ts
    tag-routes.ts
    video-routes.ts
    workspace-routes.ts
  blobs/
    blob-key.ts
    blob-store.ts
    local-blob-store.ts
  domain/
    fragment-timing.ts
    models.ts
  videos/
    video-repository.ts
    video-service.ts
  fragments/
    fragment-repository.ts
    fragment-service.ts
  workspace/
    workspace-repository.ts
    workspace-service.ts
  jobs/
    job-envelope.ts
    worker-runtime.ts
    processors/{inspect-video,generate-preview,purge-fragment,delete-video}.ts
  media/fragment-preview-generator.ts

apps/web/src/
  domain/{editor-model,editor-mappers}.ts
  components/ImportVideoButton.svelte
  app/{workspace-session,fragment-library,background-processing}.svelte.ts
  lib/api.ts
```

---

### Task 1: Implement the Managed BlobStore

**Files:**
- Create: `apps/server/src/blobs/blob-key.ts`
- Create: `apps/server/src/blobs/blob-store.ts`
- Create: `apps/server/src/blobs/local-blob-store.ts`
- Create: `apps/server/test/blob-store.test.ts`
- Modify: `apps/server/package.json`

**Interfaces:**
- `BlobKey` is a validated POSIX-relative logical key.
- `BlobStore` supports staged write, atomic publish, range read, stat, and delete.
- `LocalMediaFiles` gives server media adapters temporary local-path access
  without adding paths to domain or public models.

- [ ] **Step 1: Add the upload dependency in the Slice 2 package update**

Add `@fastify/multipart` to the server and `uuid` to the web package. Run one
restore:

```bash
pnpm -C cut_on_eight install
```

- [ ] **Step 2: Define narrow storage interfaces**

```ts
declare const blobKeyBrand: unique symbol;
export type BlobKey = string & { readonly [blobKeyBrand]: true };

export interface StagedBlob {
  readonly key: BlobKey;
  readonly size: number;
  readonly sha256: string;
}

export interface BlobRange {
  readonly stream: NodeJS.ReadableStream;
  readonly size: number;
  readonly start: number;
  readonly endInclusive: number;
}

export interface BlobStore {
  writeStaged(
    source: AsyncIterable<Uint8Array>,
    signal?: AbortSignal,
  ): Promise<StagedBlob>;
  publish(staged: StagedBlob, destination: BlobKey): Promise<void>;
  openRange(
    key: BlobKey,
    range?: { start: number; endInclusive: number },
  ): Promise<BlobRange>;
  stat(key: BlobKey): Promise<{ size: number }>;
  delete(key: BlobKey): Promise<void>;
}

export interface LocalMediaFiles {
  withLocalPath<T>(
    key: BlobKey,
    operation: (path: string) => Promise<T>,
  ): Promise<T>;
}
```

`blobKey(value)` rejects absolute paths, backslashes, empty segments, `.`, `..`,
NUL, and keys outside the approved roots `incoming/` and `videos/`.

- [ ] **Step 3: Implement local staged and immutable writes**

- Write to `incoming/<uuidv7>.part` with `wx`.
- Compute SHA-256 and byte count while streaming.
- `fsync` and close before returning.
- Publish by creating the destination directory and renaming on the same
  filesystem.
- Refuse to overwrite a published destination.
- Delete is idempotent for a missing key.
- Range reads validate `0 <= start <= end < size`.

Use storage keys:

```ts
export const sourceBlobKey = (videoId: string, originalName: string) =>
  blobKey(`videos/${videoId}/source/${safeFileName(originalName)}`);

export const previewBlobKey = (
  videoId: string,
  fragmentId: string,
  revision: number,
) =>
  blobKey(
    `videos/${videoId}/fragments/${fragmentId}/preview-r${revision}.webp`,
  );
```

Pass `videoId` explicitly to `previewBlobKey`; never derive it from a database
lookup inside the key helper.

- [ ] **Step 4: Verify real filesystem behavior**

Use a test root under `cut_on_eight/.local/test-data/blob-store`. Cover one
stream/publish/range round trip, traversal rejection, overwrite rejection, and
idempotent delete.

```bash
pnpm -C cut_on_eight test:server -- blob-store.test.ts
```

Expected: PASS without touching `~/cut-on-eight_data`.

- [ ] **Step 5: Commit BlobStore**

```bash
git add cut_on_eight/apps/server/src/blobs cut_on_eight/apps/server/test/blob-store.test.ts cut_on_eight/apps/server/package.json cut_on_eight/apps/web/package.json cut_on_eight/pnpm-lock.yaml
git commit -m "feat: add managed local blob storage"
```

---

### Task 2: Implement Upload, Video Catalog, Assets, and Workspace

**Files:**
- Create: `apps/server/src/runtime.ts`
- Create: `apps/server/src/videos/video-repository.ts`
- Create: `apps/server/src/videos/video-service.ts`
- Create: `apps/server/src/workspace/workspace-repository.ts`
- Create: `apps/server/src/workspace/workspace-service.ts`
- Create: `apps/server/src/api/video-routes.ts`
- Create: `apps/server/src/api/workspace-routes.ts`
- Create: `apps/server/src/api/asset-routes.ts`
- Create: `apps/server/test/video-workspace-api.test.ts`
- Modify: `apps/server/src/app.ts`
- Modify: `apps/server/src/server.ts`

**Interfaces:**
- `POST /api/videos` accepts one multipart `source` file.
- `GET /api/videos`
- `GET /api/videos/:videoId`
- `POST /api/videos/:videoId/open`
- `POST /api/videos/:videoId/activate`
- `POST /api/videos/:videoId/close`
- `GET /api/workspace`
- `GET /api/assets/:assetId` with HTTP range support.

- [ ] **Step 1: Replace the giant service interface for new routes**

Compose focused services once:

```ts
export interface ApiRuntime {
  readonly db: Kysely<CatalogDatabase>;
  readonly boss: PgBoss;
  readonly blobs: BlobStore;
  readonly videos: VideoService;
  readonly fragments: FragmentService;
  readonly workspace: WorkspaceService;
  close(): Promise<void>;
}

export async function createRuntime(
  config: ServerConfig,
): Promise<ApiRuntime>;
```

`createApp({ runtime })` registers Phase 4 routes from this runtime. Keep legacy
`AppServices` only for legacy routes; do not add Phase 4 methods to it.

- [ ] **Step 2: Implement explicit repository records and DTO mappers**

Repository methods return server domain records, never public DTOs:

```ts
export interface VideoRecord {
  readonly id: string;
  readonly title: string;
  readonly description: string | null;
  readonly originalFileName: string;
  readonly sourceAssetId: string | null;
  readonly durationUs: number | null;
  readonly status: VideoStatus;
  readonly revision: number;
  readonly failure: ProcessingFailure | null;
}
```

Map with an allowlist:

```ts
export function toVideoSummaryDto(
  video: VideoRecord,
  tags: readonly TagRecord[],
): VideoSummaryDto {
  return videoSummarySchema.parse({
    id: video.id,
    title: video.title,
    description: video.description,
    originalFileName: video.originalFileName,
    durationUs: video.durationUs,
    width: video.width,
    height: video.height,
    hasAudio: video.hasAudio,
    status: video.status,
    revision: video.revision,
    tags: tags.map(toTagDto),
  });
}
```

No object spread from a row or domain record is permitted in a public mapper.

- [ ] **Step 3: Implement staged browser upload**

The service sequence is:

1. Parse one multipart file and validate an `.mp4` filename plus a bounded
   content-length limit configured as `CUT_ON_EIGHT_MAX_UPLOAD_BYTES`
   (default 20 GiB).
2. Generate UUIDv7 video and asset IDs.
3. Insert the video as `receiving`.
4. Stream to `BlobStore.writeStaged()`.
5. Publish to `videos/<video-id>/source/<safe-original-name>`.
6. In one Kysely transaction, insert the source asset, set video `queued`,
   open/activate it in the workspace, and call:

```ts
await boss.send(
  jobNames.inspectVideo,
  envelope({ videoId, expectedRevision: 1 }),
  {
    db: fromKysely(transaction),
    retryLimit: 3,
    singletonKey: `${videoId}:1`,
  },
);
```

7. Return `202` with `uploadAcceptedSchema.parse({ video, workspace })`.

If streaming fails, delete the staged blob and mark the record `failed` with a
stable private failure code. If publishing succeeds but the transaction fails,
leave a `receiving` record for Slice 4 recovery; never expose an anonymous
video.

- [ ] **Step 4: Implement PostgreSQL-backed workspace operations**

`WorkspaceService.snapshot()` loads:

- library videos excluding `deleting`;
- open videos ordered by `workspace_videos.position`;
- active video from the singleton `workspace_state`;
- fragments, preview metadata, tags, playback, and editor state for open videos.

Open is idempotent and appends to the visible order. Activate requires an open
video. Close persists playback/editor state, removes the open row, and selects
the last remaining open video. All three return a fresh `WorkspaceDto`.

- [ ] **Step 5: Serve managed assets with range semantics**

Resolve the asset ID in PostgreSQL, allow only `source-video` and
`fragment-preview` kinds, then call `BlobStore.openRange`. Support:

- `200` for full content;
- `206` plus `Content-Range`, `Content-Length`, and `Accept-Ranges` for one
  valid byte range;
- `416` for an unsatisfiable or multi-range request;
- immutable cache headers for revisioned previews;
- no physical path or blob key in errors.

- [ ] **Step 6: Add one feature-level video/workspace test**

With a real database and local test data root:

- upload a small byte stream as multipart;
- assert the source was published before the response advertises it;
- assert the database record is queued and an inspection job exists;
- open/activate/close two records and verify stable order;
- range-read the managed source through `/api/assets/:id`;
- parse every response with public schemas.

The uploaded bytes do not need to be a valid MP4 here; inspection belongs to the
worker integration test.

```bash
test -n "$CUT_ON_EIGHT_TEST_DATABASE_URL"
pnpm -C cut_on_eight test:server -- video-workspace-api.test.ts
```

- [ ] **Step 7: Commit the video/workspace slice**

```bash
git add cut_on_eight/apps/server/src/runtime.ts cut_on_eight/apps/server/src/videos cut_on_eight/apps/server/src/workspace cut_on_eight/apps/server/src/api cut_on_eight/apps/server/src/app.ts cut_on_eight/apps/server/src/server.ts cut_on_eight/apps/server/test/video-workspace-api.test.ts
git commit -m "feat: persist uploads and workspace in PostgreSQL"
```

---

### Task 3: Implement Fragment Editing, Tags, Revisions, and Undo

**Files:**
- Create: `apps/server/src/domain/models.ts`
- Create: `apps/server/src/domain/fragment-timing.ts`
- Create: `apps/server/src/fragments/fragment-repository.ts`
- Create: `apps/server/src/fragments/fragment-service.ts`
- Create: `apps/server/src/api/fragment-routes.ts`
- Create: `apps/server/src/api/tag-routes.ts`
- Create: `apps/server/test/editor-fragment-api.test.ts`
- Create: `apps/server/test/fragment-timing.test.ts`
- Modify: `apps/server/src/api/public-mappers.ts`

**Interfaces:**
- `PATCH /api/videos/:videoId/editor`
- `GET /api/fragments`
- `PATCH /api/fragments/:fragmentId`
- `DELETE /api/fragments/:fragmentId`
- `POST /api/fragments/:fragmentId/restore`
- `GET /api/tags`
- `POST /api/tags`

- [ ] **Step 1: Express timing invariants once in the domain**

```ts
export interface FragmentTiming {
  readonly id: string;
  readonly startUs: number;
  readonly endUs: number;
}

export function validateFragmentSet(
  fragments: readonly FragmentTiming[],
  durationUs: number | null,
): void;
```

Validation must:

- require safe non-negative integers and `startUs < endUs`;
- require `endUs <= durationUs` when duration is known;
- reject duplicate IDs;
- process end events before start events at the same timestamp;
- reject a third simultaneously active fragment.

Keep this as the only new pure domain test:

```ts
expect(() =>
  validateFragmentSet([
    fragment('a', 0, 3_000_000),
    fragment('b', 1_000_000, 4_000_000),
    fragment('c', 2_000_000, 5_000_000),
  ], 6_000_000),
).toThrow(DomainConflict);
```

- [ ] **Step 2: Implement canonical tags**

Tag creation trims and lowercases the name in both request parsing and service
logic. Insert with `ON CONFLICT (name) DO UPDATE SET name = excluded.name`
and return the existing stable ID. Replace tag assignments transactionally;
deduplicate IDs and reject unknown IDs with `422`.

- [ ] **Step 3: Implement aggregate editor save**

`PATCH /api/videos/:videoId/editor` accepts `EditorSaveRequest`.

Inside one transaction:

1. Lock the video row.
2. Compare `expectedVideoRevision`; throw `409 stale_revision` on mismatch.
3. Load existing non-deleted fragments and merge submitted mutations.
4. A submitted fragment with `expectedRevision: null` is new and must not
   already exist.
5. Existing submitted fragments must match their expected revisions.
6. Validate the complete timing set.
7. Update video metadata/editor/workspace state.
8. Insert/update fragments and tag joins.
9. Increment changed aggregate revisions.
10. Mark preview state pending and enqueue preview jobs only for
    new/timing-changed fragments using
    `fromKysely(transaction)`.
11. Return a fresh `EditorVideoDto`.

Title, description, export-selection, and tag-only edits do not enqueue preview
work. They will enqueue search projection work after Slice 3 adds the projector.

- [ ] **Step 4: Implement focused fragment mutation**

`PATCH /api/fragments/:fragmentId` uses the same timing validator and revision
rules but returns one `FragmentDto`. This serves the standalone Fragments view
without requiring an open editor.

- [ ] **Step 5: Implement immediate delete with durable eight-second Undo**

On delete:

- lock and revision-check the fragment;
- generate 32 random bytes and store only their SHA-256 hash;
- set `deleted_at` and `purge_after = now() + interval '8 seconds'`;
- hide the fragment from workspace, library, and fragment queries;
- enqueue `fragment.purge.v1` with `startAfter: 8` in the same transaction;
- return `{ fragment, undoToken, undoUntil }`.

Restore requires the matching token before `purge_after`, clears deletion
fields, increments revision, and leaves the same fragment ID/tags intact.
The purge worker re-checks the deadline and deletion marker before hard delete.

- [ ] **Step 6: Map domain failures to stable Problem Details**

Use:

| Failure | Status | Code |
| --- | ---: | --- |
| malformed request | 422 | `validation_failed` |
| missing video/fragment/tag | 404 | `catalog_item_not_found` |
| stale revision | 409 | `stale_revision` |
| invalid timing/third overlap | 409 | `fragment_timing_conflict` |
| expired/invalid Undo token | 409 | `fragment_restore_expired` |
| database unavailable | 503 | `catalog_unavailable` |

- [ ] **Step 7: Add one feature-level editor/fragment test**

Use Fastify inject plus real PostgreSQL to cover in one flow:

- create two fragments through editor save;
- reject a third overlap;
- update title/timing/tags through the fragment route;
- reject a stale revision;
- delete without confirmation;
- confirm it disappears;
- restore with the Undo token;
- confirm the same ID and tags return.

```bash
test -n "$CUT_ON_EIGHT_TEST_DATABASE_URL"
pnpm -C cut_on_eight test:server -- editor-fragment-api.test.ts fragment-timing.test.ts
```

- [ ] **Step 8: Commit fragment catalog behavior**

```bash
git add cut_on_eight/apps/server/src/domain cut_on_eight/apps/server/src/fragments cut_on_eight/apps/server/src/api/fragment-routes.ts cut_on_eight/apps/server/src/api/tag-routes.ts cut_on_eight/apps/server/src/api/public-mappers.ts cut_on_eight/apps/server/test/editor-fragment-api.test.ts cut_on_eight/apps/server/test/fragment-timing.test.ts
git commit -m "feat: persist fragment editing and undo"
```

---

### Task 4: Run Durable Inspection and Preview Work

**Files:**
- Create: `apps/server/src/jobs/job-envelope.ts`
- Create: `apps/server/src/jobs/worker-runtime.ts`
- Create: `apps/server/src/jobs/processors/inspect-video.ts`
- Create: `apps/server/src/jobs/processors/generate-preview.ts`
- Create: `apps/server/src/jobs/processors/purge-fragment.ts`
- Create: `apps/server/src/jobs/processors/delete-video.ts`
- Create: `apps/server/src/media/fragment-preview-generator.ts`
- Create: `apps/server/test/fixtures/tiny.mp4`
- Create: `apps/server/test/worker-media-integration.test.ts`
- Modify: `apps/server/src/worker.ts`
- Modify: `apps/server/src/jobs/boss.ts`

**Interfaces:**
- `JobEnvelope<T> = { payload: T; traceContext: Record<string, string> }`
- Idempotent handlers for inspection, preview, fragment purge, and video delete.
- One five-frame WebP contact sheet per fragment revision.

- [ ] **Step 1: Carry W3C trace context in every job**

```ts
export function envelope<T>(payload: T): JobEnvelope<T> {
  const traceContext: Record<string, string> = {};
  propagation.inject(context.active(), traceContext);
  return { payload, traceContext };
}

export async function inJobSpan<T>(
  job: Job<JobEnvelope<T>>,
  operation: (payload: T) => Promise<void>,
): Promise<void> {
  const parent = propagation.extract(context.active(), job.data.traceContext);
  return context.with(parent, () =>
    tracer.startActiveSpan(`job ${job.name}`, async (span) => {
      try {
        await operation(job.data.payload);
        span.setStatus({ code: SpanStatusCode.OK });
      } catch (error) {
        span.recordException(safeError(error));
        throw error;
      } finally {
        span.end();
      }
    }),
  );
}
```

Only job name, ID, attempt, entity ID, and revision become attributes.

- [ ] **Step 2: Implement idempotent video inspection**

The handler:

- locks the video and exits successfully when revision/status is stale;
- transitions `queued -> processing`;
- obtains the managed source through `LocalMediaFiles.withLocalPath`;
- runs the existing FFprobe adapter;
- stores duration as rounded safe integer microseconds plus dimensions, rational
  frame rate, audio, inspection timestamp/version;
- transitions to `ready` and increments the video revision;
- records a stable failure and throws on retryable tool/process errors.

No generic Cockatiel policy wraps FFprobe.

- [ ] **Step 3: Generate a revisioned five-frame contact sheet**

Select distinct timestamps nearest 10%, 30%, 50%, 70%, and 90% of the
fragment. Very short fragments may produce fewer samples.

```ts
export interface GeneratedPreview {
  readonly sampleUs: number[];
  readonly columns: number;
  readonly rows: 1;
  readonly frameWidth: number;
  readonly frameHeight: number;
  readonly staged: StagedBlob;
}
```

Generate 320×180 frames and one WebP row using FFmpeg. Publish to the revisioned
key, then transactionally insert the asset and replace
`fragment_previews` only if the fragment revision still matches. Queue deletion
of a superseded preview. Stale output is discarded.

- [ ] **Step 4: Start and stop worker handlers safely**

Register one `pg-boss` worker per queue with bounded concurrency:

```ts
await boss.work(jobNames.inspectVideo, { batchSize: 1 }, handleInspectVideo);
await boss.work(
  jobNames.generateFragmentPreview,
  { batchSize: 2 },
  handleGeneratePreview,
);
await boss.work(jobNames.purgeFragment, { batchSize: 4 }, handlePurgeFragment);
await boss.work(jobNames.deleteVideo, { batchSize: 1 }, handleDeleteVideo);
```

Update the worker heartbeat every five seconds. On SIGINT/SIGTERM, stop
fetching, allow current handlers to finish their idempotent boundary, stop
`pg-boss` gracefully, close Kysely, and flush telemetry.

- [ ] **Step 5: Add one real worker/media integration**

Generate and commit one tiny deterministic MP4 fixture:

```bash
ffmpeg -hide_banner -loglevel error -f lavfi -i testsrc2=size=320x180:rate=30 -f lavfi -i sine=frequency=440 -t 2 -c:v libx264 -pix_fmt yuv420p -c:a aac -movflags +faststart cut_on_eight/apps/server/test/fixtures/tiny.mp4
```

The single integration test uploads it, runs one inspection handler and one
preview handler, then verifies:

- the video becomes ready with media facts;
- the preview is a readable WebP;
- one preview record contains up to five ordered timestamps;
- rerunning each handler does not duplicate catalog/assets;
- a stale preview job cannot replace the current revision.

```bash
test -n "$CUT_ON_EIGHT_TEST_DATABASE_URL"
pnpm -C cut_on_eight test:server -- worker-media-integration.test.ts
```

- [ ] **Step 6: Commit durable media work**

```bash
git add cut_on_eight/apps/server/src/jobs cut_on_eight/apps/server/src/media cut_on_eight/apps/server/src/worker.ts cut_on_eight/apps/server/test/fixtures/tiny.mp4 cut_on_eight/apps/server/test/worker-media-integration.test.ts
git commit -m "feat: process videos and previews durably"
```

---

### Task 5: Adapt the Svelte Editor to the New API

**Files:**
- Create: `apps/web/src/domain/editor-model.ts`
- Create: `apps/web/src/domain/editor-mappers.ts`
- Create: `apps/web/src/domain/editor-mappers.test.ts`
- Create: `apps/web/src/components/ImportVideoButton.svelte`
- Modify: `apps/web/src/lib/api.ts`
- Modify: `apps/web/src/app/workspace-session.svelte.ts`
- Modify: `apps/web/src/app/fragment-library.svelte.ts`
- Modify: `apps/web/src/app/background-processing.svelte.ts`
- Modify: `apps/web/src/app/app-model.svelte.ts`
- Modify: `apps/web/src/components/LibraryView.svelte`
- Modify: `apps/web/src/components/EditorWorkspaceView.svelte`
- Modify: every web file importing editor types from the legacy contracts

**Interfaces:**
- Browser-only `ProjectDocument` and `Segment` retain seconds for media/editor
  calculations.
- API functions consume/return public microsecond DTOs.
- `WorkspaceSession` remains the coordinator used by existing components.

- [ ] **Step 1: Move editor models into the web application**

Move the current `ProjectDocument`, `Segment`, frame-rate, and `frameStepSeconds`
types/utilities into `domain/editor-model.ts`. Remove migration/Zod concerns.
Add private-to-web synchronization fields:

```ts
export interface Segment {
  id: string;
  startSeconds: number;
  endSeconds: number;
  exportSelected: boolean;
  title: string | null;
  description: string | null;
  tagIds: string[];
  revision: number;
}

export interface ProjectDocument {
  id: string;
  revision: number;
  sourceHref: string | null;
  // Preserve the current source, settings, playback, selection, segment,
  // metadata, and editor fields used by components.
}
```

Update imports mechanically. Components must not import
`@cut-on-eight/legacy-contracts`.

- [ ] **Step 2: Map seconds at the browser boundary only**

```ts
const US_PER_SECOND = 1_000_000;

export const toSeconds = (microseconds: number) =>
  microseconds / US_PER_SECOND;

export const toMicroseconds = (seconds: number) => {
  const value = Math.round(seconds * US_PER_SECOND);
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new Error('Editor timing is outside the supported range');
  }
  return value;
};

export function toProjectDocument(dto: EditorVideoDto): ProjectDocument;
export function toEditorSaveRequest(
  project: ProjectDocument,
): EditorSaveRequest;
export function toWorkspaceSnapshot(dto: WorkspaceDto): WorkspaceSnapshot;
```

The mapper test covers one non-integer media time round trip and revision/tag
preservation. No component test is needed for arithmetic.

- [ ] **Step 3: Replace browser API calls**

`lib/api.ts` must:

- parse Problem Details and expose `status`, `code`, and validation errors;
- upload a `File` using `FormData`;
- parse public video/fragment/workspace schemas;
- map workspace/editor DTOs to web domain models;
- save with `PATCH /api/videos/:id/editor`;
- use `/api/fragments/:id` for standalone mutation/delete/restore;
- use DTO-provided asset `href` values.

```ts
export async function importVideo(file: File): Promise<WorkspaceSnapshot> {
  const form = new FormData();
  form.set('source', file, file.name);
  const accepted = await request(
    '/api/videos',
    uploadAcceptedSchema,
    { method: 'POST', body: form },
  );
  return toWorkspaceSnapshot(accepted.workspace);
}
```

Do not set the multipart content-type manually.

- [ ] **Step 4: Replace the backend source picker with a reusable file input**

`ImportVideoButton.svelte` owns a hidden:

```svelte
<input
  bind:this={input}
  type="file"
  accept="video/mp4,.mp4"
  onchange={choose}
/>
```

The visible button opens it, clears the input before each selection so the same
file can be chosen again, and calls `onImport(file)`. Use it in the Library and
empty editor views. No application restart is needed to select another file.

- [ ] **Step 5: Preserve current workspace and autosave semantics**

Adapt `WorkspaceApi`; keep `SaveController` and its debounce/flush behavior.
Save-and-close flushes the editor aggregate before calling close. A `409
stale_revision` leaves local edits visible, marks the save failed, and offers
Retry after refresh; it never silently overwrites.

Creating a fragment remains an optimistic local edit. Generate its UUIDv7 in
the browser, mark the save dirty, and keep focus on the video container.

- [ ] **Step 6: Replace job events with processing-record polling**

Poll the workspace/video endpoints only while any visible video is
`receiving`, `queued`, `processing`, or `deleting`, or any visible fragment
preview is `pending`. Stop polling when all videos and previews reach a terminal
state or the model is disposed. Reuse existing status UI for concise
processing/failure state. Do not add SSE.

- [ ] **Step 7: Preserve editor keyboard/focus behavior explicitly**

Manually verify and retain:

- after marking, video focus indicator remains visible;
- Space with video focus plays/pauses full video;
- Left/Right and fast-seek variants reach the video controller;
- clicking a fragment changes visual focus to that fragment but does not play;
- Space with fragment focus loops that fragment;
- clicking video/thumbnail background selects full-video mode;
- timing keyboard/click editors work without a drag-only dependency;
- opening or saving another file does not restart the app.

- [ ] **Step 8: Run focused and complete frontend checks**

```bash
pnpm -C cut_on_eight test:web -- src/domain/editor-mappers.test.ts src/app/workspace-session.test.ts src/app/fragment-library.test.ts src/lib/editor-keyboard-context.test.ts
pnpm -C cut_on_eight svelte:fix apps/web/src/components/ImportVideoButton.svelte --svelte-version 5
pnpm -C cut_on_eight check:web
```

Expected: focused state tests and Svelte validation pass with no warnings.

- [ ] **Step 9: Commit the frontend cutover**

```bash
git add cut_on_eight/apps/web
git commit -m "feat: connect editor to PostgreSQL catalog"
```

---

### Task 6: Complete Video Deletion and the Slice Checkpoint

**Files:**
- Modify: `apps/server/src/videos/video-service.ts`
- Modify: `apps/server/src/jobs/processors/delete-video.ts`
- Modify: `apps/server/src/api/video-routes.ts`
- Modify: `apps/server/test/editor-fragment-api.test.ts`
- Modify: `apps/web/src/app/workspace-session.svelte.ts`
- Modify: `apps/web/src/app/fragment-library.svelte.ts`
- Modify: `apps/web/src/components/FragmentsPanel.svelte`
- Modify: existing video confirmation components

**Interfaces:**
- `DELETE /api/videos/:videoId` with `{ expectedRevision }`
- Existing confirmation and Undo UI remain visually stable.

- [ ] **Step 1: Make video deletion durable**

After the existing confirmation:

- lock and revision-check the video;
- set status `deleting` and hide it plus its fragments from normal queries;
- remove it from the open workspace and choose the next active video;
- enqueue `video.delete.v1` transactionally;
- return the updated workspace immediately.

The worker deletes only managed blob keys, then cascades catalog records.
Failure throws so `pg-boss` retries; it never deletes an external original.

- [ ] **Step 2: Keep fragment Undo server-timed**

The UI still shows Undo for eight seconds, but it uses the server's
`undoUntil`. Dismissing the toast does not trigger work; the durable purge job
already exists. An expired restore response removes the toast and refreshes.

- [ ] **Step 3: Run the Slice 2 checkpoint**

Automated:

```bash
pnpm -C cut_on_eight verify
```

Manual under `pnpm -C cut_on_eight dev`:

1. Import two MP4 files through the browser without restarting.
2. Confirm each exists under its own managed `videos/{video-id}/source/` folder
   before marking is enabled.
3. Mark fragments while watching; confirm focus stays on video.
4. Select a fragment and press Space; confirm only that fragment loops.
5. Edit timing/title/tags and restart the AppHost; confirm persistence.
6. Close one video explicitly and confirm its processing continues.
7. Delete/Undo a fragment without confirmation.
8. Delete a video with confirmation and confirm only managed data disappears.
9. Confirm preview jobs and API requests appear correlated in Aspire traces.

- [ ] **Step 4: Commit the Slice 2 checkpoint**

```bash
git add cut_on_eight/apps/server cut_on_eight/apps/web cut_on_eight/packages/api-contracts
git commit -m "feat: complete video and fragment catalog cutover"
```

## Slice 2 Exit Criteria

- Browser uploads are copied into the managed external data root before edits.
- PostgreSQL persists videos, fragments, tags, workspace, and editor state.
- Saves enqueue durable work and return without waiting for media processing.
- Five visible frames are stored as one revisioned WebP per fragment.
- Existing focus, keyboard, playback, close, confirmation, and Undo behavior is
  preserved.
- API responses expose no private server fields.
- The new vertical slice works after an AppHost restart.
