<script module lang="ts">
  export type ActiveView = 'editor' | 'library' | 'fragments' | 'search';
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
    processing,
    alerts,
    editor,
    library,
    fragments,
    search,
  }: {
    activeView: ActiveView;
    mode: EditorMode;
    statusLabel: string;
    statusState: 'ready' | 'working' | 'attention';
    onViewChange: (view: ActiveView) => void;
    status: Snippet;
    processing: Snippet;
    alerts: Snippet;
    editor: Snippet;
    library: Snippet;
    fragments: Snippet;
    search: Snippet;
  } = $props();
</script>

<AppBar
  {activeView}
  {statusLabel}
  {statusState}
  {onViewChange}
  {status}
  {processing}
>
  {#snippet help()}
    <ContextHelp {mode} />
  {/snippet}
</AppBar>

{@render alerts()}

<div class="view-content" data-view={activeView}>
  {#if activeView === 'editor'}
    {@render editor()}
  {:else if activeView === 'library'}
    {@render library()}
  {:else if activeView === 'fragments'}
    {@render fragments()}
  {:else}
    {@render search()}
  {/if}
</div>
