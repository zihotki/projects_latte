<script lang="ts">
  import type { BackgroundProcessing } from '../app/background-processing.svelte.js';
  import type { FragmentLibrary } from '../app/fragment-library.svelte.js';
  import type { UiPreferences } from '../app/ui-preferences.svelte.js';
  import type { WorkspaceSession } from '../app/workspace-session.svelte.js';
  import ProjectStrip from './ProjectStrip.svelte';
  import VideoEditor from './VideoEditor.svelte';

  let {
    workspace,
    background,
    fragments,
    preferences,
    onOpenLibrary,
  }: {
    workspace: WorkspaceSession;
    background: BackgroundProcessing;
    fragments: FragmentLibrary;
    preferences: UiPreferences;
    onOpenLibrary: () => void;
  } = $props();

  const activeProject = $derived(workspace.activeProject);
  const activeThumbnailJob = $derived(
    activeProject === null
      ? null
      : background.thumbnailJobFor(activeProject.id),
  );
</script>

{#if workspace.loading}
  <section class="loading-state" aria-live="polite">
    Restoring your workspace…
  </section>
{:else if workspace.workspace !== null}
  {#if workspace.workspace.openProjects.length > 0}
    <ProjectStrip
      projects={workspace.workspace.openProjects}
      activeProjectId={workspace.workspace.activeProjectId}
      busyProjectId={workspace.busyProjectId}
      saveStateFor={(projectId) => workspace.saveStateFor(projectId)}
      inspectionJobFor={(projectId) => background.inspectionJobFor(projectId)}
      retryingJobId={background.retryingJobId}
      onActivate={(projectId) => void workspace.switchProject(projectId)}
      onClose={(projectId) => void workspace.saveAndClose(projectId)}
      onRetryInspection={(job) => void background.retryInspection(job)}
    />
  {/if}

  <section class="workspace-stage" aria-labelledby="workspace-title">
    {#if activeProject !== null}
      <div class="stage-heading">
        <h1 id="workspace-title">{activeProject.source.fileName}</h1>
      </div>
      {#key activeProject.id}
        <VideoEditor
          project={activeProject}
          thumbnailManifest={background.thumbnailManifestFor(activeProject.id)}
          thumbnailState={background.thumbnailStateFor(activeProject.id)}
          thumbnailRetrying={background.retryingJobId ===
            activeThumbnailJob?.id}
          onRetryThumbnails={() =>
            void background.retryThumbnails(activeProject.id)}
          onThumbnailLoadError={() =>
            background.thumbnailPageLoadFailed(activeProject.id)}
          onChange={(projectId, mutate) =>
            workspace.updateProject(projectId, mutate)}
          onPlaybackSample={(projectId, seconds) =>
            workspace.samplePlaybackPosition(projectId, seconds)}
          registerControl={workspace.registerEditorControl}
          onSave={() => workspace.saveActiveProject()}
          segmentsCollapsed={preferences.segmentPanelCollapsed}
          onSegmentsCollapsedChange={(collapsed) =>
            preferences.setSegmentPanelCollapsed(collapsed)}
          onBoundaryModeChange={(projectId, focused) =>
            preferences.setBoundaryMode(projectId, focused)}
          tags={fragments.tags}
          onCreateTag={(name) => fragments.createTag(name)}
        />
      {/key}
    {:else}
      <div class="empty-workspace">
        <h1 id="workspace-title">No video open</h1>
        <button class="primary-action" type="button" onclick={onOpenLibrary}
          >Open Library</button
        >
      </div>
    {/if}
  </section>
{/if}
