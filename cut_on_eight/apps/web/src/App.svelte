<script lang="ts">
  import type {
    Capabilities,
    JobRecord,
    JobSnapshot,
    ProjectDocument,
    WorkspaceSnapshot,
  } from '@cut-on-eight/contracts';
  import { onDestroy } from 'svelte';
  import AppBar from './components/AppBar.svelte';
  import LibraryPanel from './components/LibraryPanel.svelte';
  import ProjectStrip from './components/ProjectStrip.svelte';
  import VideoEditor from './components/VideoEditor.svelte';
  import {
    activateProject,
    closeProject,
    loadCapabilities,
    loadWorkspace,
    openProject,
    saveProject,
    selectImport,
    retryJob,
  } from './lib/api.js';
  import {
    connectJobEvents,
    countJobs,
    mergeJobRecord,
    mergeJobSnapshot,
    newestInspectionJob,
  } from './lib/job-events.js';
  import {
    SaveController,
    type SaveState,
    type SaveStatus,
  } from './lib/save-controller.js';
  import type {
    RegisterVideoEditorControl,
    VideoEditorControl,
  } from './lib/editor-control.js';

  type BackendState = 'checking' | 'ready' | 'unavailable';

  let workspace = $state.raw<WorkspaceSnapshot | null>(null);
  let jobs = $state.raw<JobSnapshot | null>(null);
  let backendState = $state<BackendState>('checking');
  let ffprobeState = $state<BackendState>('checking');
  let loading = $state(true);
  let importing = $state(false);
  let openingProjectId = $state<string | null>(null);
  let busyProjectId = $state<string | null>(null);
  let errorMessage = $state<string | null>(null);
  let jobConnectionWarning = $state<string | null>(null);
  let saveStates = $state<Record<string, SaveState>>({});
  let saveErrors = $state<Record<string, string>>({});
  let retryingProjectId = $state<string | null>(null);
  let retryingJobId = $state<string | null>(null);

  const controllers = new Map<string, SaveController>();
  const sampledPlaybackPositions = new Map<string, number>();
  let activeEditorControl: VideoEditorControl | null = null;
  let closeJobEvents: (() => void) | null = null;
  let disposed = false;

  onDestroy(() => {
    disposed = true;
    closeJobEvents?.();
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
  const jobCounts = $derived(countJobs(jobs));
  const jobDataWarning = $derived(
    jobs !== null && jobs.errors.length > 0
      ? `${jobs.errors.length} inspection job record${jobs.errors.length === 1 ? ' is' : 's are'} unreadable and were left unchanged.`
      : null,
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
    const sampledPosition = sampledPlaybackPositions.get(projectId);
    return sampledPosition === undefined
      ? project
      : { ...project, playbackPositionSeconds: sampledPosition };
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
        sampledPlaybackPositions.delete(projectId);
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
        ? workspace?.openProjects.map((project) => [
            project.id,
            documentFor(project.id),
          ])
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

  function updateProject(
    projectId: string,
    mutate: (project: ProjectDocument) => ProjectDocument,
  ): void {
    if (workspace === null) return;
    const index = workspace.openProjects.findIndex(
      (candidate) => candidate.id === projectId,
    );
    if (index < 0) return;

    const current = workspace.openProjects[index];
    if (current === undefined) return;

    let project = mutate(current);
    if (project === current) return;

    const sampledPosition = sampledPlaybackPositions.get(projectId);
    if (
      sampledPosition !== undefined &&
      project.playbackPositionSeconds === current.playbackPositionSeconds
    ) {
      project = { ...project, playbackPositionSeconds: sampledPosition };
    }

    sampledPlaybackPositions.set(projectId, project.playbackPositionSeconds);
    workspace = {
      ...workspace,
      openProjects: workspace.openProjects.map((candidate) =>
        candidate.id === projectId ? project : candidate,
      ),
    };
    controllers.get(projectId)?.markDirty();
  }

  function samplePlaybackPosition(projectId: string, seconds: number): void {
    if (workspace?.openProjects.some((project) => project.id === projectId)) {
      sampledPlaybackPositions.set(projectId, seconds);
    }
  }

  const registerEditorControl: RegisterVideoEditorControl = (control) => {
    activeEditorControl = control;
    return () => {
      if (activeEditorControl === control) activeEditorControl = null;
    };
  };

  function prepareProjectForSave(projectId: string): VideoEditorControl | null {
    if (activeEditorControl?.projectId === projectId) {
      activeEditorControl.prepareForSave();
      return activeEditorControl;
    }
    return null;
  }

  function prepareActiveProject(): {
    projectId: string;
    control: VideoEditorControl | null;
  } | null {
    const projectId = workspace?.activeProjectId;
    if (projectId === null || projectId === undefined) return null;

    return { projectId, control: prepareProjectForSave(projectId) };
  }

  async function saveActiveProject(): Promise<void> {
    const projectId = workspace?.activeProjectId;
    if (projectId !== null && projectId !== undefined) {
      const control = prepareProjectForSave(projectId);
      try {
        await controllers.get(projectId)?.flush();
      } catch {
        // SaveController exposes the safe failure through its status callback.
      } finally {
        control?.releaseAfterSave();
      }
    }
  }

  function inspectionJobFor(projectId: string): JobRecord | null {
    return newestInspectionJob(jobs, projectId);
  }

  async function loadToolCapabilities(): Promise<void> {
    try {
      const capabilities: Capabilities = await loadCapabilities();
      ffprobeState = capabilities.ffprobeAvailable ? 'ready' : 'unavailable';
    } catch {
      ffprobeState = 'unavailable';
    }
  }

  function startJobEvents(): void {
    closeJobEvents?.();
    closeJobEvents = connectJobEvents({
      onSnapshot: (snapshot) => {
        if (!disposed) jobs = mergeJobSnapshot(jobs, snapshot);
      },
      onWarning: (warning) => {
        if (!disposed) jobConnectionWarning = warning;
      },
    });
  }

  async function initialize(): Promise<void> {
    try {
      applyWorkspace(await loadWorkspace(), false);
      backendState = 'ready';
      void loadToolCapabilities();
      startJobEvents();
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
    const prepared = prepareActiveProject();
    try {
      if (prepared !== null) {
        await controllers.get(prepared.projectId)?.flush();
      }
      const result = await selectImport();
      applyWorkspace(result.workspace);
      if (result.workspace.activeProjectId === prepared?.projectId) {
        prepared.control?.releaseAfterSave();
      }
      void loadToolCapabilities();
    } catch (error) {
      prepared?.control?.releaseAfterSave();
      errorMessage = describeError(error, 'Import failed');
    } finally {
      importing = false;
    }
  }

  async function reopenProject(projectId: string): Promise<void> {
    openingProjectId = projectId;
    errorMessage = null;
    const prepared =
      projectId === workspace?.activeProjectId ? null : prepareActiveProject();
    try {
      if (prepared !== null) {
        await controllers.get(prepared.projectId)?.flush();
      }
      applyWorkspace(await openProject(projectId));
    } catch (error) {
      prepared?.control?.releaseAfterSave();
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
    const prepared = prepareActiveProject();
    try {
      if (prepared !== null) {
        await controllers.get(prepared.projectId)?.flush();
      }
      applyWorkspace(await activateProject(projectId));
    } catch (error) {
      prepared?.control?.releaseAfterSave();
      errorMessage = describeError(error, 'Could not switch videos');
    } finally {
      busyProjectId = null;
    }
  }

  async function saveAndClose(projectId: string): Promise<void> {
    if (busyProjectId !== null) return;

    busyProjectId = projectId;
    errorMessage = null;
    const control = prepareProjectForSave(projectId);
    try {
      await controllers.get(projectId)?.flush();
      const snapshot = await closeProject(documentFor(projectId));
      applyWorkspace(snapshot);
    } catch (error) {
      control?.releaseAfterSave();
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

  async function retryInspection(job: JobRecord): Promise<void> {
    if (retryingJobId !== null) return;

    retryingJobId = job.id;
    errorMessage = null;
    try {
      const updated = await retryJob(job.id);
      jobs =
        jobs === null
          ? { jobs: [updated], errors: [] }
          : mergeJobRecord(jobs, updated);
    } catch (error) {
      errorMessage = describeError(error, 'Could not retry inspection');
    } finally {
      retryingJobId = null;
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
    {ffprobeState}
    {jobCounts}
    {importing}
    onImport={() => void importMp4()}
  />

  {#if ffprobeState === 'unavailable'}
    <div class="tool-warning" role="status">
      FFprobe is unavailable, so video details cannot be inspected. Marking,
      saving, and playback still work.
    </div>
  {/if}

  {#if jobConnectionWarning !== null}
    <div class="connection-warning" role="status">
      {jobConnectionWarning}
    </div>
  {/if}

  {#if jobDataWarning !== null}
    <div class="connection-warning" role="status">
      {jobDataWarning}
    </div>
  {/if}

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
      {inspectionJobFor}
      {retryingJobId}
      onActivate={(projectId) => void switchProject(projectId)}
      onClose={(projectId) => void saveAndClose(projectId)}
      onRetryInspection={(job) => void retryInspection(job)}
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
          {#key activeProject.id}
            <VideoEditor
              project={activeProject}
              onChange={updateProject}
              onPlaybackSample={samplePlaybackPosition}
              registerControl={registerEditorControl}
              onSave={saveActiveProject}
            />
          {/key}
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
