<script lang="ts">
  import type { ProcessingModel } from '../app/processing-model.svelte.js';

  let {
    model,
    onOpenVideo,
  }: {
    model: ProcessingModel;
    onOpenVideo: (videoId: string) => void;
  } = $props();
</script>

<div class="processing-control">
  <button
    type="button"
    class="status-summary processing-toggle"
    aria-expanded={model.expanded}
    aria-controls="processing-panel"
    onclick={() => model.toggle()}
  >
    Processing {model.snapshot?.activeCount ?? '—'}
    {#if (model.snapshot?.failedCount ?? 0) > 0}
      <span
        class="processing-failure-count"
        aria-label={`${model.snapshot?.failedCount} failed`}
      >
        !{model.snapshot?.failedCount}
      </span>
    {/if}
  </button>

  {#if model.expanded}
    <aside
      id="processing-panel"
      class="processing-panel"
      aria-label="Video processing"
    >
      <div class="processing-heading">
        <strong>Video processing</strong>
        <button
          type="button"
          aria-label="Close processing panel"
          onclick={() => model.toggle()}>×</button
        >
      </div>
      {#if model.stale}
        <p class="processing-stale" role="status">Status may be out of date.</p>
      {/if}
      {#if model.snapshot === null}
        <p class="processing-empty">Status unavailable.</p>
      {:else if model.snapshot.items.length > 0}
        <ul>
          {#each model.snapshot.items as item (`${item.videoId}:${item.task}`)}
            <li>
              <button type="button" onclick={() => onOpenVideo(item.videoId)}>
                <strong>{item.videoTitle}</strong>
                <span>{item.task} · {item.state}</span>
                {#if item.failureCode !== null}
                  <small>{item.failureCode.replaceAll('_', ' ')}</small>
                {/if}
              </button>
            </li>
          {/each}
        </ul>
      {:else}
        <p class="processing-empty">No video work in progress.</p>
      {/if}
    </aside>
  {/if}
</div>
