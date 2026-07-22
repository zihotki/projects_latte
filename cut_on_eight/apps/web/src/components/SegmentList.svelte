<script lang="ts">
  import type { Segment } from '@cut-on-eight/contracts';
  import { segmentDurationStatus } from '../lib/segment-constraints.js';
  import { sortSegmentsByStart } from '../lib/segments.js';

  let {
    segments,
    selectedSegmentId,
    onSelect,
    onToggleExport,
  }: {
    segments: Segment[];
    selectedSegmentId: string | null;
    onSelect: (segment: Segment) => void;
    onToggleExport: (segmentId: string, selected: boolean) => void;
  } = $props();

  const chronologicalSegments = $derived(sortSegmentsByStart(segments));

  function formatTime(seconds: number): string {
    const minutes = Math.floor(seconds / 60);
    const remainder = seconds - minutes * 60;
    return `${minutes}:${remainder.toFixed(2).padStart(5, '0')}`;
  }
</script>

<section class="segment-list-panel" aria-labelledby="segment-list-title">
  <div class="segment-list-heading">
    <h2 id="segment-list-title">Segments</h2>
    <span class="item-count">{segments.length}</span>
  </div>

  {#if chronologicalSegments.length === 0}
    <p class="segment-list-empty">No segments yet.</p>
  {:else}
    <ol class="segment-list">
      {#each chronologicalSegments as segment, index (segment.id)}
        {@const duration = segment.endSeconds - segment.startSeconds}
        {@const durationStatus = segmentDurationStatus(duration)}
        <li
          class:selected={segment.id === selectedSegmentId}
          data-segment-id={segment.id}
        >
          <button
            class="segment-list-select"
            type="button"
            aria-pressed={segment.id === selectedSegmentId}
            aria-label={`Select segment ${index + 1} for keyboard playback`}
            data-editor-playback-surface
            data-segment-focus-id={segment.id}
            onclick={() => onSelect(segment)}
          >
            <span>Segment {index + 1}</span>
            <strong
              >{formatTime(segment.startSeconds)}–{formatTime(
                segment.endSeconds,
              )}</strong
            >
            <small data-duration-status={durationStatus}
              >{duration.toFixed(2)}s{durationStatus === 'short'
                ? ' · short'
                : durationStatus === 'long'
                  ? ' · long'
                  : ''}</small
            >
          </button>
          <label class="export-choice">
            <input
              type="checkbox"
              checked={segment.exportSelected}
              onchange={(event) =>
                onToggleExport(segment.id, event.currentTarget.checked)}
            />
            Export
          </label>
        </li>
      {/each}
    </ol>
  {/if}
</section>
