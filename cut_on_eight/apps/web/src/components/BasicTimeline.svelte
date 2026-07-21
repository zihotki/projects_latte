<script lang="ts">
  import type { Segment } from '@cut-on-eight/contracts';
  import { segmentDurationStatus } from '../lib/segment-constraints.js';

  let {
    durationSeconds,
    currentSeconds,
    pendingStartSeconds,
    segments,
    selectedSegmentId,
    onSelect,
    onSeek,
    onClearSelectionAndSeek,
  }: {
    durationSeconds: number;
    currentSeconds: number;
    pendingStartSeconds: number | null;
    segments: Segment[];
    selectedSegmentId: string | null;
    onSelect: (segment: Segment) => void;
    onSeek: (seconds: number) => void;
    onClearSelectionAndSeek: (seconds: number) => void;
  } = $props();

  const safeDuration = $derived(Math.max(durationSeconds, 0));

  function percentage(seconds: number): number {
    if (safeDuration === 0) return 0;
    return Math.min(100, Math.max(0, (seconds / safeDuration) * 100));
  }

  function seekFromPointer(event: MouseEvent): void {
    if (safeDuration === 0 || !(event.currentTarget instanceof HTMLElement)) {
      return;
    }

    const bounds = event.currentTarget.getBoundingClientRect();
    const ratio = Math.min(
      1,
      Math.max(0, (event.clientX - bounds.left) / bounds.width),
    );
    onClearSelectionAndSeek(ratio * safeDuration);
  }

  function seekFromKeyboard(event: KeyboardEvent): void {
    const step = event.shiftKey ? 10 : 1;
    let next: number | null = null;

    if (event.key === 'ArrowLeft') next = currentSeconds - step;
    if (event.key === 'ArrowRight') next = currentSeconds + step;
    if (event.key === 'Home') next = 0;
    if (event.key === 'End') next = safeDuration;
    if (next === null) return;

    event.preventDefault();
    onSeek(Math.min(safeDuration, Math.max(0, next)));
  }
</script>

<div class="timeline-shell">
  <div
    class="timeline-lane"
    role="slider"
    tabindex="0"
    aria-label="Video timeline"
    aria-valuemin="0"
    aria-valuemax={safeDuration}
    aria-valuenow={Math.min(currentSeconds, safeDuration)}
    onclick={seekFromPointer}
    onkeydown={seekFromKeyboard}
  >
    {#if pendingStartSeconds !== null}
      <span
        class="pending-range"
        style:left={`${percentage(Math.min(pendingStartSeconds, currentSeconds))}%`}
        style:width={`${Math.abs(percentage(currentSeconds) - percentage(pendingStartSeconds))}%`}
        aria-hidden="true"
      ></span>
    {/if}

    {#each segments as segment (segment.id)}
      {@const duration = segment.endSeconds - segment.startSeconds}
      {@const durationStatus = segmentDurationStatus(duration)}
      <button
        class="segment-range"
        class:selected={segment.id === selectedSegmentId}
        type="button"
        aria-label={`Select ${durationStatus === 'expected' ? '' : `${durationStatus} `}segment from ${segment.startSeconds.toFixed(2)} to ${segment.endSeconds.toFixed(2)} seconds`}
        data-duration-status={durationStatus}
        style:left={`${percentage(segment.startSeconds)}%`}
        style:width={`${Math.max(0.35, percentage(segment.endSeconds) - percentage(segment.startSeconds))}%`}
        onclick={(event) => {
          event.stopPropagation();
          onSelect(segment);
        }}
      ></button>
    {/each}

    <span
      class="timeline-playhead"
      style:left={`${percentage(currentSeconds)}%`}
      aria-hidden="true"
    ></span>
  </div>
</div>
