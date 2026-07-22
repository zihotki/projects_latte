<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { ActiveView } from './EditorShell.svelte';

  let {
    activeView,
    statusLabel,
    statusState,
    onViewChange,
    status,
    help,
  }: {
    activeView: ActiveView;
    statusLabel: string;
    statusState: 'ready' | 'working' | 'attention';
    onViewChange: (view: ActiveView) => void;
    status: Snippet;
    help: Snippet;
  } = $props();
</script>

<header class="app-bar" aria-label="Cut on Eight">
  <nav class="view-tabs" aria-label="Application sections">
    <button
      type="button"
      aria-current={activeView === 'editor' ? 'page' : undefined}
      onclick={() => onViewChange('editor')}>Editor</button
    >
    <button
      type="button"
      aria-current={activeView === 'library' ? 'page' : undefined}
      onclick={() => onViewChange('library')}>Library</button
    >
    <button
      type="button"
      aria-current={activeView === 'fragments' ? 'page' : undefined}
      onclick={() => onViewChange('fragments')}>Fragments</button
    >
  </nav>

  <div class="top-tools">
    <details class="status-menu">
      <summary class="status-summary" data-state={statusState}
        >{statusLabel}</summary
      >
      <section class="popover status-popover" aria-label="Operational status">
        {@render status()}
      </section>
    </details>
    {@render help()}
  </div>
</header>
