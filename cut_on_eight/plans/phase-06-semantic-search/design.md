# Semantic Search Design

**Status:** Approved for planning

## Purpose

Add a fragment-first search service that combines semantic similarity with
exact terminology. It must search dance vocabulary, names, titles, tags, and
free-form descriptions without making catalog edits wait for indexing.

PostgreSQL remains authoritative. Qdrant is a disposable, eventually
consistent read model. Search is deliberately a separate concern from video
fragmenting and thumbnail generation.

## Product Shape

Search is a top-level view with one plain-language input, fragment-first
results, visible source-video context, and thumbnail previews. Optional UI
filters narrow by tag, collection, and source video.

A term that matches a known tag is a ranking boost, not an implicit filter.
The first version has no query language, automatic hard filters, or video-first
search mode. Video search and advanced syntax remain future work.

## Retrieval Model

Each fragment has one Qdrant point with payload filters and two named vectors:

```text
semantic-v1  dense cosine vector from EmbeddingGemma via LM Studio
lexical-v1   sparse BM25 vector generated locally by Qdrant
```

The configured active embedding profile supplies its stable profile ID, model
name, expected dimensions, and LM Studio OpenAI-compatible endpoint. The
initial active profile is `embeddinggemma-v1`. Other compatible profiles,
including Qwen3-Embedding, can be configured and indexed later, but only one
is active for user search at a time. Agent/chat models are not embedding
profiles and are not used for retrieval.

The collection name includes the profile and schema version. Its public alias
identifies the active profile. A model or vector-shape change creates and
backfills a new collection, then atomically moves the alias; it never mutates
or discards a working collection in place.

BM25 runs inside the self-hosted Qdrant 1.18.3 container using its
`qdrant/bm25` inference model. It needs no second LLM, Python service, or
network model download. The collection config enables IDF for `lexical-v1`.

## Search Document and Ranking

`search_text_v1` is canonical, deterministic, and versioned. It contains:

- fragment title and description;
- normalized lowercase fragment tags;
- source-video title, description, and tags.

It deliberately excludes collection title, description, and tags. A collection
rename must not force every member fragment to be re-embedded. Collection IDs
remain keyword payload filters.

At query time the API embeds the input through LM Studio and sends the original
text to Qdrant BM25. It prefetches dense and sparse candidates using the same
payload filter, fuses them with reciprocal-rank fusion, and returns the first
page of fragment results. Tags therefore influence both lexical ranking and
visible filter choices, without hidden narrowing.

If LM Studio is unavailable, the endpoint still performs lexical-only BM25
search. If Qdrant is unavailable, the endpoint reports search unavailable; it
does not fall back to unbounded browser filtering or block catalog operations.

## Durable Indexing

The existing immutable `fragment.changed.v1` and `fragment.deleted.v1` events
remain the source of index work. A new durable JetStream consumer,
`search-indexer-v1`, replaces the payload-only projector for the active
collection:

```text
fragment mutation + outbox transaction
  -> JetStream CUT_ON_EIGHT_EVENTS
  -> search-indexer-v1
  -> current catalog fragment + search_text_v1
  -> LM Studio dense embedding + Qdrant BM25 document
  -> Qdrant upsert/delete + PostgreSQL projection state
```

The indexer resolves current catalog state rather than trusting stale event
text. It stores event position, fragment revision, text hash, profile ID, and
index status in PostgreSQL. Duplicate or stale deliveries are acknowledged
without changing Qdrant. A deletion removes the Qdrant point before recording
the newer source position.

Transient LM Studio or Qdrant failures leave the JetStream message unacknowledged
for retry. This creates visible index lag but never loses the committed catalog
change. The API exposes a compact index-status summary so the UI can say that
recent edits are still indexing rather than implying strong consistency.

## Backfill and Profile Changes

`search:rebuild --profile <id>` creates a new versioned collection, starts its
own durable consumer, records the archive high-water position, indexes a
current PostgreSQL snapshot, then catches events newer than that position. The
stored source position and text hash make the snapshot/event overlap safe.
After the consumer is caught up, the command validates collection counts and
moves the active alias. The previous collection remains available for rollback
until an explicit operator cleanup command deletes it.

This uses PostgreSQL as the durable recovery source and JetStream only for
operational delivery. It is not event sourcing and does not replay events into
the live stream.

## Runtime and Boundaries

Aspire continues to own PostgreSQL, NATS, Qdrant, API, and workers. LM Studio
is external: Aspire passes an endpoint and selected profile to `search-indexer`
and the API, but does not install or launch LM Studio. The endpoint can point
at the local Mac now or a future Mac mini later.

The new `search-indexer` process is independent from `thumbnails-service` and
the general worker. Thumbnails stay per-video and are reused in result cards;
they are not re-generated by search.

## Verification

- Unit-test canonical search text, profile validation, filter mapping, and
  indexer idempotency.
- Add a Qdrant integration test that creates the hybrid collection, upserts a
  BM25 document and dense test vector, then verifies RRF plus payload filters.
- Add an LM Studio-compatible fake HTTP server test for embedding requests and
  lexical-only degradation.
- Extend the Docker integration suite to prove PostgreSQL event -> JetStream ->
  search indexer -> Qdrant result, including a deliberate LM Studio outage and
  recovery.
- Keep `./scripts/check.sh`, `./scripts/test.sh`, and
  `./scripts/integration.sh` as handoff gates.

## Non-goals

- Automatic feature extraction from media.
- Reranking models, SPLADE, neural sparse models, or a second embedding model
  in the initial profile.
- Search history, saved searches, query syntax, relevance feedback, or manual
  ranking controls.
- Video-first result pages and collection-content semantic indexing.
- Retention or backup policy for retired index collections.
