<script lang="ts">
  import type { ProjectSummary } from '@cut-on-eight/legacy-contracts';
  import ConfirmDialog from './ConfirmDialog.svelte';

  let {
    projects,
    openProjectIds,
    openingProjectId,
    importing,
    onImport,
    onOpen,
    onDelete,
  }: {
    projects: ProjectSummary[];
    openProjectIds: ReadonlySet<string>;
    openingProjectId: string | null;
    importing: boolean;
    onImport: () => void;
    onOpen: (projectId: string) => void;
    onDelete: (projectId: string) => Promise<void>;
  } = $props();

  let deleteCandidate = $state<ProjectSummary | null>(null);
  let deleting = $state(false);
  let deleteError = $state<string | null>(null);

  async function confirmDelete(): Promise<void> {
    if (deleteCandidate === null || deleting) return;
    deleting = true;
    deleteError = null;
    try {
      await onDelete(deleteCandidate.id);
      deleteCandidate = null;
    } catch (error) {
      deleteError =
        error instanceof Error ? error.message : 'Video deletion failed.';
    } finally {
      deleting = false;
    }
  }
</script>

<section class="library-panel" aria-labelledby="library-title">
  <div class="panel-heading">
    <div>
      <h1 id="library-title">Library</h1>
      <p>Managed source videos</p>
    </div>
    <div class="library-actions">
      <span class="item-count">{projects.length}</span>
      <button
        class="primary-action"
        type="button"
        onclick={onImport}
        disabled={importing}
      >
        {importing ? 'Selecting…' : 'Import MP4'}
      </button>
    </div>
  </div>

  {#if projects.length === 0}
    <p class="empty-copy">Import an MP4 to start your managed library.</p>
  {:else}
    <ul class="library-list">
      {#each projects as project (project.id)}
        {@const isOpen = openProjectIds.has(project.id)}
        <li>
          <div class="library-item-copy">
            <strong>{project.fileName}</strong>
            <span>
              {project.durationSeconds === null
                ? 'Inspecting duration'
                : `${Math.round(project.durationSeconds)} seconds`}
            </span>
          </div>
          <div class="library-item-actions">
            <button
              class="secondary-action"
              type="button"
              disabled={isOpen || openingProjectId !== null}
              onclick={() => onOpen(project.id)}
            >
              {openingProjectId === project.id
                ? 'Opening…'
                : isOpen
                  ? 'Open'
                  : 'Reopen'}
            </button>
            <button
              class="danger-action"
              type="button"
              onclick={() => (deleteCandidate = project)}>Delete</button
            >
          </div>
        </li>
      {/each}
    </ul>
  {/if}
</section>

<ConfirmDialog
  open={deleteCandidate !== null}
  title={`Delete ${deleteCandidate?.fileName ?? 'video'}?`}
  confirmLabel="Delete permanently"
  busy={deleting}
  onConfirm={() => void confirmDelete()}
  onCancel={() => (deleteCandidate = null)}
>
  <p>
    The managed video, its fragments, thumbnails, and background jobs will be
    permanently removed. The external original is not touched.
  </p>
  {#if deleteError !== null}<p class="error-text">{deleteError}</p>{/if}
</ConfirmDialog>
