<script lang="ts">
  import type { JobState, ProjectDocument } from '@cut-on-eight/contracts';
  import type { SaveState } from '../lib/save-controller.js';

  let {
    projects,
    activeProjectId,
    busyProjectId,
    saveStateFor,
    jobStateFor,
    onActivate,
    onClose,
  }: {
    projects: ProjectDocument[];
    activeProjectId: string | null;
    busyProjectId: string | null;
    saveStateFor: (projectId: string) => SaveState;
    jobStateFor: (projectId: string) => JobState | null;
    onActivate: (projectId: string) => void;
    onClose: (projectId: string) => void;
  } = $props();
</script>

<nav class="project-strip" aria-label="Open videos">
  {#each projects as project (project.id)}
    {@const active = project.id === activeProjectId}
    {@const saveState = saveStateFor(project.id)}
    {@const jobState = jobStateFor(project.id)}
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
          {#if jobState !== null}<span>inspection {jobState}</span>{/if}
        </span>
      </button>
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
