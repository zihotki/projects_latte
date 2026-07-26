import type {
  ProjectDocument,
  Segment,
  WorkspaceSnapshot,
} from '../domain/editor-model.js';
import { SvelteMap } from 'svelte/reactivity';
import type {
  RegisterVideoEditorControl,
  VideoEditorControl,
} from '../lib/editor-control.js';
import {
  SaveController,
  type SaveState,
  type SaveStatus,
} from '../lib/save-controller.js';

export interface WorkspaceApi {
  loadWorkspace(): Promise<WorkspaceSnapshot>;
  importVideo?(file: File): Promise<WorkspaceSnapshot>;
  selectImport?(): Promise<{
    outcome: 'cancelled' | 'imported' | 'already-open';
    workspace: WorkspaceSnapshot;
  }>;
  openProject(projectId: string): Promise<WorkspaceSnapshot>;
  activateProject(projectId: string): Promise<WorkspaceSnapshot>;
  saveProject(project: ProjectDocument): Promise<ProjectDocument>;
  closeProject(project: ProjectDocument): Promise<WorkspaceSnapshot>;
  deleteProject(
    projectId: string,
    expectedRevision: number,
  ): Promise<WorkspaceSnapshot>;
}

export interface WorkspacePort {
  hasOpenProject(projectId: string): boolean;
  flushProject(projectId: string): Promise<void>;
  fragmentFor(
    projectId: string,
    fragmentId: string,
  ): { segment: Segment; index: number } | null;
  patchSegment(projectId: string, segment: Segment): void;
  removeSegment(projectId: string, fragmentId: string): void;
  restoreSegment(projectId: string, segment: Segment, index: number): void;
  deleteManagedVideo(projectId: string): Promise<void>;
}

export interface WorkspaceSessionCallbacks {
  readonly onWorkspaceApplied?: (snapshot: WorkspaceSnapshot) => void;
  readonly onProjectOpened?: (projectId: string) => void;
  readonly onImported?: () => void;
  readonly onImportOutcome?: (
    outcome: 'cancelled' | 'imported' | 'already-open',
  ) => void;
}

export type ProjectMutation = (project: ProjectDocument) => ProjectDocument;

export class WorkspaceSession implements WorkspacePort {
  workspace = $state.raw<WorkspaceSnapshot | null>(null);
  loading = $state(true);
  importing = $state(false);
  openingProjectId = $state<string | null>(null);
  busyProjectId = $state<string | null>(null);
  errorMessage = $state<string | null>(null);
  saveStates = $state<Record<string, SaveState>>({});
  saveErrors = $state<Record<string, string>>({});
  retryingProjectId = $state<string | null>(null);

  private readonly controllers = new SvelteMap<string, SaveController>();
  private readonly sampledPlaybackPositions = new SvelteMap<string, number>();
  private activeEditorControl: VideoEditorControl | null = null;
  private disposed = false;

  constructor(
    private readonly api: WorkspaceApi,
    private readonly callbacks: WorkspaceSessionCallbacks = {},
  ) {}

  get activeProject(): ProjectDocument | null {
    return (
      this.workspace?.openProjects.find(
        (project) => project.id === this.workspace?.activeProjectId,
      ) ?? null
    );
  }

  get openProjectIds(): ReadonlySet<string> {
    return new Set(
      this.workspace?.openProjects.map((project) => project.id) ?? [],
    );
  }

  async initialize(): Promise<WorkspaceSnapshot> {
    try {
      const snapshot = await this.api.loadWorkspace();
      this.applyWorkspace(snapshot, false);
      return snapshot;
    } catch (error) {
      this.errorMessage = describeError(error, 'Could not load the workspace');
      throw error;
    } finally {
      this.loading = false;
    }
  }

  async importMp4(file?: File): Promise<boolean> {
    this.importing = true;
    this.errorMessage = null;
    const prepared = this.prepareActiveProject();
    try {
      if (prepared !== null) {
        await this.controllers.get(prepared.projectId)?.flush();
      }
      const legacy =
        file === undefined ? await this.api.selectImport?.() : undefined;
      const snapshot =
        legacy?.workspace ??
        (file === undefined || this.api.importVideo === undefined
          ? null
          : await this.api.importVideo(file));
      if (snapshot === null || snapshot === undefined) return false;
      this.applyWorkspace(snapshot);
      if (snapshot.activeProjectId === prepared?.projectId) {
        prepared.control?.releaseAfterSave();
      }
      this.callbacks.onImported?.();
      if (legacy !== undefined)
        this.callbacks.onImportOutcome?.(legacy.outcome);
      return legacy?.outcome !== 'cancelled';
    } catch (error) {
      prepared?.control?.releaseAfterSave();
      this.errorMessage = describeError(error, 'Import failed');
      return false;
    } finally {
      this.importing = false;
    }
  }

  async reopenProject(projectId: string): Promise<boolean> {
    this.openingProjectId = projectId;
    this.errorMessage = null;
    const prepared =
      projectId === this.workspace?.activeProjectId
        ? null
        : this.prepareActiveProject();
    try {
      if (prepared !== null) {
        await this.controllers.get(prepared.projectId)?.flush();
      }
      this.applyWorkspace(await this.api.openProject(projectId));
      this.callbacks.onProjectOpened?.(projectId);
      return true;
    } catch (error) {
      prepared?.control?.releaseAfterSave();
      this.errorMessage = describeError(error, 'Could not reopen the video');
      return false;
    } finally {
      this.openingProjectId = null;
    }
  }

  async switchProject(projectId: string): Promise<void> {
    if (
      projectId === this.workspace?.activeProjectId ||
      this.busyProjectId !== null
    ) {
      return;
    }
    this.busyProjectId = projectId;
    this.errorMessage = null;
    const prepared = this.prepareActiveProject();
    try {
      if (prepared !== null) {
        await this.controllers.get(prepared.projectId)?.flush();
      }
      this.applyWorkspace(await this.api.activateProject(projectId));
    } catch (error) {
      prepared?.control?.releaseAfterSave();
      this.errorMessage = describeError(error, 'Could not switch videos');
    } finally {
      this.busyProjectId = null;
    }
  }

  async saveAndClose(projectId: string): Promise<void> {
    if (this.busyProjectId !== null) return;
    this.busyProjectId = projectId;
    this.errorMessage = null;
    const control = this.prepareProjectForSave(projectId);
    try {
      await this.controllers.get(projectId)?.flush();
      this.applyWorkspace(
        await this.api.closeProject(this.documentFor(projectId)),
      );
    } catch (error) {
      control?.releaseAfterSave();
      this.errorMessage = describeError(
        error,
        'Could not save and close the video',
      );
    } finally {
      this.busyProjectId = null;
    }
  }

  async deleteManagedVideo(projectId: string): Promise<void> {
    await this.flushProject(projectId);
    const revision =
      this.workspace?.openProjects.find((project) => project.id === projectId)
        ?.revision ??
      this.workspace?.library.find((project) => project.id === projectId)
        ?.revision ??
      0;
    this.applyWorkspace(
      await this.api.deleteProject(projectId, revision),
      false,
    );
  }

  updateProject(projectId: string, mutate: ProjectMutation): void {
    if (this.workspace === null) return;
    const current = this.workspace.openProjects.find(
      (candidate) => candidate.id === projectId,
    );
    if (current === undefined) return;
    let project = mutate(current);
    if (project === current) return;
    const sampledPosition = this.sampledPlaybackPositions.get(projectId);
    if (
      sampledPosition !== undefined &&
      project.playbackPositionSeconds === current.playbackPositionSeconds
    ) {
      project = { ...project, playbackPositionSeconds: sampledPosition };
    }
    this.sampledPlaybackPositions.set(
      projectId,
      project.playbackPositionSeconds,
    );
    this.workspace = {
      ...this.workspace,
      openProjects: this.workspace.openProjects.map((candidate) =>
        candidate.id === projectId ? project : candidate,
      ),
    };
    this.controllers.get(projectId)?.markDirty();
  }

  samplePlaybackPosition(projectId: string, seconds: number): void {
    if (this.hasOpenProject(projectId)) {
      this.sampledPlaybackPositions.set(projectId, seconds);
    }
  }

  readonly registerEditorControl: RegisterVideoEditorControl = (control) => {
    this.activeEditorControl = control;
    return () => {
      if (this.activeEditorControl === control) this.activeEditorControl = null;
    };
  };

  async saveActiveProject(): Promise<void> {
    const projectId = this.workspace?.activeProjectId;
    if (projectId === null || projectId === undefined) return;
    const control = this.prepareProjectForSave(projectId);
    try {
      await this.controllers.get(projectId)?.flush();
    } catch {
      // SaveController publishes the safe failure through its status callback.
    } finally {
      control?.releaseAfterSave();
    }
  }

  async retryAutosave(projectId: string): Promise<void> {
    this.retryingProjectId = projectId;
    try {
      await this.controllers.get(projectId)?.retry();
    } catch {
      // SaveController publishes the safe failure through its status callback.
    } finally {
      this.retryingProjectId = null;
    }
  }

  hasOpenProject(projectId: string): boolean {
    return (
      this.workspace?.openProjects.some(
        (project) => project.id === projectId,
      ) ?? false
    );
  }

  async flushProject(projectId: string): Promise<void> {
    await this.controllers.get(projectId)?.flush();
  }

  fragmentFor(
    projectId: string,
    fragmentId: string,
  ): { segment: Segment; index: number } | null {
    const project = this.workspace?.openProjects.find(
      (candidate) => candidate.id === projectId,
    );
    const index =
      project?.segments.findIndex((segment) => segment.id === fragmentId) ?? -1;
    const segment = project?.segments[index];
    return segment === undefined ? null : { segment, index };
  }

  patchSegment(projectId: string, segment: Segment): void {
    this.patchOpenProject(projectId, (project) => ({
      ...project,
      segments: project.segments.map((item) =>
        item.id === segment.id ? segment : item,
      ),
    }));
  }

  removeSegment(projectId: string, fragmentId: string): void {
    this.patchOpenProject(projectId, (project) => ({
      ...project,
      selectedSegmentId:
        project.selectedSegmentId === fragmentId
          ? null
          : project.selectedSegmentId,
      segments: project.segments.filter((segment) => segment.id !== fragmentId),
    }));
  }

  restoreSegment(projectId: string, segment: Segment, index: number): void {
    this.patchOpenProject(projectId, (project) => {
      const segments = [...project.segments];
      segments.splice(Math.min(index, segments.length), 0, segment);
      return { ...project, segments };
    });
  }

  documentFor(projectId: string): ProjectDocument {
    const project = this.workspace?.openProjects.find(
      (candidate) => candidate.id === projectId,
    );
    if (project === undefined)
      throw new Error('The project is no longer open.');
    const sampledPosition = this.sampledPlaybackPositions.get(projectId);
    return sampledPosition === undefined
      ? project
      : { ...project, playbackPositionSeconds: sampledPosition };
  }

  projectName(projectId: string): string {
    return (
      this.workspace?.openProjects.find((project) => project.id === projectId)
        ?.source.fileName ?? 'Project'
    );
  }

  saveStateFor(projectId: string): SaveState {
    return this.saveStates[projectId] ?? 'saved';
  }

  applyWorkspace(snapshot: WorkspaceSnapshot, preserveEdits = true): void {
    if (this.disposed) return;
    const currentProjects = new Map(
      preserveEdits
        ? this.workspace?.openProjects.map((project) => [
            project.id,
            this.documentFor(project.id),
          ])
        : [],
    );
    this.workspace = {
      ...snapshot,
      openProjects: snapshot.openProjects.map((project) => {
        const current = currentProjects.get(project.id);
        if (
          current === undefined ||
          this.saveStateFor(project.id) === 'saved'
        ) {
          return project;
        }
        return mergeUnsavedEditor(current, project);
      }),
    };
    this.ensureControllers();
    this.callbacks.onWorkspaceApplied?.(this.workspace);
  }

  clearError(): void {
    this.errorMessage = null;
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    for (const controller of this.controllers.values()) controller.cancel();
    this.controllers.clear();
    this.sampledPlaybackPositions.clear();
    this.activeEditorControl = null;
  }

  private patchOpenProject(
    projectId: string,
    patch: (project: ProjectDocument) => ProjectDocument,
  ): void {
    if (this.workspace === null || !this.hasOpenProject(projectId)) return;
    this.workspace = {
      ...this.workspace,
      openProjects: this.workspace.openProjects.map((project) =>
        project.id === projectId ? patch(project) : project,
      ),
    };
  }

  private updateSaveStatus(projectId: string, status: SaveStatus): void {
    this.saveStates = { ...this.saveStates, [projectId]: status.state };
    const nextErrors = { ...this.saveErrors };
    if (status.state === 'failed' && status.error !== null) {
      nextErrors[projectId] = status.error;
    } else {
      delete nextErrors[projectId];
    }
    this.saveErrors = nextErrors;
  }

  private ensureControllers(): void {
    const liveIds = new Set(
      this.workspace?.openProjects.map((project) => project.id) ?? [],
    );
    for (const [projectId, controller] of this.controllers) {
      if (!liveIds.has(projectId)) {
        controller.cancel();
        this.controllers.delete(projectId);
        this.sampledPlaybackPositions.delete(projectId);
      }
    }
    for (const projectId of liveIds) {
      if (this.controllers.has(projectId)) continue;
      this.saveStates = { ...this.saveStates, [projectId]: 'saved' };
      this.controllers.set(
        projectId,
        new SaveController({
          save: async () => {
            const saved = await this.api.saveProject(
              this.documentFor(projectId),
            );
            this.patchOpenProject(projectId, (current) => ({
              ...current,
              revision: saved.revision,
              segments: current.segments.map((segment) => {
                const synchronized = saved.segments.find(
                  ({ id }) => id === segment.id,
                );
                return synchronized === undefined
                  ? segment
                  : { ...segment, revision: synchronized.revision };
              }),
            }));
          },
          onStatusChange: (status) => this.updateSaveStatus(projectId, status),
        }),
      );
    }
  }

  private prepareProjectForSave(projectId: string): VideoEditorControl | null {
    if (this.activeEditorControl?.projectId === projectId) {
      this.activeEditorControl.prepareForSave();
      return this.activeEditorControl;
    }
    return null;
  }

  private prepareActiveProject(): {
    projectId: string;
    control: VideoEditorControl | null;
  } | null {
    const projectId = this.workspace?.activeProjectId;
    return projectId === null || projectId === undefined
      ? null
      : { projectId, control: this.prepareProjectForSave(projectId) };
  }
}

function mergeUnsavedEditor(
  local: ProjectDocument,
  authoritative: ProjectDocument,
): ProjectDocument {
  const remoteSegments = new Map(
    authoritative.segments.map((segment) => [segment.id, segment]),
  );
  return {
    ...authoritative,
    revision: Math.max(authoritative.revision ?? 0, local.revision ?? 0),
    playbackPositionSeconds: local.playbackPositionSeconds,
    selectedSegmentId: local.selectedSegmentId,
    settings: local.settings,
    metadata: local.metadata,
    editor: local.editor,
    segments: local.segments.map((segment) => {
      const remote = remoteSegments.get(segment.id);
      return remote === undefined
        ? segment
        : {
            ...segment,
            revision: Math.max(remote.revision ?? 0, segment.revision ?? 0),
          };
    }),
  };
}

function describeError(error: unknown, action: string): string {
  return error instanceof Error
    ? `${action}: ${error.message}`
    : `${action}: unknown error`;
}
