<script lang="ts">
  import type { AppModel } from '../app/app-model.svelte.js';

  let { app, variant }: { app: AppModel; variant: 'summary' | 'alerts' } =
    $props();
</script>

{#if variant === 'summary'}
  <dl class="status-list">
    <div>
      <dt>Backend</dt>
      <dd data-state={app.backendState}>{app.backendState}</dd>
    </div>
    <div>
      <dt>FFprobe</dt>
      <dd data-state={app.background.ffprobeState}>
        {app.background.ffprobeState}
      </dd>
    </div>
    <div>
      <dt>Jobs</dt>
      <dd>{app.status.jobsLabel}</dd>
    </div>
  </dl>
{:else}
  {#if app.background.ffprobeState === 'unavailable'}
    <div class="tool-warning" role="status">
      FFprobe is unavailable, so video details cannot be inspected. Marking,
      saving, and playback still work.
    </div>
  {/if}

  {#if app.background.connectionWarning !== null}
    <div class="connection-warning" role="status">
      {app.background.connectionWarning}
    </div>
  {/if}

  {#if app.status.jobDataWarning !== null}
    <div class="connection-warning" role="status">
      {app.status.jobDataWarning}
    </div>
  {/if}

  {#if app.generalError !== null}
    <div class="error-banner" role="alert">
      <span>{app.generalError}</span>
      <button type="button" onclick={() => app.clearGeneralError()}
        >Dismiss</button
      >
    </div>
  {/if}

  {#each Object.entries(app.workspace.saveErrors) as [projectId, saveError] (projectId)}
    <div class="save-error-banner" role="alert">
      <span
        ><strong>{app.workspace.projectName(projectId)}</strong> was not saved:
        {saveError}</span
      >
      <button
        type="button"
        disabled={app.workspace.retryingProjectId !== null}
        onclick={() => void app.workspace.retryAutosave(projectId)}
      >
        {app.workspace.retryingProjectId === projectId
          ? 'Retrying…'
          : 'Retry save'}
      </button>
    </div>
  {/each}
{/if}
