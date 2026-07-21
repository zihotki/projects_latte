<script lang="ts">
  import type { ProjectSummary } from '@cut-on-eight/contracts';

  let {
    projects,
    openProjectIds,
    openingProjectId,
    importing,
    onImport,
    onOpen,
  }: {
    projects: ProjectSummary[];
    openProjectIds: ReadonlySet<string>;
    openingProjectId: string | null;
    importing: boolean;
    onImport: () => void;
    onOpen: (projectId: string) => void;
  } = $props();
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
        </li>
      {/each}
    </ul>
  {/if}
</section>
