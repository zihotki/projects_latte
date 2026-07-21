<script lang="ts">
  import type { EditorMode } from './EditorShell.svelte';

  let { mode }: { mode: EditorMode } = $props();

  let open = $state(false);
  let trigger = $state<HTMLButtonElement>();

  const title = $derived(
    mode === 'boundary'
      ? 'Boundary editing'
      : mode === 'segment'
        ? 'Selected segment'
        : 'Full video',
  );

  function close(): void {
    open = false;
    queueMicrotask(() => trigger?.focus());
  }

  function handleKeydown(event: KeyboardEvent): void {
    if (!open || event.key !== 'Escape') return;

    event.preventDefault();
    event.stopImmediatePropagation();
    close();
  }
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="context-help">
  <button
    bind:this={trigger}
    class="icon-button"
    type="button"
    aria-label="Editor keyboard help"
    aria-expanded={open}
    aria-controls="editor-help"
    onclick={() => (open = !open)}>?</button
  >

  {#if open}
    <section id="editor-help" class="popover help-popover" aria-label={title}>
      <div class="popover-heading">
        <strong>{title}</strong>
        <button type="button" aria-label="Close help" onclick={close}>×</button>
      </div>

      <dl class="shortcut-list">
        {#if mode === 'boundary'}
          <div>
            <dt><kbd>←</kbd> <kbd>→</kbd></dt>
            <dd>Nudge one frame</dd>
          </div>
          <div>
            <dt><kbd>Shift</kbd> + <kbd>←</kbd> <kbd>→</kbd></dt>
            <dd>Nudge 0.1 seconds</dd>
          </div>
          <div>
            <dt><kbd>Escape</kbd></dt>
            <dd>Leave boundary editing</dd>
          </div>
        {:else if mode === 'segment'}
          <div>
            <dt><kbd>Space</kbd></dt>
            <dd>Play, pause, or loop the segment</dd>
          </div>
          <div>
            <dt><kbd>Enter</kbd></dt>
            <dd>Preview with one second of context</dd>
          </div>
          <div>
            <dt><kbd>↑</kbd> <kbd>↓</kbd></dt>
            <dd>Select the previous or next segment</dd>
          </div>
          <div>
            <dt><kbd>←</kbd> <kbd>→</kbd></dt>
            <dd>Seek 1 second; hold Shift for 10</dd>
          </div>
          <div>
            <dt><kbd>Delete</kbd></dt>
            <dd>Delete the selected segment</dd>
          </div>
          <div>
            <dt><kbd>I</kbd> / <kbd>O</kbd></dt>
            <dd>Mark another segment</dd>
          </div>
          <div>
            <dt><kbd>Escape</kbd></dt>
            <dd>Return to the full video</dd>
          </div>
        {:else}
          <div>
            <dt><kbd>Space</kbd></dt>
            <dd>Play or pause</dd>
          </div>
          <div>
            <dt><kbd>←</kbd> <kbd>→</kbd></dt>
            <dd>Seek 1 second; hold Shift for 10</dd>
          </div>
          <div>
            <dt><kbd>I</kbd> / <kbd>O</kbd></dt>
            <dd>Mark segment start and end</dd>
          </div>
          <div>
            <dt><kbd>Backspace</kbd></dt>
            <dd>Delete the most recent segment</dd>
          </div>
        {/if}
      </dl>
    </section>
  {/if}
</div>
