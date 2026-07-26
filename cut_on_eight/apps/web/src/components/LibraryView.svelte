<script lang="ts">
  import type { FragmentLibrary } from '../app/fragment-library.svelte.js';
  import type { WorkspaceSession } from '../app/workspace-session.svelte.js';
  import LibraryPanel from './LibraryPanel.svelte';

  let {
    workspace,
    fragments,
  }: { workspace: WorkspaceSession; fragments: FragmentLibrary } = $props();
</script>

{#if workspace.loading}
  <section class="loading-state" aria-live="polite">
    Restoring your library…
  </section>
{:else if workspace.workspace !== null}
  <LibraryPanel
    projects={workspace.workspace.library}
    openProjectIds={workspace.openProjectIds}
    openingProjectId={workspace.openingProjectId}
    importing={workspace.importing}
    onImport={async (file) => {
      await workspace.importMp4(file);
    }}
    onOpen={(projectId) => void workspace.reopenProject(projectId)}
    onDelete={(projectId) => fragments.removeManagedVideo(projectId)}
  />
{/if}
