<script lang="ts">
  import type {
    DeletedFragment,
    FragmentCatalogue,
    FragmentMutation,
    FragmentSummary,
    TagDefinition,
  } from '../domain/catalogue-model.js';
  import type { Segment } from '../domain/editor-model.js';
  import { filterFragments, fragmentLabel } from '../lib/fragment-catalogue.js';
  import type { BoundaryFocus } from '../lib/trim-controller.js';
  import { onDestroy, onMount } from 'svelte';
  import { SvelteMap, SvelteSet } from 'svelte/reactivity';
  import FragmentEditor from './FragmentEditor.svelte';
  import FragmentPlayer from './FragmentPlayer.svelte';
  import FragmentPreviewStrip from './FragmentPreviewStrip.svelte';
  import UndoToast from './UndoToast.svelte';

  const FILTERS_KEY = 'cut-on-eight.fragment-filters';

  let {
    catalogue,
    loading,
    error,
    onRefresh,
    onUpdate,
    onCreateTag,
    onDelete,
    onRestore,
    onRetryThumbnail,
  }: {
    catalogue: FragmentCatalogue | null;
    loading: boolean;
    error: string | null;
    onRefresh: () => void;
    onUpdate: (
      projectId: string,
      segmentId: string,
      mutation: FragmentMutation,
    ) => Promise<Segment>;
    onCreateTag: (name: string) => Promise<TagDefinition>;
    onDelete: (
      projectId: string,
      segmentId: string,
    ) => Promise<DeletedFragment>;
    onRestore: (deleted: DeletedFragment) => Promise<void>;
    onRetryThumbnail: (jobId: string) => void;
  } = $props();

  let query = $state('');
  let projectId = $state<string | null>(null);
  const selectedTagIds = new SvelteSet<string>();
  let activeFragmentId = $state<string | null>(null);
  let editingFragmentId = $state<string | null>(null);
  let boundaryFocus = $state.raw<BoundaryFocus>(null);
  let mutationError = $state<string | null>(null);
  let deleted = $state<DeletedFragment | null>(null);
  let undoTimer: ReturnType<typeof setTimeout> | null = null;
  let visibleLimit = $state(100);
  const fragmentDrafts = new SvelteMap<string, Segment>();
  const fragmentWrites = new SvelteMap<string, Promise<void>>();

  onDestroy(() => {
    if (undoTimer !== null) clearTimeout(undoTimer);
  });

  onMount(() => {
    try {
      const stored = JSON.parse(
        localStorage.getItem(FILTERS_KEY) ?? 'null',
      ) as {
        query?: unknown;
        projectId?: unknown;
        tagIds?: unknown;
      } | null;
      if (typeof stored?.query === 'string') query = stored.query;
      if (typeof stored?.projectId === 'string') projectId = stored.projectId;
      if (Array.isArray(stored?.tagIds)) {
        for (const tagId of stored.tagIds) {
          if (typeof tagId === 'string') selectedTagIds.add(tagId);
        }
      }
    } catch {
      // Invalid browser preferences are ignored.
    }
  });

  const fragments = $derived(catalogue?.fragments ?? []);
  const visibleFragments = $derived(
    filterFragments(fragments, { query, projectId, tagIds: selectedTagIds }),
  );
  const activeFragment = $derived.by(() => {
    const fragment =
      fragments.find((item) => item.segment.id === activeFragmentId) ?? null;
    return fragment === null ? null : withDraft(fragment);
  });
  const videos = $derived.by(() => {
    return fragments
      .filter(
        (fragment, index, all) =>
          all.findIndex(
            (candidate) => candidate.projectId === fragment.projectId,
          ) === index,
      )
      .map((fragment) => ({
        id: fragment.projectId,
        name: fragment.sourceFileName,
      }));
  });

  function toggleTag(tagId: string): void {
    if (selectedTagIds.has(tagId)) selectedTagIds.delete(tagId);
    else selectedTagIds.add(tagId);
    visibleLimit = 100;
    storeFilters();
  }

  function storeFilters(): void {
    try {
      localStorage.setItem(
        FILTERS_KEY,
        JSON.stringify({ query, projectId, tagIds: [...selectedTagIds] }),
      );
    } catch {
      // Filtering remains available when browser storage is unavailable.
    }
  }

  function withDraft(fragment: FragmentSummary): FragmentSummary {
    return {
      ...fragment,
      segment: fragmentDrafts.get(fragment.segment.id) ?? fragment.segment,
    };
  }

  function clearUndo(): void {
    if (undoTimer !== null) clearTimeout(undoTimer);
    undoTimer = null;
    deleted = null;
  }

  function refresh(): void {
    clearUndo();
    onRefresh();
  }

  async function mutate(
    fragment: FragmentSummary,
    change: Partial<FragmentMutation>,
  ): Promise<void> {
    mutationError = null;
    const base = fragmentDrafts.get(fragment.segment.id) ?? fragment.segment;
    const mutation: FragmentMutation = {
      startSeconds: base.startSeconds,
      endSeconds: base.endSeconds,
      title: base.title,
      tagIds: base.tagIds,
      exportSelected: base.exportSelected,
      ...change,
    };
    fragmentDrafts.set(fragment.segment.id, { ...base, ...mutation });
    const previous =
      fragmentWrites.get(fragment.segment.id) ?? Promise.resolve();
    let write: Promise<void>;
    write = previous
      .catch(() => undefined)
      .then(async () => {
        await onUpdate(fragment.projectId, fragment.segment.id, mutation);
        if (fragmentWrites.get(fragment.segment.id) === write) {
          fragmentDrafts.delete(fragment.segment.id);
        }
      });
    fragmentWrites.set(fragment.segment.id, write);
    try {
      await write;
      if (fragmentWrites.get(fragment.segment.id) === write) {
        mutationError = null;
      }
    } catch (nextError) {
      mutationError =
        nextError instanceof Error
          ? nextError.message
          : 'Fragment update failed.';
      if (fragmentWrites.get(fragment.segment.id) === write) {
        fragmentDrafts.delete(fragment.segment.id);
        refresh();
      }
    } finally {
      if (fragmentWrites.get(fragment.segment.id) === write) {
        fragmentWrites.delete(fragment.segment.id);
      }
    }
  }

  async function remove(fragment: FragmentSummary): Promise<void> {
    mutationError = null;
    try {
      deleted = await onDelete(fragment.projectId, fragment.segment.id);
      if (undoTimer !== null) clearTimeout(undoTimer);
      undoTimer = setTimeout(
        () => {
          deleted = null;
          undoTimer = null;
        },
        Math.max(0, Date.parse(deleted.undoUntil) - Date.now()),
      );
      if (activeFragmentId === fragment.segment.id) activeFragmentId = null;
      if (editingFragmentId === fragment.segment.id) editingFragmentId = null;
    } catch (nextError) {
      mutationError =
        nextError instanceof Error
          ? nextError.message
          : 'Fragment deletion failed.';
      onRefresh();
    }
  }

  async function undo(): Promise<void> {
    if (deleted === null) return;
    const snapshot = deleted;
    try {
      await onRestore(snapshot);
      if (undoTimer !== null) clearTimeout(undoTimer);
      undoTimer = null;
      deleted = null;
    } catch (nextError) {
      mutationError =
        nextError instanceof Error
          ? nextError.message
          : 'Fragment could not be restored.';
    }
  }
</script>

<section class="fragments-panel" aria-labelledby="fragments-title">
  <div class="panel-heading">
    <div>
      <h1 id="fragments-title">Fragments</h1>
      <p>All videos · {fragments.length} fragments</p>
    </div>
    <button
      class="secondary-action"
      type="button"
      disabled={loading}
      onclick={refresh}>Refresh</button
    >
  </div>

  <div class="fragment-filters">
    <input
      value={query}
      oninput={(event) => {
        query = event.currentTarget.value;
        visibleLimit = 100;
        storeFilters();
      }}
      type="search"
      placeholder="Search title or video"
      aria-label="Search fragments"
    />
    <select
      value={projectId ?? ''}
      onchange={(event) => {
        projectId = event.currentTarget.value || null;
        visibleLimit = 100;
        storeFilters();
      }}
      aria-label="Filter by video"
    >
      <option value="">All videos</option>
      {#each videos as video (video.id)}<option value={video.id}
          >{video.name}</option
        >{/each}
    </select>
    <div class="filter-tags" aria-label="Filter by tags">
      {#each catalogue?.tags ?? [] as tag (tag.id)}
        <button
          type="button"
          aria-pressed={selectedTagIds.has(tag.id)}
          onclick={() => toggleTag(tag.id)}>{tag.name}</button
        >
      {/each}
    </div>
  </div>

  {#if mutationError !== null}<p class="error-text" role="alert">
      {mutationError}
    </p>{/if}

  {#if loading}<p class="empty-copy">Loading fragments…</p>
  {:else if error !== null}<p class="error-text">{error}</p>
  {:else if visibleFragments.length === 0}<p class="empty-copy">
      No fragments match these filters.
    </p>
  {:else}
    <div class="fragment-grid">
      {#each visibleFragments.slice(0, visibleLimit) as sourceFragment (sourceFragment.segment.id)}
        {@const fragment = withDraft(sourceFragment)}
        <article
          class={activeFragmentId === fragment.segment.id
            ? 'active-fragment'
            : undefined}
        >
          <FragmentPreviewStrip previews={fragment.previews} />
          {#if fragment.thumbnailState !== 'ready'}
            <p class="thumbnail-status">
              Thumbnails: {fragment.thumbnailState}
            </p>
          {/if}
          <div class="fragment-card-copy">
            <h2>{fragmentLabel(fragment)}</h2>
            <p>
              {fragment.sourceFileName} · {fragment.segment.startSeconds.toFixed(
                2,
              )}–{fragment.segment.endSeconds.toFixed(2)}s
            </p>
            <div class="tag-chips">
              {#each catalogue?.tags.filter( (tag) => fragment.segment.tagIds.includes(tag.id) ) ?? [] as tag (tag.id)}
                <span class="tag-chip">{tag.name}</span>
              {/each}
            </div>
          </div>
          <div class="fragment-card-actions">
            <button
              class="primary-action"
              type="button"
              onclick={() => (activeFragmentId = fragment.segment.id)}
              >Play</button
            >
            <button
              class="secondary-action"
              type="button"
              onclick={() => {
                editingFragmentId =
                  editingFragmentId === fragment.segment.id
                    ? null
                    : fragment.segment.id;
                boundaryFocus = null;
              }}>Edit</button
            >
            <button
              class="danger-action"
              type="button"
              onclick={() => void remove(fragment)}>Delete</button
            >
            {#if fragment.thumbnailState === 'failed' && fragment.thumbnailJobId !== null}
              <button
                class="secondary-action"
                type="button"
                onclick={() => onRetryThumbnail(fragment.thumbnailJobId!)}
                >Retry thumbnails</button
              >
            {/if}
          </div>
          {#if editingFragmentId === fragment.segment.id}
            <FragmentEditor
              segment={fragment.segment}
              tags={catalogue?.tags ?? []}
              focus={boundaryFocus}
              frameSeconds={fragment.frameStepSeconds}
              approximate={fragment.frameStepApproximate}
              error={mutationError}
              onFocus={(edge) =>
                (boundaryFocus = { segmentId: fragment.segment.id, edge })}
              onNudge={(delta) =>
                void mutate(
                  fragment,
                  boundaryFocus?.edge === 'start'
                    ? { startSeconds: fragment.segment.startSeconds + delta }
                    : { endSeconds: fragment.segment.endSeconds + delta },
                )}
              onMetadataChange={(change) => void mutate(fragment, change)}
              {onCreateTag}
            />
          {/if}
        </article>
      {/each}
    </div>
    {#if visibleFragments.length > visibleLimit}
      <button
        class="secondary-action show-more-fragments"
        type="button"
        onclick={() => (visibleLimit += 100)}>Show 100 more</button
      >
    {/if}
  {/if}

  {#each catalogue?.diagnostics ?? [] as diagnostic (diagnostic.projectId)}
    <p class="connection-warning">
      {diagnostic.sourceFileName}: {diagnostic.message}
    </p>
  {/each}
</section>

<FragmentPlayer
  fragment={activeFragment}
  onClose={() => (activeFragmentId = null)}
/>
<UndoToast
  visible={deleted !== null}
  message={mutationError ?? 'Fragment deleted'}
  onUndo={() => void undo()}
  onDismiss={clearUndo}
/>
