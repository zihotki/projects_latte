<script module lang="ts">
  export type ActiveView = 'editor' | 'library';
  export type EditorMode = 'video' | 'segment' | 'boundary';
</script>

<script lang="ts">
  import type { Snippet } from 'svelte';
  import AppBar from './AppBar.svelte';
  import ContextHelp from './ContextHelp.svelte';

  let {
    activeView,
    mode,
    statusLabel,
    statusState,
    onViewChange,
    status,
    alerts,
    editor,
    library,
  }: {
    activeView: ActiveView;
    mode: EditorMode;
    statusLabel: string;
    statusState: 'ready' | 'working' | 'attention';
    onViewChange: (view: ActiveView) => void;
    status: Snippet;
    alerts: Snippet;
    editor: Snippet;
    library: Snippet;
  } = $props();
</script>

<AppBar {activeView} {statusLabel} {statusState} {onViewChange} {status}>
  {#snippet help()}
    <ContextHelp {mode} />
  {/snippet}
</AppBar>

{@render alerts()}

<div class="view-content" data-view={activeView}>
  {#if activeView === 'editor'}
    {@render editor()}
  {:else}
    {@render library()}
  {/if}
</div>
