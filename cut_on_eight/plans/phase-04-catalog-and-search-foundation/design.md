# Phase 4: Catalog and Search Foundation

**Status:** Approved design

**Date:** 2026-07-26

**Product:** Cut on Eight

## Purpose

Phase 4 replaces the JSON catalogue with a relational catalog, introduces
ordered collections, adds fragment-first search, and establishes durable
background processing and observability.

The application remains a client-only Svelte SPA with a TypeScript backend.
PostgreSQL becomes authoritative. Qdrant is a rebuildable search projection
that can evolve independently as fragment features and embeddings are added.

This phase supersedes the JSON authority and root tag-registry decisions in
Phase 3. Existing JSON files are left untouched but ignored; there is no
migration because the current catalogue contains no valuable data.

## Product Shape

Fragments are the primary working entity. Videos provide source media and
context; they are not the default unit for browsing or search.

The top-level application sections are:

- **Editor** for watching a source video, marking fragments, and precise
  fragment editing.
- **Fragments** for browsing and playing fragments across videos.
- **Collections** for arranging reusable ordered sets of fragments.
- **Search** for fragment-first retrieval with an optional video scope.
- **Library** for exceptional video-level operations such as import, reopen,
  inspection, and deletion.

Search results show the fragment preview, title, timing, tags, and compact
source-video context. Opening a result can navigate to the source editor, but
fragment editing remains a separate explicit operation.

## Scope

### Included

- PostgreSQL 18.4 as the authoritative catalog.
- Kysely with the `pg` driver and code-based migrations.
- A local filesystem `BlobStore` rooted at `~/cut-on-eight_data`.
- Durable TypeScript background work backed by `pg-boss`.
- Ordered collections with title, description, and tags.
- Fragment-first PostgreSQL search and an optional video scope.
- A payload-only Qdrant fragment projection with idempotent updates and full
  rebuild.
- A TypeScript Aspire AppHost using Docker Desktop for PostgreSQL and Qdrant.
- Explicit public Zod DTOs separated from server domain and persistence models.
- Cockatiel resilience policies for appropriate remote calls.
- OpenTelemetry traces, metrics, and correlated structured logs in the Aspire
  dashboard.
- Preservation of current editor, playback, deletion, and multi-file workspace
  behavior.

### Deferred

- Embedding-model selection and automatic fragment feature extraction.
- Semantic, sparse, hybrid, and reranked search.
- Transcripts, OCR, frame analysis, image embeddings, and visual captions.
- A Python service until an actual feature extractor justifies it.
- Browser OpenTelemetry.
- Authentication and public-internet deployment.
- Remote object storage.
- Database migration from the old JSON documents.
- Automatic deduplication of imported videos.
- PostgreSQL replication and Qdrant clustering.

## Runtime Architecture

The TypeScript Aspire AppHost is the single local entry point:

```text
Svelte SPA ──HTTP──> Fastify API ──> PostgreSQL
                         │               │
                         │               └── pg-boss queue
                         │
                         ├──range reads──> local BlobStore
                         │
                         └──search───────> Qdrant (optional enhancement)

TypeScript worker ──────> PostgreSQL / pg-boss
       │
       ├───────────────> local BlobStore
       ├───────────────> FFmpeg / FFprobe
       └───────────────> Qdrant
```

During local development:

- Svelte, Fastify, and the worker run as normal host processes.
- Docker Desktop runs PostgreSQL 18.4 and Qdrant 1.18.3 as OCI containers.
- Aspire uses its default Docker runtime.
- PostgreSQL uses the named volume `cut-on-eight-postgres-data`.
- Qdrant uses the named volume `cut-on-eight-qdrant-data`.
- The application requires Docker Desktop for local Aspire container resources.

On macOS, the named volumes live inside Docker Desktop. They survive
container recreation but not deletion of Docker Desktop data. PostgreSQL logical
backups are therefore written outside the VM under
`~/cut-on-eight_data/backups/postgres/`. Qdrant is derived and needs no
independent backup.

System-wide Docker Desktop and Aspire CLI installation remains the user's
responsibility. `aspire doctor` is the environment preflight.

The same API and worker accept connection strings and storage roots through
environment variables. Moving to an external PostgreSQL server or Linux
mini-server therefore changes configuration, not domain code.

## Code Boundaries

The project remains vertically sliced and avoids a generic enterprise layer
stack:

```text
cut_on_eight/
  aspire.config.json
  aspire-apphost/
    apphost.mts
  apps/
    web/
    server/
      src/
        api/
        domain/
        persistence/
        media/
        search/
        jobs/
        observability/
        internal-api/
        server.ts
        worker.ts
  packages/
    api-contracts/
```

`apps/server` supplies two process entry points, API and worker, while sharing
server-only domain and infrastructure modules. A separate backend library is
not introduced until another application genuinely needs one.

`packages/api-contracts` contains only public request, response, and Problem
Details schemas safe to import in the browser. The existing persistence-shaped
project and workspace documents do not remain shared contracts.

Server-only code owns:

- Domain entities and invariants.
- Kysely table and row types.
- Database migrations.
- Filesystem keys, checksums, and physical paths.
- Job payloads and Qdrant projection records.
- Future Python-service contracts.

Every response is constructed by an explicit allowlist mapper and validated
against its public Zod schema. Persistence rows are never passed directly to
`reply.send`.

## Authoritative Catalog

Application-generated UUIDv7 values identify catalog entities. IDs are
available before a database insert so imports can reserve stable storage keys.

Fragment boundaries use integer microseconds in PostgreSQL. Public DTOs carry
safe integer microseconds; floating-point media seconds exist only at the
browser and FFmpeg boundaries. This avoids frame-number assumptions for
variable-frame-rate videos.

### Core records

| Record | Responsibility |
| --- | --- |
| `videos` | Source identity, title, description, media facts, lifecycle status, revision, and timestamps. |
| `fragments` | Video reference, start/end microseconds, title, description, export selection, revision, deletion state, and timestamps. |
| `tags` | Stable ID and canonical lowercase name. |
| `video_tags` | Video-to-tag assignments. |
| `fragment_tags` | Fragment-to-tag assignments. |
| `collections` | Title, description, revision, and timestamps. |
| `collection_tags` | Collection-to-tag assignments. |
| `collection_items` | Independent item ID, collection ID, fragment ID, and integer position. |
| `assets` | Logical storage key, owner, kind, MIME type, size, checksum, revision, and generation state. |
| `fragment_previews` | Fragment revision, preview asset, five sample timestamps, and sprite layout. |
| `search_projection_state` | Fragment revision, projection version, status, and last failure. |
| `workspace_videos` | Explicitly open videos, order, and last playback position. |
| `workspace_state` | The active video and workspace-level settings. |
| `editor_state` | Per-video timeline and editor preferences that must survive restart. |

`pg-boss` owns its queue tables. Kysely owns the application schema-migration
history. The application does not introduce competing job or migration tables.

### Invariants

- Tags are trimmed, stored lowercase, and unique.
- A fragment belongs to exactly one source video.
- Fragment start is non-negative and strictly before end.
- The existing maximum-two-overlaps rule remains enforced by the domain.
- A collection may contain a fragment more than once because each membership
  has its own ID.
- Collection positions are contiguous and unique within a collection.
- Reordering rewrites the small ordered list in one transaction.
- A fragment may belong to any number of collections.
- There is no hard collection-size limit; the design is intended to remain
  comfortable for roughly 1–100 items.
- Mutable aggregate records carry an integer revision for optimistic updates.
- A stale update returns `409 Conflict` rather than overwriting newer data.

## Media Storage

PostgreSQL stores logical asset keys, never absolute filesystem paths. The
configured `CUT_ON_EIGHT_DATA_ROOT` resolves those keys through the
application-owned `BlobStore` interface.

```text
~/cut-on-eight_data/
  incoming/
  videos/<video-id>/
    source/<original-name>
    derived/
    fragments/<fragment-id>/preview-r<revision>.webp
  backups/postgres/
```

The `BlobStore` exposes only the operations Cut on Eight needs: staged write,
atomic publish, range read, metadata inspection, and delete. It starts with a
local filesystem adapter but does not leak Node paths into domain or API
models.

Imported sources and published generated assets are immutable. Replacement
creates a revisioned asset key and changes the database reference. Superseded
derived assets are removed asynchronously.

Each fragment preview is one WebP contact sheet containing five visible 16:9
frames. Initial targets are approximately 10%, 30%, 50%, 70%, and 90% through
the fragment. Very short fragments may contain fewer distinct frames rather
than duplicated images. The database records sample timestamps and layout so
the UI can render the sheet as separate frames. Scene-aware sampling can later
replace the selection policy without changing the asset contract.

## Import and Processing

A browser file picker streams the selected source to Fastify. Opening a new
file never requires restarting the application.

The import lifecycle is:

1. Generate the video ID and create a `receiving` catalog record.
2. Stream to `incoming/` while computing size and SHA-256.
3. Atomically publish the source into its per-video directory.
4. In one PostgreSQL transaction, move the record to `queued` and enqueue the
   inspection job.
5. The worker runs FFprobe, records media facts, and generates derived video
   imagery.
6. The video becomes `ready`, or `failed` with a stable retryable processing
   state.

Stale `receiving` records and files are reconciled on startup. A completed
source without a committed catalog transition is treated as an orphan and
quarantined or removed; it never becomes an anonymous visible video.

Creating a fragment writes only catalog metadata and returns immediately.
Inline playback seeks and loops against the managed source video; it does not
render a clip file.

Timing changes increment the fragment revision and enqueue preview replacement.
Title, description, tag, video metadata, or collection-membership changes
enqueue search projection work. Job payloads carry the expected revision.
Workers check it before publishing, so stale work cannot replace newer output.

Jobs are idempotent. Generated files use staging plus atomic publish, Qdrant
uses deterministic fragment IDs, and database updates use expected revisions.
Saving never waits for preview or projection work.

## Collections

Collections are first-class catalog entities rather than saved search queries.
They carry title, description, and tags and contain an explicitly ordered list
of fragment references.

The Collections section provides:

- Collection creation and metadata editing.
- Ordered fragment browsing with linked source context.
- Add-to-collection actions from Fragments and Search.
- Move-up, move-down, and direct-position actions that work without drag and
  drop.
- Removal of one collection item without deleting its fragment.
- Navigation from an item to explicit fragment editing.

Deleting a fragment ultimately removes every collection item that references
it. Deleting a collection never deletes its fragments.

## Search

Search is a top-level application concept. It defaults to fragments and offers
a deliberate video-scope switch.

The first search implementation is PostgreSQL-backed and case-insensitive. It
matches:

- Fragment title and description.
- Fragment tags.
- Source-video title, description, and tags.
- Collection title and tags when filtering by collection.

The minimal controls are a query field, scope switch, and optional tag,
collection, and source-video filters. Fragment results remain the dominant
presentation and always include source context.

The API depends on a small `SearchProvider` boundary. Phase 4 uses
`PostgresSearchProvider`; later Qdrant hybrid search can replace or augment it
without changing page-level DTOs.

### Qdrant projection

Qdrant contains one point per fragment, using the fragment UUID as the point
ID. The payload contains only derived search data:

- Fragment and source-video IDs.
- Fragment title, description, tags, and timing.
- Source-video title, description, and tags.
- Collection IDs needed for filtering.
- Catalog revision and projection version.

Phase 4 stores these as zero-vector, payload-only points. Qdrant explicitly
supports points with no vector so vectors can be attached later. Such points
are available through scroll and filtering but do not participate in
nearest-neighbor search.

Projection writes are durable `pg-boss` jobs. They are idempotent, report
failure in `search_projection_state`, and never block catalog writes. A rebuild
command recreates the Qdrant collection from PostgreSQL and verifies the point
count. PostgreSQL search remains available while Qdrant is absent or rebuilding.

Dense, sparse, parent-specific, and experimental compressed representations
remain future named vectors or versioned collections. No placeholder embedding
is generated in this phase.

## Public API

Task-oriented HTTP resources replace filesystem-shaped routes:

- `/api/videos` for import, list, inspect, open, close, and delete.
- `/api/fragments` for list, create, edit, tag, restore, and delete.
- `/api/collections` for metadata, membership, and ordered replacement.
- `/api/search` for fragment-first search and optional video scope.
- `/api/assets/:id` for authorized media and preview delivery with HTTP range
  support.
- `/api/health/live` and `/api/health/ready` for process and dependency health.

The API returns a compact RFC 9457-style Problem Details body with a stable
application code. Validation failures use `422`, missing records use `404`,
stale revisions use `409`, and unavailable required dependencies use `503`.
Errors never expose absolute paths, SQL, job internals, or private catalog
fields.

Active processing records are polled at a short interval. Permanent SSE or
WebSocket infrastructure is deferred; resource DTOs do not depend on the
polling mechanism.

## Resilience

Cockatiel 4 provides Polly-style retry, timeout, circuit-breaker, bulkhead, and
fallback policies behind a small application-owned `ResilientCall` interface.

Policies apply to short remote calls such as:

- Qdrant.
- A future Python feature service.
- A future remote `BlobStore`.

Only classified transient network failures and suitable responses such as 429,
502, 503, and 504 are retried, using bounded jittered backoff.

Generic resilience policies do not wrap:

- PostgreSQL transactions, except an explicitly safe retry for a known
  serialization or deadlock failure.
- FFmpeg commands.
- `pg-boss` job execution.

`pg-boss` owns durable job retries and dead-letter behavior. This avoids stacked
retries, duplicate work, and retry storms.

## OpenTelemetry

The API and worker load one server-only OpenTelemetry bootstrap before other
application imports.

It configures:

- OpenTelemetry Node SDK with OTLP traces and metrics.
- Aspire-provided `OTEL_SERVICE_NAME`, resource attributes, endpoint, and
  protocol settings.
- Official `@fastify/otel` request and handler instrumentation.
- HTTP, Undici, PostgreSQL, and Node runtime instrumentation.
- Pino JSON logging enriched with trace and span IDs.
- Graceful telemetry flush on process shutdown.

Manual domain spans cover:

- Video import and inspection.
- Fragment preview generation.
- Fragment projection.
- Fragment search.
- Collection reorder.

W3C trace context is carried in job metadata so enqueue and worker processing
remain connected. Job name, job ID, attempt, entity ID, and revision are safe
span attributes; titles, descriptions, tags, and physical paths are not.

Initial low-cardinality metrics include job duration and outcome, import
throughput, preview duration, search latency, PostgreSQL fallback count, and
resilience-policy events.

Development samples all traces. Production sampling is configurable. The
Aspire dashboard and `aspire otel` commands are the primary local inspection
tools. Browser telemetry is not part of this phase.

## Deletion and Recovery

Fragment deletion remains immediate in the UI, requires no confirmation, and
keeps the existing short Undo opportunity. The database marks the fragment
deleted and hides its collection memberships during the grace period. Undo
clears the deletion marker and restores the same relationships. Expiry
permanently deletes the row and relationships and queues preview cleanup.

Video deletion requires explicit confirmation. It enters `deleting`, hides the
video and its fragments, and queues managed-file cleanup. Successful cleanup
permanently cascades the catalog records. Failure keeps the transition visible
to the worker for retry. External originals are never touched.

PostgreSQL is required for API readiness. Qdrant failure reports degraded search
enhancement but does not block editing or PostgreSQL search. Missing FFmpeg
makes the worker unready while catalog operations remain available.

Shutdown stops accepting new jobs and lets current work reach a safe,
idempotent boundary.

## Cutover

Phase 4 starts with a new empty PostgreSQL catalog:

1. Preserve existing `~/cut-on-eight_data` contents.
2. Create the PostgreSQL schema.
3. Start the new API and worker against PostgreSQL.
4. Ignore old project, workspace, catalogue metadata, and job JSON documents.
5. Import videos afresh through the new API.
6. Remove obsolete JSON-authority code only after the PostgreSQL vertical slice
   works end to end.

There is no dual-write period and no fallback to JSON authority.

## Delivery Slices

### Slice 1 — Runtime and catalog foundation

- TypeScript Aspire AppHost and Docker resources.
- Persistent PostgreSQL and Qdrant volumes.
- Kysely connection, migrations, and health checks.
- Public-contract split.
- OpenTelemetry bootstrap and Cockatiel boundary.

### Slice 2 — Video and fragment vertical slice

- Local `BlobStore` and staged import.
- PostgreSQL-backed library, workspace, and editor state.
- Fragment CRUD, tags, optimistic revisions, and deletion/Undo.
- `pg-boss` worker with inspection and preview jobs.
- Existing editor and inline playback connected to the new API.

### Slice 3 — Collections and search

- Ordered collection CRUD and metadata.
- Fragment-first PostgreSQL search UX.
- Payload-only Qdrant projection and rebuild.
- Search and collection navigation into the editor.

### Slice 4 — Cutover hardening

- Recovery and cleanup paths.
- PostgreSQL logical backup command.
- Removal of obsolete JSON-authority code.
- Practical end-to-end verification and documentation.

## Pragmatic Verification

Tests focus on application behavior rather than layers:

- Feature-level Fastify tests use `Fastify.inject()` against a real isolated
  PostgreSQL test database and cover validation, domain behavior, persistence,
  and public response shape together.
- A few unit tests cover only genuinely tricky pure logic, principally timing
  invariants and collection reordering.
- One worker integration test uses a tiny video fixture to verify inspection
  and preview generation.
- One Qdrant smoke test verifies projection upsert, deletion, and rebuild.
- A small Playwright happy-path smoke covers import, fragment edit, tag,
  collection reorder, search, and inline playback.
- OpenTelemetry and resilience behavior are inspected manually in the Aspire
  dashboard during development rather than asserted through custom telemetry
  test infrastructure.

Tests do not verify Kysely, Fastify, Cockatiel, PostgreSQL, Qdrant, or
OpenTelemetry internals. Normal work uses `pnpm -C cut_on_eight verify`; the
browser smoke is reserved for phase checkpoints.

## Acceptance Criteria

Phase 4 is complete when:

1. One Aspire command starts the host applications and persistent Docker
   resources.
2. PostgreSQL 18.4 is the sole catalog authority and the application no longer
   reads or writes authoritative JSON documents.
3. Import copies a source into the managed per-video directory before fragment
   work begins.
4. Video, fragment, tag, workspace, and editor behavior survives restart.
5. Saves return without waiting for durable inspection, preview, or projection
   work.
6. Collections support metadata, ordered membership, multiple collection
   membership, and technically duplicated fragment items.
7. Search is top-level, fragment-first, PostgreSQL-backed, and shows source-video
   context.
8. Qdrant contains a rebuildable payload-only fragment projection and its
   failure never blocks editing.
9. Public DTOs cannot expose server-only persistence or operational fields.
10. Aspire shows correlated API and worker telemetry, including queued work.
11. Video and fragment deletion preserve their established confirmation and
    Undo behavior and recover safely from interruption.
12. The pragmatic verification suite and browser checkpoint pass.

## References

- [Phase 3 design](../phase-03-fragment-library/design.md)
- [Aspire container runtime selection](https://aspire.dev/deployment/docker-compose/)
- [Aspire telemetry](https://aspire.dev/fundamentals/telemetry/)
- [Aspire OpenTelemetry CLI](https://aspire.dev/reference/cli/commands/aspire-otel/)
- [PostgreSQL 18.4 release](https://www.postgresql.org/docs/release/18.4/)
- [Qdrant releases](https://github.com/qdrant/qdrant/releases)
- [Qdrant payload-only points](https://qdrant.tech/documentation/faq/qdrant-fundamentals/#how-many-vectors-can-i-store-in-a-point-can-a-point-have-no-vector-at-all)
- [Cockatiel](https://github.com/connor4312/cockatiel)
- [Fastify OpenTelemetry](https://www.npmjs.com/package/@fastify/otel)
