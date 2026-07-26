# Event Pipeline Design

**Status:** Approved for planning

## Purpose

Introduce a durable event pipeline for derived processing while keeping the
PostgreSQL catalog authoritative. The first consumers are Qdrant fragment
projection and video thumbnail generation. The design is intentionally not
event sourcing: catalog tables are the write model, and integration events are
an immutable, replayable record for asynchronous consumers.

## Topology

```text
Fastify command handler
  └─ PostgreSQL transaction
      ├─ catalog row changes
      └─ immutable integration event + pending publication

outbox-relay ──> JetStream CUT_ON_EIGHT_EVENTS
                    ├─ qdrant-projector-v1
                    └─ thumbnail-generator-v1
                            └─ thumbnails-service
                                 ├─ FFmpeg generation
                                 └─ read-only thumbnail HTTP origin
```

Aspire runs PostgreSQL, Qdrant, NATS, API, the existing general worker,
`outbox-relay`, `qdrant-projector`, Svelte web, and `thumbnails-service`.
`thumbnails-service` is a single host process: it runs the named JetStream
consumer and its Fastify origin together, but it remains isolated from the API.

## Durable Events and Delivery

Each catalog transaction appends a versioned JSON integration event to
`integration_events`, then creates its matching `event_publications` record.
The relay leases unpublished rows, publishes them to JetStream with `eventId`
as the broker message ID, waits for broker acknowledgement, and records the
broker sequence. If it stops between publishing and recording success, it
publishes again; consumers must therefore be idempotent.

PostgreSQL retains integration events. JetStream retains the operational stream
for 30 days or 1 GiB. The archive supports isolated replay streams and consumer
tests after normal JetStream retention expires. Historic replay never publishes
back into the live stream.

The initial event types are:

```text
fragment.changed.v1
fragment.deleted.v1
video.thumbnails.requested.v1
```

Fragment changed events contain the complete Qdrant payload required at that
revision. Thumbnail-request events contain only video and source-asset IDs plus
the thumbnail profile version; the service resolves media storage through the
catalog. Events never contain media bytes, local paths, checksums, or secrets.

## Qdrant Projection

`qdrant-projector-v1` is an explicit-acknowledgement durable pull consumer.
It processes one event at a time. PostgreSQL records the last projected
fragment revision and source event so duplicate or stale deliveries are skipped.
Qdrant remains eventually consistent and disposable; `search:rebuild` makes a
fast current-state rebuild from PostgreSQL rather than replaying every edit.

## Per-Video Thumbnails

There is exactly one current thumbnail bundle per video/source asset/profile.
It is generated after successful video inspection, not after fragment changes.
Fragments reuse the video manifest: the UI selects the nearest five sampled
frames that lie in the fragment's time range and renders their sprite cells.
Fragments have no thumbnail assets, records, events, jobs, or cleanup.

`video_thumbnail_state` holds the current source asset, processing state,
opaque storage pointer, manifest, and safe failure code. The physical bundle
is created under a separate root, defaulting to `~/cut-on-eight_thumbnails`:

```text
staging/<random>/manifest.json
staging/<random>/sprite-001.<content-hash>.webp
published/<opaque-current-bundle>/manifest.json
published/<opaque-current-bundle>/sprite-001.<content-hash>.webp
```

The service validates the completed staging bundle, publishes it, switches the
database pointer, then removes the previous bundle after a one-hour grace
period. Deleting a video removes its thumbnail state and bundle as part of its
final deletion work. A failed or superseded generation cannot expose a partial
bundle.

## Thumbnail HTTP and Caching

`thumbnails-service` owns these stable public routes:

```text
GET /thumbnail-cdn/v1/videos/:videoId/manifest.json
GET /thumbnail-cdn/v1/videos/:videoId/:fileName
```

The manifest is read from the current bundle through the database pointer and
uses `Cache-Control: no-cache` plus an ETag. Its `pages` list contains hashed
sprite filenames. Sprite responses use
`Cache-Control: public, max-age=31536000, immutable`. Consequently, the tiny
manifest revalidates whenever the client needs it, while large WebP pages cache
indefinitely. The one-hour old-bundle grace period prevents a client with an
already fetched manifest from encountering a deleted page during replacement.

The origin validates the UUID and approved manifest/sprite filename forms; it
never maps arbitrary paths or serves source video media. It binds to
`127.0.0.1` locally. A mini-server reverse proxy may expose it later.

## Non-goals

- Full event sourcing or replacing catalog tables with event replay.
- User-facing vector/semantic Qdrant search.
- Thumbnail generation for individual fragments.
- Migrating legacy JSON projects or their thumbnail folders.
- Temporal workflows, object storage, or a multi-node NATS cluster.
- Deciding long-term event and backup retention; those are intentionally
  deferred until the mini-server rollout.
