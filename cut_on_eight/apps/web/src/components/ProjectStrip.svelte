<script lang="ts">
  import type {
    JobRecord,
    ProjectDocument,
  } from '@cut-on-eight/legacy-contracts';
  import type { SaveState } from '../lib/save-controller.js';

  let {
    projects,
    activeProjectId,
    busyProjectId,
    saveStateFor,
    inspectionJobFor,
    retryingJobId,
    onActivate,
    onClose,
    onRetryInspection,
  }: {
    projects: ProjectDocument[];
    activeProjectId: string | null;
    busyProjectId: string | null;
    saveStateFor: (projectId: string) => SaveState;
    inspectionJobFor: (projectId: string) => JobRecord | null;
    retryingJobId: string | null;
    onActivate: (projectId: string) => void;
    onClose: (projectId: string) => void;
    onRetryInspection: (job: JobRecord) => void;
  } = $props();
</script>

<nav class="project-strip" aria-label="Open videos">
  {#each projects as project (project.id)}
    {@const active = project.id === activeProjectId}
    {@const saveState = saveStateFor(project.id)}
    {@const inspectionJob = inspectionJobFor(project.id)}
    <div class="project-tab" data-active={active}>
      <button
        class="project-switch"
        type="button"
        aria-current={active ? 'page' : undefined}
        disabled={busyProjectId !== null}
        onclick={() => onActivate(project.id)}
      >
        <span class="project-name">{project.source.fileName}</span>
        <span class="project-meta">
          <span data-save-state={saveState}>{saveState}</span>
          {#if inspectionJob !== null}
            <span
              data-job-state={inspectionJob.state}
              title={inspectionJob.state === 'failed'
                ? inspectionJob.error.message
                : undefined}>inspection {inspectionJob.state}</span
            >
          {/if}
        </span>
      </button>
      {#if inspectionJob?.state === 'failed' && inspectionJob.error.retryable}
        <button
          class="retry-inspection"
          type="button"
          title={inspectionJob.error.message}
          disabled={retryingJobId !== null}
          onclick={() => onRetryInspection(inspectionJob)}
        >
          {retryingJobId === inspectionJob.id ? 'Retrying…' : 'Retry'}
        </button>
      {/if}
      <button
        class="close-project"
        type="button"
        aria-label={`Close ${project.source.fileName}`}
        title="Save and close"
        disabled={busyProjectId !== null}
        onclick={() => onClose(project.id)}
      >
        ×
      </button>
    </div>
  {/each}
</nav>
