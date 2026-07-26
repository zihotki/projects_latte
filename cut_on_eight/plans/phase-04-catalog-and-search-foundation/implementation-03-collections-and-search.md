# Collections and Search Implementation Plan

**Status:** Ready

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add ordered multi-membership collections, fragment-first PostgreSQL search, top-level Collections and Search UX, and a rebuildable payload-only Qdrant projection.

**Architecture:** Collection and search capabilities are vertical server modules with public DTOs and focused Svelte models/views. `PostgresSearchProvider` is the only user-facing search implementation in Phase 4. Qdrant is asynchronously projected through `pg-boss`; its availability never blocks editing or PostgreSQL search.

**Tech Stack:** Slice 2 stack plus PostgreSQL relational search, `@qdrant/js-client-rest`, Cockatiel-wrapped Qdrant calls, Svelte 5.

**Depends on:** [Slice 2 — Video and Fragment Vertical Slice](implementation-02-video-and-fragment-vertical-slice.md)

## Global Constraints

- Keep changes inside `projectslatte/cut_on_eight`; preserve both `AGENTS.md` files.
- Fragments are the default search scope and dominant result presentation.
- Collections are explicit ordered sets, not saved searches.
- A fragment may belong to many collections. Separate collection-item IDs allow
  the same fragment to appear more than once.
- Do not impose a collection-size limit. Design and test comfortably for
  roughly 1–100 items.
- Reordering uses buttons/keyboard/direct position and never requires drag and
  drop.
- Fragment editing remains an explicit navigation into the source editor.
- PostgreSQL search must remain available when Qdrant is missing, unhealthy, or
  rebuilding.
- Do not generate placeholder embeddings or query Qdrant for user-facing
  relevance in this slice.
- Add one feature-level collection/search test, one small reorder unit test,
  and one real Qdrant smoke; avoid testing framework/database internals.

## File Map

```text
packages/api-contracts/src/{collections,search}.ts

apps/server/src/
  catalog/migrations/002-collections-and-search.ts
  collections/{collection-repository,collection-service,reorder}.ts
  search/
    search-provider.ts
    postgres-search-provider.ts
    qdrant-client.ts
    fragment-projector.ts
    rebuild.ts
  api/{collection-routes,search-routes}.ts
  jobs/processors/project-fragment.ts

apps/web/src/
  app/{collection-library,search}.svelte.ts
  components/
    CollectionView.svelte
    CollectionList.svelte
    CollectionEditor.svelte
    SearchView.svelte
    SearchFilters.svelte
    FragmentSearchResult.svelte
```

---

### Task 1: Add Collection and Search Schema Contracts

**Files:**
- Create: `packages/api-contracts/src/collections.ts`
- Create: `packages/api-contracts/src/search.ts`
- Modify: `packages/api-contracts/src/index.ts`
- Modify: `packages/api-contracts/test/public-contracts.test.ts`
- Create: `apps/server/src/catalog/migrations/002-collections-and-search.ts`
- Modify: `apps/server/src/catalog/migrations/index.ts`
- Modify: `apps/server/src/catalog/database-types.ts`

**Interfaces:**
- Public collection summary/detail/mutation schemas.
- Public search query/result schemas.
- PostgreSQL collection membership and projection-state records.

- [ ] **Step 1: Define collection DTOs**

```ts
export interface CollectionSummaryDto {
  id: string;
  title: string;
  description: string | null;
  tags: TagDto[];
  itemCount: number;
  revision: number;
}

export interface CollectionItemDto {
  id: string;
  position: number;
  fragment: FragmentDto;
  source: VideoSummaryDto;
}

export interface CollectionDto extends CollectionSummaryDto {
  items: CollectionItemDto[];
}
```

Add strict schemas for:

```ts
createCollectionRequestSchema = {
  title: trimmed 1..240,
  description: trimmed nullable max 4_000,
  tagIds: unique entity IDs
}

patchCollectionRequestSchema = {
  expectedRevision,
  title,
  description,
  tagIds
}

addCollectionItemRequestSchema = {
  expectedRevision,
  fragmentId,
  position: non-negative integer nullable
}

reorderCollectionItemsRequestSchema = {
  expectedRevision,
  itemIds: unique entity IDs
}
```

No schema caps the number of collection items.

- [ ] **Step 2: Define fragment-first search DTOs**

```ts
export const searchScopeSchema = z.enum(['fragments', 'videos']);

export const searchRequestSchema = z.strictObject({
  query: z.string().trim().max(200).default(''),
  scope: searchScopeSchema.default('fragments'),
  tagIds: z.array(entityIdSchema).default([]),
  collectionId: entityIdSchema.nullable().default(null),
  videoId: entityIdSchema.nullable().default(null),
  offset: z.number().int().nonnegative().default(0),
  limit: z.number().int().min(1).max(100).default(50),
});

export interface FragmentSearchResultDto {
  kind: 'fragment';
  fragment: FragmentDto;
  source: VideoSummaryDto;
  collectionIds: string[];
}

export interface VideoSearchResultDto {
  kind: 'video';
  video: VideoSummaryDto;
  fragmentCount: number;
}

export interface SearchResponseDto {
  scope: 'fragments' | 'videos';
  offset: number;
  limit: number;
  total: number;
  items: Array<FragmentSearchResultDto | VideoSearchResultDto>;
}
```

The discriminated response schema must reject a fragment result without source
context.

- [ ] **Step 3: Add the relational migration**

Create:

- `collections`
- `collection_tags`
- `collection_items`
- `search_projection_state`

Important constraints:

```sql
collections.revision >= 1
collection_items.position >= 0
UNIQUE (collection_id, position)
-- Deliberately no UNIQUE(collection_id, fragment_id)

search_projection_state.status IN ('pending', 'ready', 'failed')
search_projection_state.projection_revision >= 1
search_projection_state.projection_version >= 1
```

`collection_items.fragment_id` cascades on permanent fragment deletion.
`collection_tags` cascades on collection deletion. Add indexes for
`fragment_id`, tag filters, source video, and collection position.

- [ ] **Step 4: Run contract and migration checks**

```bash
pnpm -C cut_on_eight test:contracts
pnpm -C cut_on_eight db:migrate
pnpm -C cut_on_eight --filter @cut-on-eight/server check
```

Expected: public schemas pass and migration `002` applies once.

- [ ] **Step 5: Commit schemas**

```bash
git add cut_on_eight/packages/api-contracts cut_on_eight/apps/server/src/catalog
git commit -m "feat: define collection and search schemas"
```

---

### Task 2: Implement Ordered Collections

**Files:**
- Create: `apps/server/src/collections/reorder.ts`
- Create: `apps/server/src/collections/collection-repository.ts`
- Create: `apps/server/src/collections/collection-service.ts`
- Create: `apps/server/src/api/collection-routes.ts`
- Create: `apps/server/test/reorder.test.ts`
- Create: `apps/server/test/collection-search-api.test.ts`
- Modify: `apps/server/src/runtime.ts`
- Modify: `apps/server/src/app.ts`
- Modify: `apps/server/src/api/public-mappers.ts`

**Interfaces:**
- `GET /api/collections`
- `POST /api/collections`
- `GET /api/collections/:collectionId`
- `PATCH /api/collections/:collectionId`
- `DELETE /api/collections/:collectionId`
- `POST /api/collections/:collectionId/items`
- `DELETE /api/collections/:collectionId/items/:itemId`
- `PUT /api/collections/:collectionId/items/order`

- [ ] **Step 1: Implement one pure reorder invariant**

```ts
export function reorderItems(
  existingIds: readonly string[],
  requestedIds: readonly string[],
): Array<{ id: string; position: number }> {
  if (
    existingIds.length !== requestedIds.length ||
    new Set(requestedIds).size !== requestedIds.length ||
    requestedIds.some((id) => !existingIds.includes(id))
  ) {
    throw new DomainValidationError('Collection order is not a permutation');
  }
  return requestedIds.map((id, position) => ({ id, position }));
}
```

Test valid reordering, missing item, duplicate item, and foreign item in one
small table-driven test.

- [ ] **Step 2: Implement transactional collection commands**

For every mutation:

- lock the collection;
- compare the expected revision;
- verify referenced tags/fragments are visible;
- update membership/positions and increment revision once;
- return a fresh `CollectionDto`.

Adding at `null` position appends. Adding at a numeric position shifts following
items. Adding the same fragment twice creates two distinct item IDs.

Removing an item compacts positions. Reordering rewrites the small list in one
transaction using a temporary negative position pass, then final contiguous
positions, avoiding the unique-position constraint.

Deleting a collection removes its memberships and tags only; it never deletes
fragments.

- [ ] **Step 3: Map collection failures**

Use public Problem Details:

| Failure | Status | Code |
| --- | ---: | --- |
| stale revision | 409 | `stale_revision` |
| invalid item permutation/position | 422 | `invalid_collection_order` |
| hidden/missing fragment | 404 | `fragment_not_found` |
| missing collection/item | 404 | `collection_item_not_found` |

- [ ] **Step 4: Extend the feature test through the API**

In `collection-search-api.test.ts`:

- create two fragments;
- create a tagged collection;
- add one fragment twice and another once;
- verify positions `0, 1, 2`;
- reorder and direct-position the items;
- reject stale revision and invalid permutation;
- remove one duplicate without deleting its fragment;
- delete the collection and confirm fragments remain.

```bash
test -n "$CUT_ON_EIGHT_TEST_DATABASE_URL"
pnpm -C cut_on_eight test:server -- reorder.test.ts collection-search-api.test.ts
```

- [ ] **Step 5: Commit collection behavior**

```bash
git add cut_on_eight/apps/server/src/collections cut_on_eight/apps/server/src/api/collection-routes.ts cut_on_eight/apps/server/src/api/public-mappers.ts cut_on_eight/apps/server/src/runtime.ts cut_on_eight/apps/server/src/app.ts cut_on_eight/apps/server/test/reorder.test.ts cut_on_eight/apps/server/test/collection-search-api.test.ts
git commit -m "feat: add ordered fragment collections"
```

---

### Task 3: Implement PostgreSQL Search

**Files:**
- Create: `apps/server/src/search/search-provider.ts`
- Create: `apps/server/src/search/postgres-search-provider.ts`
- Create: `apps/server/src/api/search-routes.ts`
- Modify: `apps/server/src/runtime.ts`
- Modify: `apps/server/src/app.ts`
- Modify: `apps/server/test/collection-search-api.test.ts`

**Interfaces:**
- `GET /api/search`
- `SearchProvider.search(request): Promise<SearchResponseDto>`
- Default implementation: `PostgresSearchProvider`.

- [ ] **Step 1: Define a stable provider boundary**

```ts
export interface SearchProvider {
  search(request: SearchRequest): Promise<SearchResponseDto>;
}
```

Routes parse repeated `tagId` query-string values deliberately rather than
relying on implicit Fastify coercion.

Convert this to `searchRequestSchema` before invoking the provider.

- [ ] **Step 2: Implement fragment search in PostgreSQL**

Search visible, non-deleting records and match case-insensitively across:

- fragment title and description;
- fragment tag names;
- source-video title, description, and tag names.
- the selected collection's title and tag names when `collectionId` is active.

Apply optional tag, collection, and source-video filters. Use parameterized SQL
and escape `%`, `_`, and `\` before an `ILIKE ... ESCAPE '\'` pattern. An empty
query returns recently updated fragments under the active filters.

Order deterministically:

1. exact fragment-title match;
2. fragment-title prefix;
3. fragment-title substring;
4. other matched fields;
5. `fragments.updated_at DESC`;
6. fragment ID.

Compute `total` and the paged rows from the same filtered CTE. Fetch tags,
preview, source, and collection IDs without N+1 queries.

- [ ] **Step 3: Implement optional video scope**

Video scope matches video title, description, and tags. It returns video
summaries plus visible fragment counts. Collection and source-video filters are
valid only for fragment scope; reject invalid combinations with
`422 invalid_search_filter`.

- [ ] **Step 4: Instrument search without sensitive attributes**

Create a `fragment.search` span and record:

- scope;
- whether query is empty;
- result count bucket;
- filter count;
- duration.

Do not record query text, titles, descriptions, or tags.

- [ ] **Step 5: Complete the feature-level API test**

Seed mixed-case fragment/video titles, descriptions, and lowercase tags. Verify:

- default scope is fragments;
- matching is case-insensitive across all specified fields;
- source context is always present for fragment results;
- tag/collection/video filters compose;
- video scope returns videos;
- paging is stable;
- deleted fragments and deleting videos never appear.

```bash
test -n "$CUT_ON_EIGHT_TEST_DATABASE_URL"
pnpm -C cut_on_eight test:server -- collection-search-api.test.ts
```

- [ ] **Step 6: Commit PostgreSQL search**

```bash
git add cut_on_eight/apps/server/src/search/search-provider.ts cut_on_eight/apps/server/src/search/postgres-search-provider.ts cut_on_eight/apps/server/src/api/search-routes.ts cut_on_eight/apps/server/src/runtime.ts cut_on_eight/apps/server/src/app.ts cut_on_eight/apps/server/test/collection-search-api.test.ts
git commit -m "feat: add fragment-first PostgreSQL search"
```

---

### Task 4: Add Top-Level Collections and Search UX

**Files:**
- Create: `apps/web/src/app/collection-library.svelte.ts`
- Create: `apps/web/src/app/search.svelte.ts`
- Create: `apps/web/src/app/collection-library.test.ts`
- Create: `apps/web/src/app/search.test.ts`
- Create: `apps/web/src/components/CollectionView.svelte`
- Create: `apps/web/src/components/CollectionList.svelte`
- Create: `apps/web/src/components/CollectionEditor.svelte`
- Create: `apps/web/src/components/SearchView.svelte`
- Create: `apps/web/src/components/SearchFilters.svelte`
- Create: `apps/web/src/components/FragmentSearchResult.svelte`
- Modify: `apps/web/src/components/EditorShell.svelte`
- Modify: `apps/web/src/components/AppBar.svelte`
- Modify: `apps/web/src/components/FragmentsPanel.svelte`
- Modify: `apps/web/src/App.svelte`
- Modify: `apps/web/src/app/app-model.svelte.ts`
- Modify: `apps/web/src/app/ui-preferences.svelte.ts`
- Modify: `apps/web/src/lib/api.ts`
- Modify: `apps/web/src/app.css`

**Interfaces:**
- `ActiveView = 'editor' | 'fragments' | 'collections' | 'search' | 'library'`
- `CollectionLibrary` owns collection loading and mutations.
- `SearchModel` owns request, filters, results, loading, and errors.

- [ ] **Step 1: Add focused API clients and state models**

```ts
export class SearchModel {
  query = $state('');
  scope = $state<SearchScope>('fragments');
  filters = $state<SearchFilters>(emptySearchFilters());
  response = $state.raw<SearchResponseDto | null>(null);
  loading = $state(false);
  error = $state<string | null>(null);

  search(): Promise<void>;
  setScope(scope: SearchScope): void;
  clearFilters(): void;
  dispose(): void;
}
```

Use request revisions so slow responses cannot replace newer results. Search on
explicit submit and on filter/scope change; do not issue a request on every
keystroke.

`CollectionLibrary` exposes create/update/delete, add/remove item, move
up/down, and direct-position commands. It updates from server-returned DTOs and
does not implement a parallel ordering algorithm.

- [ ] **Step 2: Make both concepts top-level**

Order navigation:

```text
Editor | Fragments | Collections | Search | Library
```

Library remains standalone. Keep the content-first density and existing
central help popover; add a short Search/Collections mode section there rather
than per-control help bubbles.

- [ ] **Step 3: Build the Collections view**

The view provides:

- compact collection list;
- inline title/description/tag editor using the same click/keyboard style as
  fragment metadata/timing editors;
- selected collection's ordered items with five-frame previews and source
  context;
- inline fragment playback;
- Move up, Move down, and numeric position controls;
- Remove item without deleting fragment;
- explicit “Edit in source” navigation;
- collection delete confirmation.

No drag handle is required. Disable impossible move buttons.

- [ ] **Step 4: Add “Add to collection” actions**

Fragments and Search results open a compact collection picker. Selecting a
collection appends by default and returns visible success state. Do not hide an
already-used collection because duplicates are technically valid.

- [ ] **Step 5: Build the fragment-first Search view**

Initial state:

- empty query;
- Fragments selected;
- no filters;
- recent fragments visible after first explicit Search or entering the view.

Show query, a two-option Fragments/Videos scope switch, and a collapsible filter
panel for tags, collection, and source video. Fragment cards emphasize preview,
title, timing, and tags; source video is a compact linked context line.

Clicking a fragment selects it for inline playback. “Edit in source” opens and
activates the source video, selects the fragment, and moves to Editor without
starting playback automatically.

- [ ] **Step 6: Test state, then validate Svelte**

State tests cover only stale-response suppression, default fragment scope,
filter reset, duplicate collection add, and reorder response application.

```bash
pnpm -C cut_on_eight test:web -- src/app/collection-library.test.ts src/app/search.test.ts
pnpm -C cut_on_eight svelte:fix apps/web/src/components/CollectionView.svelte --svelte-version 5
pnpm -C cut_on_eight svelte:fix apps/web/src/components/SearchView.svelte --svelte-version 5
pnpm -C cut_on_eight check:web
```

- [ ] **Step 7: Commit collection and search UX**

```bash
git add cut_on_eight/apps/web
git commit -m "feat: add collections and top-level search"
```

---

### Task 5: Add the Payload-Only Qdrant Projection

**Files:**
- Create: `apps/server/src/search/qdrant-client.ts`
- Create: `apps/server/src/search/fragment-projector.ts`
- Create: `apps/server/src/search/rebuild.ts`
- Create: `apps/server/src/jobs/processors/project-fragment.ts`
- Create: `apps/server/test/qdrant-smoke.test.ts`
- Modify: `apps/server/src/jobs/worker-runtime.ts`
- Modify: video, fragment, and collection transaction services
- Modify: `apps/server/package.json`
- Modify: root `package.json`

**Interfaces:**
- Qdrant collection: `cut_on_eight_fragments_v1`
- Point ID: fragment UUID.
- `pnpm -C cut_on_eight search:rebuild`
- `pnpm -C cut_on_eight search:smoke`

- [ ] **Step 1: Create a Qdrant client behind Cockatiel**

```ts
export interface FragmentProjectionStore {
  ensureCollection(): Promise<void>;
  upsert(point: FragmentProjection): Promise<void>;
  delete(fragmentId: string): Promise<void>;
  replaceAll(points: AsyncIterable<FragmentProjection>): Promise<number>;
  count(): Promise<number>;
}
```

Configure from `QDRANT_HTTPURI` and optional `QDRANT_APIKEY`. If the URL is
absent, construct a disabled store that reports degraded health and throws one
classified unavailable error only when projection work is attempted.

The real store creates:

```ts
await client.createCollection(collectionName, {
  vectors: {},
  on_disk_payload: true,
});
```

Points omit `vector` entirely. Qdrant supports such payload-only points; they
are filterable/scrollable but cannot appear in nearest-neighbor search.

- [ ] **Step 2: Define a versioned projection payload**

```ts
export const projectionVersion = 1;

export interface FragmentProjection {
  id: string;
  payload: {
    projection_version: 1;
    projection_revision: number;
    fragment_id: string;
    video_id: string;
    start_us: number;
    end_us: number;
    fragment_title: string | null;
    fragment_description: string | null;
    fragment_tags: string[];
    source_title: string;
    source_description: string | null;
    source_tags: string[];
    collection_ids: string[];
  };
}
```

No absolute paths, checksums, errors, or private notes enter Qdrant.

- [ ] **Step 3: Mark and enqueue projections transactionally**

Create one helper:

```ts
export async function markFragmentProjectionPending(
  trx: Transaction<CatalogDatabase>,
  boss: PgBoss,
  fragmentId: string,
): Promise<number>;
```

It increments the fragment's independent `projection_revision`, sets state
`pending`, and enqueues `fragment.project.v1` with the expected projection
revision through `fromKysely(trx)`.

Invoke it after:

- fragment title/description/tags/timing changes;
- source video title/description/tags changes for every visible fragment;
- collection add/remove/delete only for affected distinct fragments;
- fragment restore;
- fragment deletion, so the projector removes the point.

- [ ] **Step 4: Implement idempotent projection work**

The handler loads the complete projection from PostgreSQL. If the fragment is
missing/deleted or its video is deleting, delete the Qdrant point. Otherwise
upsert `{ id, payload }` with `wait: true`.

After the remote call, update `search_projection_state` to `ready` only when the
expected projection revision still matches. On failure, store a stable
server-only error code, mark failed, and rethrow for `pg-boss`. Qdrant calls use
the Slice 1 remote-call policy; the job handler itself gets no extra retry loop.

- [ ] **Step 5: Implement a full rebuild command**

`search:rebuild`:

1. Reads PostgreSQL as authority.
2. Recreates `cut_on_eight_fragments_v1` with `vectors: {}`.
3. Streams visible fragments in batches of 100.
4. Upserts payload-only points.
5. Compares Qdrant exact count to PostgreSQL visible fragment count.
6. Marks corresponding projection states ready.
7. Exits non-zero on a mismatch.

PostgreSQL search remains untouched during rebuild.

- [ ] **Step 6: Add one real Qdrant smoke**

Against the Aspire Qdrant resource:

- create two catalog fragments;
- project both and verify payload through scroll;
- delete one fragment and verify point deletion;
- deliberately clear the collection;
- rebuild and verify exact point count and payload version.

```bash
test -n "$QDRANT_HTTPURI"
test -n "$CUT_ON_EIGHT_TEST_DATABASE_URL"
pnpm -C cut_on_eight search:smoke
```

Do not mock the Qdrant client.

- [ ] **Step 7: Commit Qdrant projection**

```bash
git add cut_on_eight/apps/server/src/search cut_on_eight/apps/server/src/jobs cut_on_eight/apps/server/src/videos cut_on_eight/apps/server/src/fragments cut_on_eight/apps/server/src/collections cut_on_eight/apps/server/test/qdrant-smoke.test.ts cut_on_eight/apps/server/package.json cut_on_eight/package.json
git commit -m "feat: project fragment catalog to Qdrant"
```

---

### Task 6: Run the Slice 3 Checkpoint

**Files:**
- Modify as needed only to fix checkpoint defects.

- [ ] **Step 1: Run automated verification**

```bash
pnpm -C cut_on_eight verify
```

With the AppHost resources available:

```bash
pnpm -C cut_on_eight search:smoke
```

- [ ] **Step 2: Run a bounded manual UX check**

Under `pnpm -C cut_on_eight dev`:

1. Create two collections and edit title/description/lowercase tags.
2. Add one fragment to both; add it twice to one collection.
3. Move items using buttons and direct position; restart and confirm order.
4. Play a collection item inline, then explicitly open it in the source editor.
5. Search a mixed-case title/tag/source term; verify fragment results and
   linked source context.
6. Apply tag, collection, and source-video filters.
7. Switch to Videos scope and back; Fragments remains the initial default on a
   fresh session.
8. Stop Qdrant; verify editing and PostgreSQL search still work and readiness
   reports degraded enhancement.
9. Restart Qdrant and run rebuild; verify projection count.

- [ ] **Step 3: Commit checkpoint fixes**

```bash
git add cut_on_eight
git commit -m "fix: complete collections and search checkpoint"
```

Skip this commit when the checkpoint required no changes.

## Slice 3 Exit Criteria

- Collections have metadata, tags, durable order, multi-membership, and
  technically duplicated fragment items.
- Search is top-level, fragment-first, case-insensitive, filterable, and shows
  source context.
- Collection and search results play inline and navigate explicitly to editing.
- Qdrant stores one rebuildable payload-only point per visible fragment.
- Qdrant failure does not block catalog writes or PostgreSQL search.
