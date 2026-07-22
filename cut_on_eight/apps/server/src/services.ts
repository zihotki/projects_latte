import {
  importSelectionResponseSchema,
  capabilitiesSchema,
  jobSnapshotSchema,
  projectDocumentSchema,
  projectSummarySchema,
  workspaceSnapshotSchema,
  type Capabilities,
  type ImportSelectionResponse,
  type JobRecord,
  type JobSnapshot,
  type ProjectDocument,
  type WorkspaceSnapshot,
} from '@cut-on-eight/contracts';
import { constants } from 'node:fs';
import { open, type FileHandle } from 'node:fs/promises';
import { posix } from 'node:path';
import type { ServerConfig } from './config.js';
import { ApiRouteError } from './http/api-error.js';
import { ImportService } from './imports/import-service.js';
import type { SourcePicker } from './imports/source-picker.js';
import {
  FfprobeRunner,
  type ProbeResult,
  type ProbeRunner,
} from './jobs/ffprobe-runner.js';
import { JobQueue } from './jobs/job-queue.js';
import { JobRepository } from './jobs/job-repository.js';
import { CatalogRepository } from './storage/catalog-repository.js';
import { CorruptPersistedDataError } from './storage/atomic-json.js';
import {
  LibraryRepository,
  type LibraryDocument,
  type LibraryEntry,
} from './storage/library-repository.js';
import { StorageLayout } from './storage/layout.js';
import {
  MissingProjectSidecarError,
  ProjectRepository,
} from './storage/project-repository.js';
import {
  WorkspaceRepository,
  type WorkspaceDocument,
} from './storage/workspace-repository.js';

export interface ManagedSource {
  readonly file: FileHandle;
  readonly size: number;
}

export interface AppServices {
  activateProject(projectId: string): Promise<WorkspaceSnapshot>;
  closeProject(
    projectId: string,
    document: ProjectDocument,
  ): Promise<WorkspaceSnapshot>;
  getCapabilities(): Promise<Capabilities>;
  getJobs(): Promise<JobSnapshot>;
  getWorkspace(): Promise<WorkspaceSnapshot>;
  openProject(projectId: string): Promise<WorkspaceSnapshot>;
  openSource(projectId: string): Promise<ManagedSource>;
  recover(): Promise<void>;
  retryJob(jobId: string): Promise<JobRecord>;
  saveProject(
    projectId: string,
    document: ProjectDocument,
  ): Promise<ProjectDocument>;
  selectImport(): Promise<ImportSelectionResponse>;
  shutdown?(): Promise<void>;
  subscribeToJobs(listener: (snapshot: JobSnapshot) => void): () => void;
}

export interface CreateServicesOptions {
  readonly config: ServerConfig;
  readonly picker: SourcePicker;
  readonly probeRunner?: ProbeRunner;
}

function activeWorkspace(
  workspace: WorkspaceDocument,
  projectId: string,
): WorkspaceDocument {
  return {
    schemaVersion: 1,
    openProjectIds: workspace.openProjectIds.includes(projectId)
      ? [...workspace.openProjectIds]
      : [...workspace.openProjectIds, projectId],
    activeProjectId: projectId,
  };
}

function closedWorkspace(
  workspace: WorkspaceDocument,
  projectId: string,
): WorkspaceDocument {
  const openProjectIds = workspace.openProjectIds.filter(
    (openProjectId) => openProjectId !== projectId,
  );

  return {
    schemaVersion: 1,
    openProjectIds,
    activeProjectId:
      workspace.activeProjectId === projectId
        ? (openProjectIds.at(-1) ?? null)
        : workspace.activeProjectId,
  };
}

function preserveInspectedSource(
  existing: ProjectDocument,
  incoming: ProjectDocument,
): ProjectDocument {
  return {
    ...incoming,
    source: {
      ...incoming.source,
      durationSeconds: existing.source.durationSeconds,
      width: existing.source.width,
      height: existing.source.height,
      frameRateNumerator: existing.source.frameRateNumerator,
      frameRateDenominator: existing.source.frameRateDenominator,
      frameRateReliability: existing.source.frameRateReliability,
      hasAudio: existing.source.hasAudio,
      inspectedAt: existing.source.inspectedAt,
      inspectorVersion: existing.source.inspectorVersion,
    },
  };
}

export function createServices(options: CreateServicesOptions): AppServices {
  const layout = new StorageLayout(options.config.dataRoot);
  const library = new LibraryRepository(layout);
  const projects = new ProjectRepository(layout);
  const workspace = new WorkspaceRepository(layout);
  const catalog = new CatalogRepository(layout, library, workspace);
  const jobs = new JobRepository(layout);
  const imports = new ImportService(layout, {
    catalog,
    jobs,
    library,
    picker: options.picker,
    projects,
    workspace,
  });

  return new ManagedWorkspaceServices(
    layout,
    library,
    projects,
    workspace,
    imports,
    jobs,
    options.probeRunner ?? new FfprobeRunner(),
  );
}

class ManagedWorkspaceServices implements AppServices {
  private operationQueue: Promise<void> = Promise.resolve();
  private readonly jobQueue: JobQueue;

  constructor(
    private readonly layout: StorageLayout,
    private readonly library: LibraryRepository,
    private readonly projects: ProjectRepository,
    private readonly workspace: WorkspaceRepository,
    private readonly imports: ImportService,
    jobs: JobRepository,
    probe: ProbeRunner,
  ) {
    this.jobQueue = new JobQueue(
      layout,
      library,
      jobs,
      probe,
      (projectId, metadata) => this.updateSourceMetadata(projectId, metadata),
      () => this.imports.reconcileThumbnailJobs(),
    );
  }

  async recover(): Promise<void> {
    const importRecoveryIssues = await this.enqueue(() =>
      this.imports.recover(),
    );
    await this.jobQueue.recover([...importRecoveryIssues]);
  }

  async getCapabilities(): Promise<Capabilities> {
    return capabilitiesSchema.parse({
      backendAvailable: true,
      ffprobeAvailable: await this.jobQueue.isProbeAvailable(),
    });
  }

  async getJobs(): Promise<JobSnapshot> {
    return jobSnapshotSchema.parse(await this.jobQueue.refresh());
  }

  async retryJob(jobId: string): Promise<JobRecord> {
    try {
      return await this.jobQueue.retry(jobId);
    } catch (error) {
      const code = error instanceof Error ? error.message : '';
      if (code === 'job_not_found') {
        throw new ApiRouteError(
          404,
          code,
          'The inspection job was not found.',
          false,
        );
      }
      if (code === 'job_not_retryable' || code === 'job_attempts_exhausted') {
        throw new ApiRouteError(
          409,
          code,
          'The inspection job cannot be retried.',
          false,
        );
      }
      throw error;
    }
  }

  subscribeToJobs(listener: (snapshot: JobSnapshot) => void): () => void {
    return this.jobQueue.subscribe(listener);
  }

  async shutdown(): Promise<void> {
    const stoppingJobs = this.jobQueue.shutdown();
    await this.enqueue(async () => undefined);
    await stoppingJobs;
    await this.enqueue(async () => undefined);
  }

  getWorkspace(): Promise<WorkspaceSnapshot> {
    return this.enqueue(() => this.snapshot());
  }

  async selectImport(): Promise<ImportSelectionResponse> {
    const selectedPath = await this.imports.selectSource();

    if (selectedPath === null) {
      return this.enqueue(async () =>
        importSelectionResponseSchema.parse({
          outcome: 'cancelled',
          workspace: await this.snapshot(),
        }),
      );
    }

    return this.enqueue(async () => {
      const result = await this.imports.importSelected(selectedPath);
      const workspaceSnapshot = await this.snapshot();
      await this.jobQueue.refresh();

      return importSelectionResponseSchema.parse({
        ...result,
        workspace: workspaceSnapshot,
      });
    });
  }

  openProject(projectId: string): Promise<WorkspaceSnapshot> {
    return this.enqueue(async () => {
      const entry = await this.requireLibraryEntry(projectId);
      try {
        await this.projects.readRequired(entry.id, entry.managedSourcePath);
      } catch (error) {
        if (isUnavailableSidecar(error)) {
          throw new ApiRouteError(
            500,
            'project_data_unavailable',
            'The managed project data is missing or corrupt.',
            false,
            { projectId },
          );
        }
        throw error;
      }
      const current = await this.workspace.read();
      await this.workspace.save(activeWorkspace(current, projectId));
      return this.snapshot();
    });
  }

  activateProject(projectId: string): Promise<WorkspaceSnapshot> {
    return this.enqueue(async () => {
      await this.requireLibraryEntry(projectId);
      const current = await this.workspace.read();

      if (!current.openProjectIds.includes(projectId)) {
        throw new ApiRouteError(
          409,
          'project_not_open',
          'The project must be open before it can be activated.',
          false,
          { projectId },
        );
      }

      await this.workspace.save({ ...current, activeProjectId: projectId });
      return this.snapshot();
    });
  }

  saveProject(
    projectId: string,
    document: ProjectDocument,
  ): Promise<ProjectDocument> {
    return this.enqueue(async () => {
      const validated = projectDocumentSchema.parse(document);
      const entry = await this.requireLibraryEntry(projectId);
      const existing = await this.projects.readRequired(
        projectId,
        entry.managedSourcePath,
      );
      const persisted = preserveInspectedSource(existing, validated);
      await this.projects.save(projectId, entry.managedSourcePath, persisted);
      return persisted;
    });
  }

  closeProject(
    projectId: string,
    document: ProjectDocument,
  ): Promise<WorkspaceSnapshot> {
    return this.enqueue(async () => {
      const validated = projectDocumentSchema.parse(document);
      const library = await this.library.read();
      const entry = this.findLibraryEntry(library, projectId);
      const current = await this.workspace.read();

      if (!current.openProjectIds.includes(projectId)) {
        throw new ApiRouteError(
          409,
          'project_not_open',
          'The project is not open.',
          false,
          { projectId },
        );
      }

      const existing = await this.projects.readRequired(
        projectId,
        entry.managedSourcePath,
      );
      const persisted = preserveInspectedSource(existing, validated);
      const nextWorkspace = closedWorkspace(current, projectId);
      const response = await this.snapshot(
        { library, workspace: nextWorkspace },
        new Map([[projectId, persisted]]),
      );
      await this.projects.save(projectId, entry.managedSourcePath, persisted);
      await this.workspace.save(nextWorkspace);
      return response;
    });
  }

  async openSource(projectId: string): Promise<ManagedSource> {
    const entry = await this.requireLibraryEntry(projectId);
    const sourcePath = this.layout.resolveManagedRelativePath(
      entry.managedSourcePath,
    );
    await this.layout.assertNoSymlinkComponents(sourcePath);
    let file: FileHandle;

    try {
      file = await open(sourcePath, constants.O_RDONLY | constants.O_NOFOLLOW);
    } catch {
      throw new ApiRouteError(
        404,
        'source_unavailable',
        'The managed video source is unavailable.',
        false,
        { projectId },
      );
    }

    try {
      const status = await file.stat();

      if (!status.isFile() || !Number.isSafeInteger(status.size)) {
        throw new Error('Managed source is not a regular file');
      }

      return { file, size: status.size };
    } catch (error) {
      await file.close().catch(() => undefined);

      if (error instanceof ApiRouteError) {
        throw error;
      }

      throw new ApiRouteError(
        404,
        'source_unavailable',
        'The managed video source is unavailable.',
        false,
        { projectId },
      );
    }
  }

  private enqueue<T>(operation: () => Promise<T>): Promise<T> {
    const result = this.operationQueue.then(operation);
    this.operationQueue = result.then(
      () => undefined,
      () => undefined,
    );
    return result;
  }

  private updateSourceMetadata(
    projectId: string,
    metadata: ProbeResult,
  ): Promise<void> {
    return this.enqueue(async () => {
      const entry = await this.requireLibraryEntry(projectId);
      const project = await this.projects.readRequired(
        projectId,
        entry.managedSourcePath,
      );
      await this.projects.save(projectId, entry.managedSourcePath, {
        ...project,
        source: {
          ...project.source,
          durationSeconds: metadata.durationSeconds,
          width: metadata.width,
          height: metadata.height,
          frameRateNumerator: metadata.frameRateNumerator,
          frameRateDenominator: metadata.frameRateDenominator,
          frameRateReliability: metadata.frameRateReliability,
          hasAudio: metadata.hasAudio,
          inspectedAt: new Date().toISOString(),
          inspectorVersion: 'ffprobe-v1',
        },
      });
    });
  }

  private async requireLibraryEntry(projectId: string): Promise<LibraryEntry> {
    const library = await this.library.read();
    return this.findLibraryEntry(library, projectId);
  }

  private findLibraryEntry(
    library: LibraryDocument,
    projectId: string,
  ): LibraryEntry {
    const entry = library.entries.find(
      (candidate) => candidate.id === projectId,
    );

    if (entry === undefined) {
      throw new ApiRouteError(
        404,
        'project_not_found',
        'The managed project was not found.',
        false,
        { projectId },
      );
    }

    return entry;
  }

  private async snapshot(
    state?: {
      readonly library: LibraryDocument;
      readonly workspace: WorkspaceDocument;
    },
    projectOverrides: ReadonlyMap<string, ProjectDocument> = new Map(),
  ): Promise<WorkspaceSnapshot> {
    let resolvedState = state;

    if (resolvedState === undefined) {
      const [library, workspace] = await Promise.all([
        this.library.read(),
        this.workspace.read(),
      ]);
      resolvedState = { library, workspace };
    }

    const { library, workspace } = resolvedState;
    const projectsById = await this.readLibraryProjects(
      library,
      new Set(workspace.openProjectIds),
      projectOverrides,
    );
    const openProjects = workspace.openProjectIds.map((projectId) => {
      const project = projectsById.get(projectId);

      if (project === undefined) {
        throw new ApiRouteError(
          500,
          'workspace_project_missing',
          'The saved workspace refers to a missing managed project.',
          false,
          { projectId },
        );
      }

      return project;
    });
    const summaries = library.entries.map((entry) => {
      const project = projectsById.get(entry.id);

      return projectSummarySchema.parse({
        id: entry.id,
        fileName:
          project?.source.fileName ?? posix.basename(entry.managedSourcePath),
        durationSeconds: project?.source.durationSeconds ?? null,
      });
    });

    return workspaceSnapshotSchema.parse({
      activeProjectId: workspace.activeProjectId,
      openProjects,
      library: summaries,
    });
  }

  private async readLibraryProjects(
    library: LibraryDocument,
    openProjectIds: ReadonlySet<string>,
    projectOverrides: ReadonlyMap<string, ProjectDocument>,
  ): Promise<Map<string, ProjectDocument>> {
    const entries = await Promise.all(
      library.entries.map(async (entry) => {
        const projectOverride = projectOverrides.get(entry.id);
        if (projectOverride !== undefined) {
          return [entry.id, projectOverride] as const;
        }

        let project: ProjectDocument;
        try {
          project = await this.projects.readRequired(
            entry.id,
            entry.managedSourcePath,
          );
        } catch (error) {
          if (!isUnavailableSidecar(error)) throw error;
          if (!openProjectIds.has(entry.id)) return undefined;
          throw new ApiRouteError(
            500,
            'workspace_project_unavailable',
            'An open managed project is missing or corrupt.',
            false,
            { projectId: entry.id },
          );
        }
        return [entry.id, project] as const;
      }),
    );

    return new Map(entries.filter((entry) => entry !== undefined));
  }
}

function isUnavailableSidecar(
  error: unknown,
): error is CorruptPersistedDataError | MissingProjectSidecarError {
  return (
    error instanceof CorruptPersistedDataError ||
    error instanceof MissingProjectSidecarError
  );
}
