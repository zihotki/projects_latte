# Cut on Eight

Cut on Eight is a local macOS app for importing dance videos, marking precise
fragments, editing their timing and metadata, and browsing the resulting video
and fragment library. It is in active development: the PostgreSQL catalog,
durable media-processing worker, fragment library, tags, previews, and
event-driven Qdrant projection are working. Collections and user-facing
server-side/semantic search are next.

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
projector, `thumbnails-service`, and Svelte app. Open the Vite URL shown by Aspire
(normally <http://127.0.0.1:5173>); its dashboard URL is printed too.

From the repository root, use `pnpm -C cut_on_eight dev` instead.

### Default data locations

The application-owned media directory is `~/cut-on-eight_data`. Imported files
are copied there before processing, and source videos plus generated fragment
previews remain there. Do not edit or remove its contents while the app is
using them.

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

## Current functionality

- Import a video through the browser, then work from the managed copy.
- Keep several videos open, switch between them, save-and-close safely, and
  return to them from the library.
- Create fragments while watching, loop a selected fragment, nudge its start
  and end with clicks or the keyboard, and edit its title, description, and
  lower-case tags.
- Browse a standalone fragment library with five-frame previews; delete and
  restore fragments, or delete videos with confirmation.
- Run inspection and preview generation as durable background work. Saves do
  not wait for that work, and the worker resumes queued work after restart.

## Search and consistency

The current Fragments view is a fast local filter over the loaded catalog. It
matches fragment titles and source-video names, and filters by video and tags.
It is immediately consistent with the catalog once the view refreshes; there
is no server-side ranking or semantic retrieval yet.

Every visible fragment is also projected asynchronously to Qdrant. A save
commits PostgreSQL state and an immutable outbox event in one transaction. The
outbox relay publishes that event to NATS JetStream, and the Qdrant projector
applies it idempotently; a new edit or deletion can therefore take a moment to
appear in Qdrant.
The projection contains only search metadata (titles, descriptions, tags,
timing, and source context), uses no embeddings, and never blocks editing.
`search:rebuild` recreates it from PostgreSQL if needed. JetStream is bounded
operational delivery; PostgreSQL remains the durable replay source.

For an audit or a clean projection run, `pnpm events:replay` copies the archived
events into a new, isolated JetStream replay stream and records the run in
PostgreSQL. It never rewinds the live consumers or republishes into the live
stream.

## Architecture

The Svelte 5 SPA runs in the browser. A local Fastify API and a separate worker
run on the host; PostgreSQL is the source of truth, while the external media
directory is the blob store. Aspire coordinates those processes with PostgreSQL
and Qdrant containers in Docker Desktop. See [the architecture note](docs/architecture.md)
for boundaries, data ownership, and the planned search model.

## Verification

```bash
pnpm verify
```

From the repository root, `./scripts/verify.sh` adds the Docker PostgreSQL
integration suite.
