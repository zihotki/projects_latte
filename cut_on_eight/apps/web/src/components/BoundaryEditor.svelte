<script lang="ts">
  import type { Segment } from '../domain/editor-model.js';
  import type { BoundaryFocus } from '../lib/trim-controller.js';

  let {
    segment,
    focus,
    frameSeconds,
    approximate,
    error,
    onFocus,
    onNudge,
  }: {
    segment: Segment;
    focus: BoundaryFocus;
    frameSeconds: number;
    approximate: boolean;
    error: string | null;
    onFocus: (edge: 'start' | 'end') => void;
    onNudge: (deltaSeconds: number) => void;
  } = $props();

  function formatTime(seconds: number): string {
    const minutes = Math.floor(seconds / 60);
    const remainder = seconds - minutes * 60;
    return `${minutes}:${remainder.toFixed(3).padStart(6, '0')}`;
  }
</script>

<section class="boundary-editor" aria-label="Selected segment boundaries">
  {#each ['start', 'end'] as edge (edge)}
    {@const typedEdge = edge as 'start' | 'end'}
    {@const focused = focus?.edge === typedEdge}
    <div class={['boundary-row', focused && 'focused']}>
      <button
        class="boundary-focus"
        type="button"
        aria-pressed={focused}
        onclick={() => onFocus(typedEdge)}
      >
        <span>{typedEdge === 'start' ? 'Start' : 'End'}</span>
        <strong>{formatTime(segment[`${typedEdge}Seconds`])}</strong>
      </button>
      {#if focused}
        <div class="boundary-nudges" aria-label={`${typedEdge} adjustments`}>
          <button type="button" onclick={() => onNudge(-frameSeconds)}
            >−frame</button
          >
          <button type="button" onclick={() => onNudge(frameSeconds)}
            >+frame</button
          >
          <button type="button" onclick={() => onNudge(-0.1)}>−0.1</button>
          <button type="button" onclick={() => onNudge(0.1)}>+0.1</button>
        </div>
      {/if}
    </div>
  {/each}

  {#if approximate}
    <span class="boundary-warning">Approximate frame stepping</span>
  {/if}
  {#if error !== null}
    <span class="error-text" aria-live="polite">{error}</span>
  {/if}
</section>
