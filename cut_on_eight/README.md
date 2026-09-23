# Cut on Eight

Cut on Eight is a browser app for importing dance videos, marking precise
fragments, editing their timing and metadata, browsing the resulting video and
fragment library, and searching fragments. It is in active development: the
PostgreSQL catalog, durable media-processing worker, fragment library, tags,
video thumbnail bundles, and eventually consistent hybrid Qdrant search are working.

## Install

Prerequisites: macOS, Node.js 24+, pnpm 11.13 (via Corepack), Docker Desktop,
the Aspire CLI, and `ffmpeg`/`ffprobe` on `PATH`.

```bash
corepack enable
pnpm install
```

## Run locally

From this directory:

```bash
pnpm dev
```

Aspire starts Docker-backed PostgreSQL, Qdrant, and NATS JetStream, runs
migrations, then starts the Fastify API, pg-boss worker, outbox relay, Qdrant
search indexer, `thumbnails-service`, and Svelte app. Open the Vite URL shown
by Aspire (normally <http://127.0.0.1:5173>); its dashboard URL is printed too.

From the repository root, use `pnpm -C cut_on_eight dev` instead.

### Default data locations

The application-owned media directory is `~/cut-on-eight_data`. Imported files
are copied there before processing. Source videos and any older fragment
previews remain there. New fragment cards reuse the separate video thumbnail
bundles. Do not edit or remove these files while the app is using them.

The authoritative catalog and durable job queue are in Docker's named volume
`cut-on-eight-postgres-data`. Qdrant uses the separate, rebuildable
`cut-on-eight-qdrant-data` volume; NATS JetStream retains operational events in
`cut-on-eight-nats-data`. Reusable video thumbnail bundles live in
`~/cut-on-eight_thumbnails`, outside the source-media root. To override either
local media directory, provide
an absolute path:

```bash
CUT_ON_EIGHT_DATA_ROOT=/absolute/path/to/cut-on-eight-data pnpm dev
CUT_ON_EIGHT_THUMBNAIL_ROOT=/absolute/path/to/cut-on-eight-thumbnails pnpm dev
```

### Optional semantic embeddings

Hybrid search uses BM25 in Qdrant and, when configured, dense vectors from an
external LM Studio server. Download and load
`google/embeddinggemma-300M` in LM Studio, enable its OpenAI-compatible server,
then start the app with its `/v1` endpoint:

```bash
CUT_ON_EIGHT_EMBEDDINGS_URL=http://127.0.0.1:1234/v1 pnpm dev
```

The default profile is `embeddinggemma-v1`, with model
`google/embeddinggemma-300M` and 768 dimensions. Override the profile, model,
or dimensions only as a matching set when changing embedding models:

```bash
CUT_ON_EIGHT_EMBEDDING_PROFILE=my-profile \
CUT_ON_EIGHT_EMBEDDING_MODEL=provider/model \
CUT_ON_EIGHT_EMBEDDING_DIMENSIONS=768 \
CUT_ON_EIGHT_EMBEDDINGS_URL=http://127.0.0.1:1234/v1 \
pnpm dev
```

## Current functionality

- Import a video through the browser, then work from the managed copy.
- Keep several videos open, switch between them, save-and-close safely, and
  return to them from the library.
- Create fragments while watching, loop a selected fragment, nudge its start
  and end with clicks or the keyboard, and edit its title, description, and
  lower-case tags.
- Browse a standalone fragment library with up to five video-bundle frames; delete and
  restore fragments, or delete videos with confirmation.
- Search fragments from the top-level Search view with plain text and optional
  tag, collection, or source-video filters. Results include their source video
  and existing previews.
- Check queued and active video work in the compact Processing panel. Import,
  inspection, and video thumbnail generation do not block fragment edits.

## Search and consistency

Search is fragment-first and server-side. Qdrant combines exact lexical BM25
matches with dense semantic matches through reciprocal-rank fusion when LM
Studio embeddings are available. Fragment and source titles, descriptions, and
tags contribute to ranking; known tags boost results rather than silently
narrowing them. Tag, collection, and source-video filters are explicit UI
constraints.

Without `CUT_ON_EIGHT_EMBEDDINGS_URL`, indexing and queries remain lexical
BM25-only. If the configured LM Studio endpoint is temporarily unavailable, a
query degrades to lexical results; the durable indexer retries failed embedding
work up to ten deliveries, then records a failed index state for recovery.
Qdrant unavailability returns a temporary search
error, but never blocks editing or catalog writes.

Every visible fragment is indexed asynchronously. A save commits PostgreSQL
state and an immutable outbox event in one transaction. The outbox relay
publishes it to NATS JetStream, and the `search-indexer` re-reads current
catalog state before applying a source-positioned, idempotent update. A recent
edit or deletion can therefore take a moment to appear in search. PostgreSQL
remains the durable replay source; Qdrant is disposable derived state.

`pnpm search:rebuild` creates a fresh profile collection, indexes a PostgreSQL
snapshot, catches up with later events, verifies its point count, and atomically
moves the active Qdrant alias only after the target is ready. Use it after a
profile or vector-dimension change, or to recover the index.

For an audit or a clean projection run, `pnpm events:replay` copies the archived
events into a new, isolated JetStream replay stream and records the run in
PostgreSQL. It never rewinds the live consumers or republishes into the live
stream.

## Architecture

The Svelte 5 SPA runs in the browser. A local Fastify API and separate workers
run on the host; PostgreSQL is the source of truth, while the external media
directory is the blob store. Aspire coordinates those processes with
PostgreSQL, Qdrant, and NATS containers in Docker Desktop. See [the architecture
note](docs/architecture.md) for boundaries, data ownership, and search
operation.

For a Linux single-host container setup, see the
[homelab deployment guide](docs/homelab-deployment.md). It uses persistent
host media directories and an existing PostgreSQL service. S3 storage is a
future adapter, not a current config option.

## Verification

```bash
pnpm verify
```

From the repository root, `./scripts/verify.sh` adds the Docker PostgreSQL
integration suite.
