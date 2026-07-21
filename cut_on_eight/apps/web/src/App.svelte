<script lang="ts">
  import type {
    JobSnapshot,
    JobState,
    ProjectDocument,
    WorkspaceSnapshot,
  } from '@cut-on-eight/contracts';
  import { onDestroy } from 'svelte';
  import AppBar from './components/AppBar.svelte';
  import LibraryPanel from './components/LibraryPanel.svelte';
  import ProjectStrip from './components/ProjectStrip.svelte';
  import {
    activateProject,
    closeProject,
    loadJobs,
    loadWorkspace,
    openProject,
    saveProject,
    selectImport,
  } from './lib/api.js';
  import {
    SaveController,
    type SaveState,
    type SaveStatus,
  } from './lib/save-controller.js';

  type BackendState = 'checking' | 'ready' | 'unavailable';

  let workspace = $state.raw<WorkspaceSnapshot | null>(null);
  let jobs = $state.raw<JobSnapshot | null>(null);
  let backendState = $state<BackendState>('checking');
  let loading = $state(true);
  let importing = $state(false);
  let openingProjectId = $state<string | null>(null);
  let busyProjectId = $state<string | null>(null);
  let errorMessage = $state<string | null>(null);
  let jobsLabel = $state('checking');
  let saveStates = $state<Record<string, SaveState>>({});
  let saveErrors = $state<Record<string, string>>({});
  let retryingProjectId = $state<string | null>(null);

  const controllers = new Map<string, SaveController>();
  let disposed = false;

  onDestroy(() => {
    disposed = true;
    for (const controller of controllers.values()) controller.cancel();
    controllers.clear();
  });
  const activeProject = $derived(
    workspace?.openProjects.find(
      (project) => project.id === workspace?.activeProjectId,
    ) ?? null,
  );
  const openProjectIds = $derived(
    new Set(workspace?.openProjects.map((project) => project.id) ?? []),
  );

  function describeError(error: unknown, action: string): string {
    return error instanceof Error
      ? `${action}: ${error.message}`
      : `${action}: unknown error`;
  }

  function documentFor(projectId: string): ProjectDocument {
    const project = workspace?.openProjects.find(
      (candidate) => candidate.id === projectId,
    );
    if (project === undefined) {
      throw new Error('The project is no longer open.');
    }
    return project;
  }

  function projectName(projectId: string): string {
    return (
      workspace?.openProjects.find((project) => project.id === projectId)
        ?.source.fileName ?? 'Project'
    );
  }

  function updateSaveStatus(projectId: string, status: SaveStatus): void {
    saveStates = { ...saveStates, [projectId]: status.state };
    const nextErrors = { ...saveErrors };

    if (status.state === 'failed' && status.error !== null) {
      nextErrors[projectId] = status.error;
    } else {
      delete nextErrors[projectId];
    }

    saveErrors = nextErrors;
  }

  function ensureControllers(): void {
    const liveIds = new Set(
      workspace?.openProjects.map((project) => project.id) ?? [],
    );

    for (const [projectId, controller] of controllers) {
      if (!liveIds.has(projectId)) {
        controller.cancel();
        controllers.delete(projectId);
      }
    }

    for (const projectId of liveIds) {
      if (controllers.has(projectId)) continue;

      saveStates = { ...saveStates, [projectId]: 'saved' };
      controllers.set(
        projectId,
        new SaveController({
          save: async () => {
            await saveProject(documentFor(projectId));
          },
          onStatusChange: (status) => updateSaveStatus(projectId, status),
        }),
      );
    }
  }

  function applyWorkspace(
    snapshot: WorkspaceSnapshot,
    preserveEdits = true,
  ): void {
    if (disposed) return;

    const currentProjects = new Map(
      preserveEdits
        ? workspace?.openProjects.map((project) => [project.id, project])
        : [],
    );
    workspace = {
      ...snapshot,
      openProjects: snapshot.openProjects.map(
        (project) => currentProjects.get(project.id) ?? project,
      ),
    };
    ensureControllers();
  }

  function saveStateFor(projectId: string): SaveState {
    return saveStates[projectId] ?? 'saved';
  }

  function jobStateFor(projectId: string): JobState | null {
    const projectJobs =
      jobs?.jobs.filter((job) => job.projectId === projectId) ?? [];
    return projectJobs.at(-1)?.state ?? null;
  }

  async function refreshJobs(): Promise<void> {
    try {
      jobs = await loadJobs();
      const activeJobs = jobs.jobs.filter(
        (job) => job.state === 'queued' || job.state === 'running',
      ).length;
      jobsLabel = activeJobs === 0 ? 'idle' : `${activeJobs} active`;
    } catch {
      jobs = null;
      jobsLabel = 'unavailable';
    }
  }

  async function initialize(): Promise<void> {
    try {
      applyWorkspace(await loadWorkspace(), false);
      backendState = 'ready';
      void refreshJobs();
    } catch (error) {
      backendState = 'unavailable';
      errorMessage = describeError(error, 'Could not load the workspace');
    } finally {
      loading = false;
    }
  }

  async function importMp4(): Promise<void> {
    importing = true;
    errorMessage = null;
    try {
      const result = await selectImport();
      applyWorkspace(result.workspace);
      void refreshJobs();
    } catch (error) {
      errorMessage = describeError(error, 'Import failed');
    } finally {
      importing = false;
    }
  }

  async function reopenProject(projectId: string): Promise<void> {
    openingProjectId = projectId;
    errorMessage = null;
    try {
      applyWorkspace(await openProject(projectId));
    } catch (error) {
      errorMessage = describeError(error, 'Could not reopen the video');
    } finally {
      openingProjectId = null;
    }
  }

  async function switchProject(projectId: string): Promise<void> {
    if (projectId === workspace?.activeProjectId || busyProjectId !== null)
      return;

    busyProjectId = projectId;
    errorMessage = null;
    try {
      const currentId = workspace?.activeProjectId;
      if (currentId !== null && currentId !== undefined) {
        await controllers.get(currentId)?.flush();
      }
      applyWorkspace(await activateProject(projectId));
    } catch (error) {
      errorMessage = describeError(error, 'Could not switch videos');
    } finally {
      busyProjectId = null;
    }
  }

  async function saveAndClose(projectId: string): Promise<void> {
    if (busyProjectId !== null) return;

    busyProjectId = projectId;
    errorMessage = null;
    try {
      await controllers.get(projectId)?.flush();
      const snapshot = await closeProject(documentFor(projectId));
      applyWorkspace(snapshot);
    } catch (error) {
      errorMessage = describeError(error, 'Could not save and close the video');
    } finally {
      busyProjectId = null;
    }
  }

  async function retryAutosave(projectId: string): Promise<void> {
    retryingProjectId = projectId;
    try {
      await controllers.get(projectId)?.retry();
    } catch {
      // SaveController reports the safe failure detail through onStatusChange.
    } finally {
      retryingProjectId = null;
    }
  }

  void initialize();
</script>

<svelte:head>
  <meta
    name="description"
    content="Local dance-video segmentation and cataloguing"
  />
</svelte:head>

<main>
  <AppBar
    {backendState}
    ffprobeState="unavailable"
    {jobsLabel}
    {importing}
    onImport={() => void importMp4()}
  />

  {#if errorMessage !== null}
    <div class="error-banner" role="alert">
      <span>{errorMessage}</span>
      <button type="button" onclick={() => (errorMessage = null)}
        >Dismiss</button
      >
    </div>
  {/if}

  {#each Object.entries(saveErrors) as [projectId, saveError] (projectId)}
    <div class="save-error-banner" role="alert">
      <span
        ><strong>{projectName(projectId)}</strong> was not saved: {saveError}</span
      >
      <button
        type="button"
        disabled={retryingProjectId !== null}
        onclick={() => void retryAutosave(projectId)}
      >
        {retryingProjectId === projectId ? 'Retrying…' : 'Retry save'}
      </button>
    </div>
  {/each}

  {#if loading}
    <section class="loading-state" aria-live="polite">
      Restoring your workspace…
    </section>
  {:else if workspace !== null}
    <ProjectStrip
      projects={workspace.openProjects}
      activeProjectId={workspace.activeProjectId}
      {busyProjectId}
      {saveStateFor}
      {jobStateFor}
      onActivate={(projectId) => void switchProject(projectId)}
      onClose={(projectId) => void saveAndClose(projectId)}
    />

    <div class="workspace-layout">
      <LibraryPanel
        projects={workspace.library}
        {openProjectIds}
        {openingProjectId}
        onOpen={(projectId) => void reopenProject(projectId)}
      />

      <section class="workspace-stage" aria-labelledby="workspace-title">
        {#if activeProject !== null}
          <div class="stage-heading">
            <p class="eyebrow">Active video</p>
            <h2 id="workspace-title">{activeProject.source.fileName}</h2>
          </div>
          <div class="editor-placeholder">
            <span aria-hidden="true">▶</span>
            <p>The managed video is ready for rough marking.</p>
          </div>
        {:else}
          <div class="empty-workspace">
            <p class="eyebrow">Nothing open</p>
            <h2 id="workspace-title">
              Choose a managed video or import an MP4.
            </h2>
          </div>
        {/if}
      </section>
    </div>
  {/if}
</main>
