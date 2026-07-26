# Semantic Search Implementation Plan

**Status:** Planned

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver fragment-first hybrid search with Qdrant BM25 and
EmbeddingGemma vectors, durably built from catalog events and exposed through a
small top-level Svelte search view.

**Architecture:** PostgreSQL remains authoritative; `fragment.changed.v1` and
`fragment.deleted.v1` drive an idempotent JetStream `search-indexer` that reads
current catalog state and upserts hybrid Qdrant points. The API performs
dense+sparse reciprocal-rank fusion, while the UI supplies a plain-text query
and explicit filters. LM Studio is an external OpenAI-compatible embedding
endpoint configured by Aspire; BM25 is local to Qdrant.

**Tech Stack:** TypeScript, Fastify 5, Svelte 5, Zod,
Qdrant HTTP API, Qdrant 1.18.3, NATS JetStream,
PostgreSQL 18.4, Kysely, Vitest, Aspire TypeScript AppHost.

## Global Constraints

- Keep the PostgreSQL catalog as the transactional write authority; Qdrant is
  disposable and eventually consistent.
- Reuse immutable `fragment.changed.v1` and `fragment.deleted.v1`; do not add
  events containing media paths, bytes, secrets, or vectors.
- The default profile is `embeddinggemma-v1`, model
  `google/embeddinggemma-300M`, cosine distance, and 768 dimensions.
- `CUT_ON_EIGHT_EMBEDDINGS_URL` is an optional absolute `http` or `https` URL
  ending in `/v1`; when absent, indexing and querying remain lexical-only.
- BM25 uses Qdrant’s local `qdrant/bm25` model and a sparse vector named
  `lexical-v1` with IDF enabled. Do not add Python, FastEmbed, SPLADE, or a
  second model service.
- The dense vector is named `semantic-v1`. A profile or dimension change creates
  a fresh versioned collection and moves an alias only after backfill catches up.
- `search_text_v1` contains fragment title/description/tags and source
  title/description/tags; collection metadata is never copied into every
  fragment document.
- Tag matches boost rank through `search_text_v1`; they never silently become
  filters. UI filters are only tag IDs, collection IDs, and source-video IDs.
- Keep `thumbnails-service` unchanged. Search results reuse its existing
  fragment preview/thumbnail URLs.
- Run `./scripts/check.sh` and `./scripts/test.sh` before handoff; run
  `./scripts/integration.sh` when Docker is available.

## File Map

```text
apps/server/src/
  catalog/migrations/004-semantic-search.ts              # state and rebuild metadata
  catalog/{database-types,migrations/index}.ts            # Kysely table types/migration list
  config.ts                                                # validated embedding profile config
  search/embedding-client.ts                               # LM Studio OpenAI embeddings client
  search/search-document.ts                                # canonical text and SHA-256 hash
  search/hybrid-qdrant-store.ts                            # collection, aliases, upsert/query
  search/search-index-state.ts                             # source-position idempotency state
  search/search-indexer.ts                                 # JetStream consumer message handler
  search/search-indexer-main.ts                            # standalone process entry point
  search/search-service.ts                                 # query orchestration and degradation
  search/rebuild-semantic-search.ts                        # snapshot/catch-up/alias command
  api/search-routes.ts                                    # GET /api/search/fragments
  app.ts                                                   # route registration
  runtime.ts                                               # runtime search service construction
  events/{jetstream,topology}.ts                           # search consumer topology
  qdrant-projector.ts                                     # remove old payload-only process entry

apps/server/test/
  config.test.ts
  search-document.test.ts
  embedding-client.test.ts
  hybrid-qdrant-store.integration.test.ts
  search-indexer.test.ts
  search-routes.test.ts
  semantic-search-event.integration.test.ts

packages/api-contracts/src/
  search.ts                                                # public Zod request/response schemas
  index.ts                                                 # export search schemas
packages/api-contracts/test/public-contracts.test.ts

apps/web/src/
  components/SearchView.svelte                             # page layout and result cards
  components/{AppBar,EditorShell}.svelte                   # Search navigation/snippet
  app/ui-preferences.svelte.ts                              # view persistence
  app/search-model.svelte.ts                                # query state
  app/search-model.test.ts
  lib/api.ts                                               # typed search request
  domain/search-model.ts                                   # UI result/filter types

aspire-apphost/apphost.mts                                 # search-indexer and env wiring
apps/server/package.json                                   # search scripts
docs/architecture.md                                       # hybrid search runtime truth
README.md                                                  # local LM Studio setup and search lag
plans/phase-06-semantic-search/implementation-01-semantic-search.md
```

---

### Task 1: Define the Search Profile, Persistent State, and Public Contract

**Files:**
- Create: `apps/server/src/catalog/migrations/004-semantic-search.ts`
- Modify: `apps/server/src/catalog/{database-types,migrations/index}.ts`
- Modify: `apps/server/src/config.ts`
- Create: `packages/api-contracts/src/search.ts`
- Modify: `packages/api-contracts/src/index.ts`
- Modify: `packages/api-contracts/test/public-contracts.test.ts`
- Test: `apps/server/test/config.test.ts`

**Consumes:** the Phase 5 catalog schema and public-contract export pattern.

**Produces:** validated `EmbeddingProfile`, durable per-profile index state, and
typed `/api/search/fragments` request/response contracts.

- [ ] **Step 1: Add failing configuration tests**

```ts
expect(() =>
  getServerConfig({
    DATABASE_URL: 'postgres://catalog',
    CUT_ON_EIGHT_EMBEDDINGS_URL: 'ftp://localhost/v1',
  }),
).toThrow('embedding URL uses an unsupported protocol');

expect(
  getServerConfig({ DATABASE_URL: 'postgres://catalog' }).embeddingProfile,
).toEqual({
  id: 'embeddinggemma-v1',
  model: 'google/embeddinggemma-300M',
  dimensions: 768,
  baseUrl: null,
});
```

- [ ] **Step 2: Add the semantic-search migration and Kysely table types**

Create `semantic_search_index_state` keyed by `(profile_id, fragment_id)` with
`collection_name`, `fragment_revision`, `text_hash`, `status` (`pending`,
`ready`, `failed`), `last_event_id`, `last_source_position`, `failure_code`,
and timestamps. Create `semantic_search_rebuilds` with its UUID, profile,
target collection, snapshot high-water event position, status (`running`,
`ready`, `failed`), error text, and timestamps.

```sql
create table semantic_search_index_state (
  profile_id text not null,
  fragment_id uuid not null,
  collection_name text not null,
  fragment_revision integer not null,
  text_hash char(64) not null,
  status text not null check (status in ('pending', 'ready', 'failed')),
  last_event_id uuid,
  last_source_position bigint,
  failure_code text,
  updated_at timestamptz not null default now(),
  primary key (profile_id, fragment_id)
);

create index semantic_search_index_state_position_idx
  on semantic_search_index_state (profile_id, last_source_position);
```

Do not alter or delete `search_projection_state` in this slice; it is an
existing disposable derived-state record and must not endanger catalog data.

- [ ] **Step 3: Implement a validated `EmbeddingProfile` in `config.ts`**

```ts
export interface EmbeddingProfile {
  readonly id: string;
  readonly model: string;
  readonly dimensions: number;
  readonly baseUrl: string | null;
}

// CUT_ON_EIGHT_EMBEDDING_PROFILE defaults to embeddinggemma-v1.
// CUT_ON_EIGHT_EMBEDDING_MODEL defaults to google/embeddinggemma-300M.
// CUT_ON_EIGHT_EMBEDDING_DIMENSIONS defaults to 768.
// CUT_ON_EIGHT_EMBEDDINGS_URL is optional and must end in /v1.
```

Accept IDs matching `^[a-z0-9][a-z0-9-]{0,63}$`, positive dimensions at most
8192, and non-empty model names. Do not read an API key: the initial LM Studio
endpoint is local/private.

- [ ] **Step 4: Define and export the public search contract**

```ts
export const fragmentSearchQuerySchema = z.object({
  q: z.string().trim().min(1).max(500),
  tagIds: z.array(z.uuid()).max(20).default([]),
  collectionIds: z.array(z.uuid()).max(20).default([]),
  videoIds: z.array(z.uuid()).max(20).default([]),
  limit: z.coerce.number().int().min(1).max(50).default(20),
});

export const fragmentSearchResponseSchema = z.object({
  mode: z.enum(['hybrid', 'lexical']),
  indexing: z.object({ pending: z.number().int().nonnegative() }),
  results: z.array(fragmentSearchResultSchema),
});
```

`fragmentSearchResultSchema` contains the fragment ID, title, description,
tags, timing, source video ID/title, collections, score, and existing preview
metadata needed by a result card. It must not expose database state, storage
keys, local paths, or raw Qdrant payloads.

- [ ] **Step 5: Run focused checks**

Run: `pnpm -C cut_on_eight --filter @cut-on-eight/server test -- config.test.ts`

Expected: defaults and invalid profile input are covered.

Run: `pnpm -C cut_on_eight --filter @cut-on-eight/api-contracts test`

Expected: contracts compile and their public surface test passes.

- [ ] **Step 6: Commit the task**

```bash
git add apps/server/src/catalog apps/server/src/config.ts apps/server/test/config.test.ts packages/api-contracts
git commit -m "feat: define semantic search profile and contracts"
```

---

### Task 2: Build Canonical Documents and the LM Studio Embedding Boundary

**Files:**
- Create: `apps/server/src/search/search-document.ts`
- Create: `apps/server/src/search/embedding-client.ts`
- Create: `apps/server/test/search-document.test.ts`
- Create: `apps/server/test/embedding-client.test.ts`

**Consumes:** `EmbeddingProfile` and current fragment/video/tag catalog rows.

**Produces:** deterministic `SearchDocument` values and a small client that
returns only validated dense vectors.

- [ ] **Step 1: Write document-builder tests**

```ts
expect(buildSearchDocument(source)).toEqual({
  text: 'fragment title\nslow turn\nfoxtrot\nsource title\nlesson notes\nbronze',
  hash: '…sha256 of the exact UTF-8 text…',
});

expect(buildSearchDocument({ ...source, collectionTitles: ['ignored'] }).text)
  .not.toContain('ignored');
```

Use lowercase tags in lexical text, retain human-entered title/description
case, omit null/blank fields, separate fields with one newline, and never
include a collection’s metadata.

- [ ] **Step 2: Implement `SearchDocument` and current-state loading**

```ts
export interface SearchDocument {
  readonly text: string;
  readonly hash: string;
}

export function buildSearchDocument(input: SearchDocumentInput): SearchDocument;

export async function loadSearchDocument(
  database: Kysely<CatalogDatabase>,
  fragmentId: string,
): Promise<CurrentFragmentSearchDocument | null>;
```

`loadSearchDocument` must return `null` for missing, soft-deleted, or
source-video-deleting fragments. Its payload includes only the public fragment
search fields and keyword filter IDs.

- [ ] **Step 3: Write embedding-client tests with a local fake server**

```ts
await expect(client.embed(['a fragment'])).resolves.toEqual([[0.1, 0.2, 0.3]]);
await expect(client.embed(['a fragment'])).rejects.toThrow(
  'Embedding response vector has 3 dimensions; expected 768.',
);
```

The fake server must assert a `POST /v1/embeddings` request with
`{ model, input }`; test 502/non-JSON responses as retryable remote failures.

- [ ] **Step 4: Implement the client with one deep interface**

```ts
export interface EmbeddingClient {
  available(): boolean;
  embed(texts: readonly string[]): Promise<readonly number[][]>;
}

export function createEmbeddingClient(
  profile: EmbeddingProfile,
  resilientCall?: ResilientCall,
): EmbeddingClient;
```

When `baseUrl` is `null`, `available()` returns false and `embed()` throws a
typed `embedding_unavailable` error. Validate `data[].embedding` ordering,
finite numeric values, and exact configured dimensions before any Qdrant call.

- [ ] **Step 5: Run focused checks**

Run: `pnpm -C cut_on_eight --filter @cut-on-eight/server test -- search-document.test.ts embedding-client.test.ts`

Expected: canonical text/hash stability and LM Studio protocol validation pass.

- [ ] **Step 6: Commit the task**

```bash
git add apps/server/src/search/search-document.ts apps/server/src/search/embedding-client.ts apps/server/test
git commit -m "feat: add semantic search document and embedding client"
```

---

### Task 3: Replace the Payload-Only Projector with a Durable Hybrid Indexer

**Files:**
- Create: `apps/server/src/search/hybrid-qdrant-store.ts`
- Create: `apps/server/src/search/search-index-state.ts`
- Create: `apps/server/src/search/search-indexer.ts`
- Create: `apps/server/src/search/search-indexer-main.ts`
- Modify: `apps/server/src/events/{jetstream,topology}.ts`
- Modify: `apps/server/src/qdrant-projector.ts`
- Modify: `apps/server/package.json`
- Create: `apps/server/test/search-indexer.test.ts`
- Create: `apps/server/test/hybrid-qdrant-store.integration.test.ts`

**Consumes:** Task 1 profile/state, Task 2 document and embeddings, and Phase 5
JetStream event delivery.

**Produces:** the `search-indexer-v1` durable consumer, a versioned hybrid
collection, and safely retryable event processing.

- [ ] **Step 1: Write an indexer idempotency test**

```ts
await processSearchIndexMessage(dependencies, changedMessageAt(42));
await processSearchIndexMessage(dependencies, changedMessageAt(42));

expect(store.upsert).toHaveBeenCalledTimes(1);
expect(await indexState.position('embeddinggemma-v1', fragmentId)).toBe(42);
```

Also prove a later deletion calls `store.delete(fragmentId)` and is recorded
only after the delete succeeds; an unavailable embedding service must leave the
message unacknowledged and state non-ready.

- [ ] **Step 2: Implement the hybrid Qdrant store**

```ts
export interface HybridSearchStore {
  ensureCollection(target: SearchCollection): Promise<void>;
  upsert(input: IndexedFragment): Promise<void>;
  delete(collection: string, fragmentId: string): Promise<void>;
  query(input: HybridQuery): Promise<readonly RankedFragmentPoint[]>;
  setAlias(alias: string, collection: string): Promise<void>;
}
```

`ensureCollection` must create:

```json
{
  "vectors": { "semantic-v1": { "size": 768, "distance": "Cosine" } },
  "sparse_vectors": { "lexical-v1": { "modifier": "idf" } },
  "on_disk_payload": true
}
```

Create keyword indexes for `video_id`, `fragment_tag_ids`, `collection_ids`,
and `source_tag_ids`. Upsert the dense vector only when one is supplied, and
upsert the sparse document as `{ "text": searchText, "model": "qdrant/bm25" }`.

- [ ] **Step 3: Implement a per-profile source-position state store**

```ts
export async function isAlreadyApplied(
  database: Kysely<CatalogDatabase>,
  profileId: string,
  fragmentId: string,
  position: number,
): Promise<boolean>;

export async function recordApplied(input: AppliedSearchIndexState): Promise<void>;
```

Use an upsert guarded by `last_source_position < excluded.last_source_position`.
The state update happens only after Qdrant accepts the point/delete.

- [ ] **Step 4: Add `search-indexer-v1` topology and process entry point**

Add the explicit-ack pull consumer with filter
`cut_on_eight.fragment.>`, one pending message, a 60-second acknowledgement
window, and bounded retry backoff. Stop creating the old
`qdrant-projector-v1` consumer; leave its derived state/collection in place for
manual rollback, but remove the old AppHost process and package script.

`search-indexer-main.ts` must initialize topology, database, Qdrant store, and
embedding client, honour `SIGINT`/`SIGTERM`, and drain all connections on exit.

- [ ] **Step 5: Add the Qdrant integration test**

Run the test against Qdrant 1.18.3. It must create an `embeddinggemma-v1`
collection, insert two points with small deterministic dense vectors and BM25
documents, apply a tag filter, and assert an RRF response returns only the
filtered point. This proves the local `qdrant/bm25` path before application
code relies on it.

- [ ] **Step 6: Run focused checks**

Run: `pnpm -C cut_on_eight --filter @cut-on-eight/server test -- search-indexer.test.ts`

Expected: duplicate, stale, deletion, and unavailable-embedding delivery cases pass.

Run: `pnpm -C cut_on_eight --filter @cut-on-eight/server exec vitest run test/hybrid-qdrant-store.integration.test.ts`

Expected: Qdrant accepts hybrid points and filtered RRF queries.

- [ ] **Step 7: Commit the task**

```bash
git add apps/server/src/search apps/server/src/events apps/server/src/qdrant-projector.ts apps/server/package.json apps/server/test
git commit -m "feat: index fragments into hybrid qdrant search"
```

---

### Task 4: Expose Fragment Search with Graceful Lexical Degradation

**Files:**
- Create: `apps/server/src/search/search-service.ts`
- Create: `apps/server/src/api/search-routes.ts`
- Modify: `apps/server/src/runtime.ts`
- Modify: `apps/server/src/app.ts`
- Create: `apps/server/test/search-routes.test.ts`

**Consumes:** Task 1 public contract, Task 2 embedding client, and Task 3
hybrid query store.

**Produces:** `GET /api/search/fragments`, returning public result cards and
an explicit `hybrid` or `lexical` mode.

- [ ] **Step 1: Write route tests**

```ts
const response = await app.inject({
  method: 'GET',
  url: '/api/search/fragments?q=promenade&tagIds=' + tagId,
});

expect(response.statusCode).toBe(200);
expect(response.json()).toMatchObject({
  mode: 'hybrid',
  results: [expect.objectContaining({ fragmentId, sourceVideoId })],
});
```

With an unavailable embedding client, assert `mode: 'lexical'` and that the
same request still calls sparse Qdrant search. With Qdrant unavailable, assert
the existing problem-details envelope returns `503 search_unavailable`.

- [ ] **Step 2: Implement a focused query service**

```ts
export interface FragmentSearchService {
  search(query: FragmentSearchQuery): Promise<FragmentSearchResponse>;
}
```

For hybrid mode, request 50 dense and 50 lexical candidates under the exact
same Qdrant filter, then use server-side RRF and return at most `query.limit`.
For lexical mode, submit only the BM25 prefetch and query. The service maps
payloads to public contract DTOs and counts pending active-profile state rows
for the `indexing.pending` hint.

- [ ] **Step 3: Register the route and runtime dependency**

Add `registerSearchRoutes(app, runtime)` only to the catalog runtime branch.
Parse repeated query parameters as string arrays, validate with
`fragmentSearchQuerySchema`, and never pass raw request values to Qdrant.

- [ ] **Step 4: Run focused checks**

Run: `pnpm -C cut_on_eight --filter @cut-on-eight/server test -- search-routes.test.ts`

Expected: hybrid mode, lexical fallback, exact filter validation, and 503
failure mapping pass.

- [ ] **Step 5: Commit the task**

```bash
git add apps/server/src/api/search-routes.ts apps/server/src/search/search-service.ts apps/server/src/{app,runtime}.ts apps/server/test/search-routes.test.ts
git commit -m "feat: expose fragment search api"
```

---

### Task 5: Make Backfill, Alias Cutover, and Aspire Operation Explicit

**Files:**
- Create: `apps/server/src/search/rebuild-semantic-search.ts`
- Modify: `apps/server/package.json`
- Modify: `aspire-apphost/apphost.mts`
- Create: `apps/server/test/semantic-search-event.integration.test.ts`
- Modify: `scripts/integration.sh`

**Consumes:** the Task 3 hybrid indexer and `semantic_search_rebuilds` metadata.

**Produces:** a safe rebuild command, a standalone Aspire `search-indexer`
process, and end-to-end durable delivery proof.

- [ ] **Step 1: Write a rebuild-state test**

```ts
const run = await rebuildSemanticSearch(dependencies, 'embeddinggemma-v1');

expect(run.status).toBe('ready');
expect(await store.aliasTarget('cut_on_eight_fragments_active')).toBe(
  run.targetCollection,
);
expect(run.snapshotHighWaterPosition).toBeGreaterThanOrEqual(0);
```

Add a failure case where collection-count validation fails: alias remains on
the original collection and the rebuild row becomes `failed` with a safe error.

- [ ] **Step 2: Implement snapshot-plus-catch-up rebuild**

`search:rebuild --profile embeddinggemma-v1` must:

1. Create a unique target collection named
   `cut_on_eight_fragments_embeddinggemma-v1_v1_<run-id>`.
2. Read and persist the current maximum `integration_events.position`.
3. Index the current visible PostgreSQL fragment snapshot into that target.
4. Apply fragment events newer than the recorded position until caught up.
5. Require the target point count to equal the visible catalog fragment count.
6. Move `cut_on_eight_fragments_active` to the target using one Qdrant alias
   action only after all previous steps succeed.

On retry, create a fresh target and leave failed/old collections untouched.

- [ ] **Step 3: Wire Aspire without installing LM Studio**

Add `search-indexer` as a host JavaScript app with references to catalog,
Qdrant, and NATS. Pass through the four `CUT_ON_EIGHT_EMBEDDING_*` variables
unchanged; do not create a container, download a model, or publish an LM Studio
endpoint. Give API the same profile variables because it embeds queries.

- [ ] **Step 4: Extend the Docker integration suite**

The test must create a catalog fragment, append/publish a real
`fragment.changed.v1`, run `search-indexer` with an LM Studio-compatible fake
embedding endpoint, and poll Qdrant for the resulting point. Stop the fake
endpoint for one event, prove the message is retried, restore it, then verify
the updated point and state position converge.

- [ ] **Step 5: Run focused checks**

Run: `./scripts/integration.sh`

Expected: PostgreSQL -> outbox -> JetStream -> hybrid search indexer -> Qdrant
is proven, including one transient embedding outage.

- [ ] **Step 6: Commit the task**

```bash
git add apps/server/src/search/rebuild-semantic-search.ts apps/server/package.json aspire-apphost/apphost.mts apps/server/test/semantic-search-event.integration.test.ts scripts/integration.sh
git commit -m "feat: add semantic search rebuild and runtime"
```

---

### Task 6: Add the Small Fragment-First Search View

**Files:**
- Create: `apps/web/src/domain/search-model.ts`
- Create: `apps/web/src/app/search-model.svelte.ts`
- Create: `apps/web/src/app/search-model.test.ts`
- Create: `apps/web/src/components/SearchView.svelte`
- Modify: `apps/web/src/App.svelte`
- Modify: `apps/web/src/app/ui-preferences.svelte.ts`
- Modify: `apps/web/src/components/{AppBar,EditorShell}.svelte`
- Modify: `apps/web/src/lib/api.ts`

**Consumes:** Task 1 public search DTOs and Task 4 endpoint.

**Produces:** a top-level Search tab with a single text field, explicit filters,
result cards, source context, existing thumbnails, and an unobtrusive lag hint.

- [ ] **Step 1: Write search-model tests**

```ts
const model = createSearchModel(api);
model.setQuery('promenade');
await vi.advanceTimersByTimeAsync(200);

expect(api.searchFragments).toHaveBeenCalledWith({
  q: 'promenade', tagIds: [], collectionIds: [], videoIds: [], limit: 20,
});
```

Also assert blank input performs no request, replacing the query aborts the
previous request, and a lexical response displays the mode without treating it
as an error.

- [ ] **Step 2: Implement typed API and search model**

```ts
export interface SearchModel {
  query: string;
  filters: FragmentSearchFilters;
  response: FragmentSearchResponse | null;
  state: 'idle' | 'loading' | 'ready' | 'error';
  setQuery(value: string): void;
  setFilters(value: FragmentSearchFilters): void;
  dispose(): void;
}
```

Use a 200 ms debounce and `AbortController`; retain old results while a newer
request is loading. Keep filter controls collapsed until the user opens them.

- [ ] **Step 3: Implement the view and navigation**

Add `search` to `ActiveView`, its local-storage validation, `AppBar`, and
`EditorShell`. `SearchView` contains one labelled input, expandable exact
filters, and compact fragment cards showing title, source title, tags, timing,
and the existing preview strip. Display `Indexing N recent changes` only when
`indexing.pending > 0`; display `Lexical results while embeddings reconnect`
only for `mode: 'lexical'`.

Clicking a card opens its source video and selects the fragment through the
existing workspace/fragment flow. Do not invent a separate video player.

- [ ] **Step 4: Run focused web checks**

Run: `pnpm -C cut_on_eight --filter @cut-on-eight/web test -- search-model.test.ts`

Expected: debounce, cancellation, empty query, and lexical state behaviour pass.

Run: `pnpm -C cut_on_eight check:web`

Expected: Svelte and TypeScript checks pass.

- [ ] **Step 5: Commit the task**

```bash
git add apps/web/src
git commit -m "feat: add fragment search view"
```

---

### Task 7: Document the Operational Contract and Run the Full Gate

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `plans/phase-06-semantic-search/implementation-01-semantic-search.md`

**Consumes:** the completed runtime and UI.

**Produces:** accurate local setup instructions and a verified phase handoff.

- [ ] **Step 1: Document exact local embedding setup**

Add the required LM Studio model and server configuration:

```text
Model: google/embeddinggemma-300M
LM Studio server: OpenAI-compatible endpoint enabled on http://127.0.0.1:1234/v1
CUT_ON_EIGHT_EMBEDDINGS_URL=http://127.0.0.1:1234/v1
```

State that the app is lexical-only when the endpoint is omitted/unavailable and
that search can lag recent catalog edits while event processing catches up.

- [ ] **Step 2: Update the architecture truth**

Replace the payload-only Qdrant description with the active alias, named dense
and BM25 vectors, RRF, source-position idempotency, rebuild process, and the
fact that Qdrant/LM Studio failures never block catalog writes.

- [ ] **Step 3: Run all required verification**

Run: `./scripts/check.sh`

Expected: all TypeScript, Svelte, lint, and contract checks pass.

Run: `./scripts/test.sh`

Expected: unit and ordinary integration tests pass.

Run: `./scripts/integration.sh`

Expected: Docker-backed event, Qdrant, thumbnail, and semantic-search checks pass.

- [ ] **Step 4: Mark the plan implemented and commit**

Change `**Status:** Planned` to `**Status:** Implemented` at the top of this
file after all three commands succeed.

```bash
git add README.md docs/architecture.md plans/phase-06-semantic-search
git commit -m "docs: document semantic search"
```
