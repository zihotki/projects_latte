# Architecture

## Current runtime

Aspire is the local entry point. It starts persistent Docker containers for
PostgreSQL 18.4, Qdrant 1.18.3, and NATS 2.14.3 with JetStream, runs catalog
migrations, and then starts the API, worker, outbox relay, Qdrant projector,
`thumbnails-service`, and Svelte development server as host processes.

```text
Svelte SPA ──HTTP──> Fastify API ──> PostgreSQL catalog + pg-boss queue
                              │
                              ├──> ~/cut-on-eight_data (source media and previews)
                              └──> integration event archive + outbox

Worker ───────────────────────> PostgreSQL / pg-boss / local media / FFmpeg
Outbox relay ────────────────> NATS JetStream ──> Qdrant projector ──> Qdrant
                                              └──> thumbnails-service ──> ~/cut-on-eight_thumbnails
```

## Ownership and durability

- PostgreSQL is the authoritative store for videos, fragments, tags, editor
  state, workspace state, assets, projection state, and durable background jobs.
- `~/cut-on-eight_data` is an application-owned local blob store. An import is
  copied there before the catalog publishes the video; the worker writes
  generated fragment-preview assets there too.
- Docker named volumes retain PostgreSQL and Qdrant data between AppHost runs.
  NATS has its own bounded operational volume. PostgreSQL is authoritative;
  Qdrant is disposable because it is intended to be rebuilt from PostgreSQL.
- The API returns after durable catalog/job state is committed. Inspection,
  preview generation, cleanup, and purge work run asynchronously through
  `pg-boss` and resume after a worker restart.

## Current product boundary

The current vertical slice supports video import, editor and workspace state,
fragment CRUD, title/description/tag editing, video and fragment deletion,
fragment-preview generation, and the standalone fragment library. The older
JSON-based project format is not migrated into the PostgreSQL catalog; new
videos should be imported through the current application.

## Search today and later

Today, the Fragments view fetches fragments, videos, and tags from the
PostgreSQL-backed API and filters them in the browser by title, source video,
video selection, and tags. It is not a search service and has no index lag: a
refresh reads current catalog data.

The worker now projects every visible fragment to the Qdrant collection
`cut_on_eight_fragments_v1`. Each payload has the fragment/source IDs, titles,
descriptions, lowercase tags, timing, fragment revision, and projection version;
it contains no media paths, checksums, or operational data. The point has no
vector yet, so it is ready for future filtering and embeddings but does not
provide nearest-neighbour retrieval today.

Projection state lives in PostgreSQL. A catalog mutation commits first alongside
an immutable integration event and an outbox-publication row. The relay publishes
to JetStream after commit; the named Qdrant consumer applies source-positioned,
idempotent upserts and deletes. Consequently, the projection is deliberately
eventually consistent. Qdrant failures do not block catalog writes, and
`pnpm search:rebuild` recreates it from PostgreSQL.

`pnpm events:replay` materializes the immutable PostgreSQL archive into a new,
separate JetStream replay stream, with progress recorded in `event_replay_runs`.
It deliberately leaves the live stream and consumers untouched; an operator can
bind an isolated projection consumer to that stream for recovery or inspection.

Video inspection also emits a thumbnail request. `thumbnails-service` consumes
it, generates one reusable WebP sprite bundle per video/source/profile, and
serves a stable manifest URL with revalidation plus fingerprinted immutable
sprite pages. Fragments select their nearest five in-range manifest samples;
they do not own thumbnail jobs or files. A successful replacement switches the
current bundle pointer; old bundles are deleted after a one-hour grace period,
and the video purge deletes the current bundle.

The intended next model is fragment-first server-side search, followed by
embeddings and extracted fragment features. PostgreSQL remains transactional;
Qdrant may lag a recent edit or deletion while editing stays strongly consistent.
