<script lang="ts">
  import { onDestroy } from 'svelte';
  import { createAppModel } from './app/app-model.svelte.js';
  import AppStatus from './components/AppStatus.svelte';
  import EditorShell from './components/EditorShell.svelte';
  import EditorWorkspaceView from './components/EditorWorkspaceView.svelte';
  import FragmentLibraryView from './components/FragmentLibraryView.svelte';
  import LibraryView from './components/LibraryView.svelte';

  const app = createAppModel();
  onDestroy(() => app.dispose());
  void app.start();
</script>

<svelte:head>
  <meta
    name="description"
    content="Local dance-video segmentation and cataloguing"
  />
</svelte:head>

<main>
  <EditorShell
    activeView={app.preferences.activeView}
    mode={app.editorMode}
    statusLabel={app.status.label}
    statusState={app.status.state}
    onViewChange={(view) => app.changeView(view)}
  >
    {#snippet status()}
      <AppStatus {app} variant="summary" />
    {/snippet}

    {#snippet alerts()}
      <AppStatus {app} variant="alerts" />
    {/snippet}

    {#snippet editor()}
      <EditorWorkspaceView
        workspace={app.workspace}
        background={app.background}
        fragments={app.fragments}
        preferences={app.preferences}
        onOpenLibrary={() => app.changeView('library')}
      />
    {/snippet}

    {#snippet library()}
      <LibraryView workspace={app.workspace} fragments={app.fragments} />
    {/snippet}

    {#snippet fragments()}
      <FragmentLibraryView fragments={app.fragments} />
    {/snippet}
  </EditorShell>
</main>
