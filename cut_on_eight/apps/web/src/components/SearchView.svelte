<script lang="ts">
  import type { FragmentSearchResultDto } from '@cut-on-eight/api-contracts';
  import type { SearchModel } from '../app/search-model.svelte.js';
  import {
    searchResultLabel,
    searchResultPreviews,
  } from '../domain/search-model.js';
  import type { TagDefinition } from '../domain/catalogue-model.js';
  import type { ProjectSummary } from '../domain/editor-model.js';
  import FragmentPreviewStrip from './FragmentPreviewStrip.svelte';
  import { thumbnailPageUrl } from '../lib/api.js';
  import { selectVideoFragmentPreviews } from '../domain/video-fragment-previews.js';

  let {
    model,
    tags,
    videos,
    onOpenFragment,
  }: {
    model: SearchModel;
    tags: readonly TagDefinition[];
    videos: readonly ProjectSummary[];
    onOpenFragment: (videoId: string, fragmentId: string) => void;
  } = $props();

  let filtersOpen = $state(false);
  let pendingIndexUpdates = $derived(model.response?.indexing.pending ?? 0);

  function toggleId(ids: readonly string[], id: string): string[] {
    return ids.includes(id)
      ? ids.filter((value) => value !== id)
      : [...ids, id];
  }

  function toggleTag(tagId: string): void {
    model.setFilters({
      ...model.filters,
      tagIds: toggleId(model.filters.tagIds, tagId),
    });
  }

  function toggleVideo(videoId: string): void {
    model.setFilters({
      ...model.filters,
      videoIds: toggleId(model.filters.videoIds, videoId),
    });
  }

  function duration(result: FragmentSearchResultDto): string {
    return `${(result.startUs / 1_000_000).toFixed(2)}–${(
      result.endUs / 1_000_000
    ).toFixed(2)}s`;
  }

  function resultPreviews(result: FragmentSearchResultDto) {
    const manifest = model.manifests[result.videoId];
    if (manifest === undefined) return searchResultPreviews(result);
    return selectVideoFragmentPreviews(
      manifest,
      result.startUs / 1_000_000,
      result.endUs / 1_000_000,
    ).map((preview) => ({
      ...preview,
      href: thumbnailPageUrl(
        result.videoId,
        preview.pageFileName,
        preview.identity,
      ),
    }));
  }
</script>

<section class="search-view" aria-labelledby="search-title">
  <div class="panel-heading">
    <div>
      <h1 id="search-title">Search</h1>
      <p>Find fragments across your video library.</p>
    </div>
  </div>

  <label class="search-input-label" for="fragment-search"
    >Search fragments</label
  >
  <input
    id="fragment-search"
    class="search-input"
    value={model.query}
    type="search"
    placeholder="Describe a fragment, move, or moment"
    oninput={(event) => model.setQuery(event.currentTarget.value)}
  />

  <details class="search-filters" bind:open={filtersOpen}>
    <summary
      >Filters{model.filters.tagIds.length + model.filters.videoIds.length > 0
        ? ` (${model.filters.tagIds.length + model.filters.videoIds.length})`
        : ''}</summary
    >
    <div class="search-filter-groups">
      <fieldset>
        <legend>Tags</legend>
        <div class="filter-tags">
          {#each tags as tag (tag.id)}
            <button
              type="button"
              aria-pressed={model.filters.tagIds.includes(tag.id)}
              onclick={() => toggleTag(tag.id)}>{tag.name}</button
            >
          {/each}
        </div>
      </fieldset>
      <fieldset>
        <legend>Videos</legend>
        <div class="filter-tags">
          {#each videos as video (video.id)}
            <button
              type="button"
              aria-pressed={model.filters.videoIds.includes(video.id)}
              onclick={() => toggleVideo(video.id)}>{video.fileName}</button
            >
          {/each}
        </div>
      </fieldset>
    </div>
  </details>

  {#if pendingIndexUpdates > 0}
    <p class="search-indexing-hint">
      Indexing {pendingIndexUpdates} recent changes
    </p>
  {/if}
  {#if model.response?.mode === 'lexical'}
    <p class="search-indexing-hint">
      Lexical results while embeddings reconnect
    </p>
  {/if}
  {#if model.error !== null}
    <p class="error-text" role="alert">{model.error}</p>
  {/if}

  {#if model.query.trim() === ''}
    <p class="empty-copy">
      Search your fragments by description, title, or tag.
    </p>
  {:else if model.state === 'loading' && model.response === null}
    <p class="empty-copy">Searching fragments…</p>
  {:else if model.response !== null && model.response.results.length === 0}
    <p class="empty-copy">No fragments match this search.</p>
  {:else if model.response !== null}
    <div class="fragment-grid search-results">
      {#each model.response.results as result (result.id)}
        <article>
          <button
            class="search-result-card"
            type="button"
            onclick={() => onOpenFragment(result.videoId, result.id)}
          >
            <FragmentPreviewStrip previews={resultPreviews(result)} />
            <span class="fragment-card-copy">
              <strong>{searchResultLabel(result)}</strong>
              <span>{result.sourceTitle} · {duration(result)}</span>
              <span class="tag-chips">
                {#each result.tags as tag (tag.id)}
                  <span class="tag-chip">{tag.name}</span>
                {/each}
              </span>
            </span>
          </button>
        </article>
      {/each}
    </div>
  {/if}
</section>
