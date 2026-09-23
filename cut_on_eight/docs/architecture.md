# Architecture

## Current runtime

Aspire is the local entry point. It starts persistent Docker containers for
PostgreSQL 18.4, Qdrant 1.18.3, and NATS 2.14.3 with JetStream, runs catalog
migrations, and then starts the API, worker, outbox relay, `search-indexer`,
`thumbnails-service`, and Svelte development server as host processes.

```text
Svelte SPA ──HTTP──> Fastify API ──> PostgreSQL catalog + pg-boss queue
                              │
                              ├──> ~/cut-on-eight_data (source media and previews)
                              └──> integration event archive + outbox

Worker ───────────────────────> PostgreSQL / pg-boss / local media / FFmpeg
Outbox relay ────────────────> NATS JetStream ──> search-indexer ──> Qdrant
                                              └──> thumbnails-service ──> ~/cut-on-eight_thumbnails
Fastify search API ──────────> LM Studio embeddings (optional) / Qdrant
```

## Ownership and durability

- PostgreSQL is the authoritative store for videos, fragments, tags, editor
  state, workspace state, assets, projection state, and durable background jobs.
- `~/cut-on-eight_data` is an application-owned local blob store. An import is
  copied there before the catalog publishes the video. Historical
  fragment-preview assets remain readable during the thumbnail cutover.
- Docker named volumes retain PostgreSQL and Qdrant data between AppHost runs.
  NATS has its own bounded operational volume. PostgreSQL is authoritative;
  Qdrant is disposable because it is intended to be rebuilt from PostgreSQL.
- The API returns after durable catalog/job state is committed. Inspection,
  cleanup, and purge work run asynchronously through `pg-boss`. Per-video
  thumbnail generation runs in `thumbnails-service`; new fragment edits do
  not queue per-fragment preview jobs.

## Current product boundary

The current vertical slice supports video import, editor and workspace state,
fragment CRUD, title/description/tag editing, video and fragment deletion,
reusable video thumbnails, and the standalone fragment library. The older
JSON-based project format is not migrated into the PostgreSQL catalog; new
videos should be imported through the current application.

## Search

The Search view is fragment-first. Its Fastify endpoint accepts one plain-text
query plus optional tag, collection, and source-video filters. It returns
fragment metadata, source-video context, and existing preview URLs; it never
exposes local media paths, database state, or raw Qdrant payloads.

For each embedding profile, Qdrant stores a versioned collection
with two named vectors: `lexical-v1` is local BM25 with IDF and `semantic-v1`
is a cosine dense vector. The canonical indexed document contains fragment
title, description, and lowercase tags plus source title, description, and
lowercase tags. Collection metadata is deliberately excluded so a collection
rename does not require re-embedding all of its fragments. Keyword payload
indexes support the explicit source-video, collection, and tag filters.

With `CUT_ON_EIGHT_EMBEDDINGS_URL` configured, the API sends the query to the
OpenAI-compatible LM Studio `/v1/embeddings` endpoint using the configured
profile (by default `google/embeddinggemma-300M`, 768 dimensions). Qdrant
retrieves dense and BM25 candidates and fuses them with reciprocal-rank fusion.
Tags participate in the indexed text, so a tag match boosts ranking; only a
visible UI filter narrows results.

Without an embedding endpoint, the indexer writes BM25 vectors only and search
runs in lexical mode. If LM Studio is temporarily unavailable, the API falls
back to lexical querying while the durable indexer retries the pending dense
work. If Qdrant is unavailable, search is temporarily unavailable; neither
failure prevents catalog writes.

Projection state lives in PostgreSQL. A catalog mutation commits first alongside
an immutable integration event and an outbox-publication row. The relay publishes
to JetStream after commit; `search-indexer` re-reads current catalog state and
applies source-positioned, idempotent upserts and deletes. The search index is
therefore deliberately eventually consistent, while catalog editing is strongly
consistent. Qdrant is disposable derived state.

The active alias `cut_on_eight_fragments_active` isolates reads from rebuilding.
`pnpm search:rebuild` creates a fresh profile collection, indexes a PostgreSQL
snapshot, catches up with events after its high-water mark, verifies that its
point count equals the visible catalog count, then atomically moves the alias.
Failed rebuild collections remain available for diagnosis and never replace the
active index.

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
