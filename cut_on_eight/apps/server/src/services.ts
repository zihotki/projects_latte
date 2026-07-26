import {
  importSelectionResponseSchema,
  capabilitiesSchema,
  frameStepSeconds,
  segmentSchema,
  tagDefinitionSchema,
  jobSnapshotSchema,
  projectDocumentSchema,
  projectSummarySchema,
  workspaceSnapshotSchema,
  type Capabilities,
  type ImportSelectionResponse,
  type DeletedFragment,
  type FragmentCatalogue,
  type FragmentMutation,
  type JobRecord,
  type JobSnapshot,
  type ProjectDocument,
  type Segment,
  type TagDefinition,
  type ThumbnailManifestV1,
  type WorkspaceSnapshot,
} from '@cut-on-eight/legacy-contracts';
import { constants } from 'node:fs';
import { randomUUID } from 'node:crypto';
import { open, type FileHandle } from 'node:fs/promises';
import { posix, resolve } from 'node:path';
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
import { FfmpegRunner } from './jobs/ffmpeg-runner.js';
import { thumbnailJobIdentity } from './jobs/thumbnail-job.js';
import { CatalogRepository } from './storage/catalog-repository.js';
import { CatalogueMetadataRepository } from './storage/catalogue-metadata-repository.js';
import { ProjectDeletion } from './storage/project-deletion.js';
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
import {
  ThumbnailWorker,
  type ThumbnailGenerator,
} from './thumbnails/thumbnail-worker.js';
import { readCompatibleThumbnailManifest } from './thumbnails/thumbnail-manifest.js';
import {
  catalogueResponse,
  orderedSegments,
  selectFragmentPreviews,
  validateFragmentTiming,
} from './fragments/fragment-catalogue.js';

export interface ManagedSource {
  readonly file: FileHandle;
  readonly size: number;
}

export interface ManagedThumbnailPage {
  readonly file: FileHandle;
  readonly size: number;
}

export interface AppServices {
  activateProject(projectId: string): Promise<WorkspaceSnapshot>;
  closeProject(
    projectId: string,
    document: ProjectDocument,
  ): Promise<WorkspaceSnapshot>;
  createTag(name: string): Promise<TagDefinition>;
  deleteFragment(
    projectId: string,
    fragmentId: string,
  ): Promise<DeletedFragment>;
  deleteProject(projectId: string): Promise<WorkspaceSnapshot>;
  getCapabilities(): Promise<Capabilities>;
  getJobs(): Promise<JobSnapshot>;
  getFragments(): Promise<FragmentCatalogue>;
  getTags(): Promise<TagDefinition[]>;
  getThumbnailManifest(projectId: string): Promise<ThumbnailManifestV1>;
  getWorkspace(): Promise<WorkspaceSnapshot>;
  openProject(projectId: string): Promise<WorkspaceSnapshot>;
  openSource(projectId: string): Promise<ManagedSource>;
  openThumbnailPage(
    projectId: string,
    fileName: string,
  ): Promise<ManagedThumbnailPage>;
  recover(): Promise<void>;
  retryJob(jobId: string): Promise<JobRecord>;
  restoreFragment(
    projectId: string,
    fragmentId: string,
    deleted: DeletedFragment,
  ): Promise<Segment>;
  saveProject(
    projectId: string,
    document: ProjectDocument,
  ): Promise<ProjectDocument>;
  selectImport(): Promise<ImportSelectionResponse>;
  shutdown?(): Promise<void>;
  subscribeToJobs(listener: (snapshot: JobSnapshot) => void): () => void;
  updateFragment(
    projectId: string,
    fragmentId: string,
    mutation: FragmentMutation,
  ): Promise<Segment>;
}

export interface CreateServicesOptions {
  readonly config: ServerConfig;
  readonly picker: SourcePicker;
  readonly probeRunner?: ProbeRunner;
  readonly thumbnailGenerator?: ThumbnailGenerator;
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
  const catalogueMetadata = new CatalogueMetadataRepository(layout);
  const jobs = new JobRepository(layout);
  const imports = new ImportService(layout, {
    catalog,
    jobs,
    library,
    picker: options.picker,
    projects,
    workspace,
  });
  const projectDeletion = new ProjectDeletion(
    layout,
    library,
    workspace,
    catalog,
  );

  return new ManagedWorkspaceServices(
    layout,
    library,
    projects,
    workspace,
    imports,
    jobs,
    catalogueMetadata,
    projectDeletion,
    options.probeRunner ?? new FfprobeRunner(),
    options.thumbnailGenerator ?? new ThumbnailWorker(new FfmpegRunner()),
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
    private readonly catalogueMetadata: CatalogueMetadataRepository,
    private readonly projectDeletion: ProjectDeletion,
    probe: ProbeRunner,
    thumbnailGenerator: ThumbnailGenerator,
  ) {
    this.jobQueue = new JobQueue(
      layout,
      library,
      jobs,
      probe,
      (projectId, metadata) => this.updateSourceMetadata(projectId, metadata),
      () => this.imports.reconcileThumbnailJobs(),
      thumbnailGenerator,
      (projectId) => this.loadThumbnailContext(projectId),
    );
  }

  async recover(): Promise<void> {
    await this.enqueue(() => this.projectDeletion.recover());
    const importRecoveryIssues = await this.enqueue(() =>
      this.imports.recover(),
    );
    await this.jobQueue.recover([...importRecoveryIssues]);
  }

  async deleteProject(projectId: string): Promise<WorkspaceSnapshot> {
    try {
      await this.jobQueue.stopProject(projectId);
      return await this.enqueue(async () => {
        const library = await this.library.read();
        const entry = library.entries.find(
          (candidate) => candidate.id === projectId,
        );
        if (entry === undefined) return this.snapshot();
        await this.projectDeletion.delete(entry);
        return this.snapshot();
      });
    } finally {
      this.jobQueue.resumeProject(projectId);
    }
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

  getFragments(): Promise<FragmentCatalogue> {
    return Promise.all([
      this.library.read(),
      this.catalogueMetadata.read(),
    ]).then(async ([library, metadata]) => {
      const jobs = this.jobQueue.snapshot().jobs;
      const results = await Promise.all(
        library.entries.map(async (entry) => {
          const fragments: FragmentCatalogue['fragments'] = [];
          const diagnostics: FragmentCatalogue['diagnostics'] = [];
          let project: ProjectDocument;
          try {
            project = await this.projects.readRequired(
              entry.id,
              entry.managedSourcePath,
            );
          } catch (error) {
            if (!isUnavailableSidecar(error)) throw error;
            diagnostics.push({
              projectId: entry.id,
              sourceFileName: posix.basename(entry.managedSourcePath),
              message: 'Managed project data is unavailable.',
            });
            return { fragments, diagnostics };
          }

          const durationSeconds = project.source.durationSeconds;
          const identity = thumbnailJobIdentity(entry.fingerprint);
          const manifest =
            durationSeconds === null
              ? undefined
              : await readCompatibleThumbnailManifest(
                  this.layout.thumbnailsDirectory(entry.managedSourcePath),
                  { ...identity, durationSeconds },
                );
          const thumbnailJob = jobs
            .filter(
              (job) =>
                job.projectId === entry.id &&
                job.type === 'generate-thumbnails',
            )
            .sort((left, right) =>
              right.updatedAt.localeCompare(left.updatedAt),
            )[0];
          const step = frameStepSeconds(project.source);
          const thumbnailState =
            manifest !== undefined
              ? 'ready'
              : thumbnailJob?.state === 'failed'
                ? 'failed'
                : thumbnailJob?.state === 'queued' ||
                    thumbnailJob?.state === 'running'
                  ? 'generating'
                  : 'unavailable';
          for (const [index, segment] of orderedSegments(project).entries()) {
            fragments.push({
              projectId: entry.id,
              sourceFileName: project.source.fileName,
              sourceDurationSeconds: durationSeconds,
              ordinal: index + 1,
              segment,
              previews: selectFragmentPreviews(segment, manifest),
              thumbnailState,
              thumbnailJobId: thumbnailJob?.id ?? null,
              frameStepSeconds: step.seconds,
              frameStepApproximate: step.approximate,
            });
          }
          return { fragments, diagnostics };
        }),
      );

      const fragments = results
        .flatMap((result) => result.fragments)
        .sort(
          (left, right) =>
            left.sourceFileName.localeCompare(right.sourceFileName) ||
            left.ordinal - right.ordinal,
        );
      return catalogueResponse({
        fragments,
        tags: metadata.tags,
        diagnostics: results.flatMap((result) => result.diagnostics),
      });
    });
  }

  async getTags(): Promise<TagDefinition[]> {
    return (await this.catalogueMetadata.read()).tags;
  }

  createTag(name: string): Promise<TagDefinition> {
    return this.enqueue(async () => {
      const normalized = name.trim().toLowerCase();
      const metadata = await this.catalogueMetadata.read();
      const existing = metadata.tags.find((tag) => tag.name === normalized);
      if (existing !== undefined) return existing;
      const tag = tagDefinitionSchema.parse({
        id: randomUUID(),
        name: normalized,
      });
      await this.catalogueMetadata.save({
        ...metadata,
        tags: [...metadata.tags, tag].sort((left, right) =>
          left.name.localeCompare(right.name),
        ),
      });
      return tag;
    });
  }

  updateFragment(
    projectId: string,
    fragmentId: string,
    mutation: FragmentMutation,
  ): Promise<Segment> {
    return this.enqueue(async () => {
      const { entry, project } = await this.loadThumbnailProject(projectId);
      const index = project.segments.findIndex(
        (segment) => segment.id === fragmentId,
      );
      if (index < 0) throw fragmentNotFound(projectId, fragmentId);
      const metadata = await this.catalogueMetadata.read();
      const knownTags = new Set(metadata.tags.map((tag) => tag.id));
      if (mutation.tagIds.some((tagId) => !knownTags.has(tagId))) {
        throw new ApiRouteError(
          400,
          'unknown_tag',
          'The fragment contains an unknown tag.',
          false,
        );
      }
      const segment = segmentSchema.parse({ id: fragmentId, ...mutation });
      const issue = validateFragmentTiming(
        project.segments,
        segment,
        project.source.durationSeconds,
      );
      if (issue !== null)
        throw new ApiRouteError(409, issue.code, issue.message, false);
      const segments = [...project.segments];
      segments[index] = segment;
      await this.projects.save(projectId, entry.managedSourcePath, {
        ...project,
        segments,
      });
      return segment;
    });
  }

  deleteFragment(
    projectId: string,
    fragmentId: string,
  ): Promise<DeletedFragment> {
    return this.enqueue(async () => {
      const { entry, project } = await this.loadThumbnailProject(projectId);
      const index = project.segments.findIndex(
        (segment) => segment.id === fragmentId,
      );
      if (index < 0) throw fragmentNotFound(projectId, fragmentId);
      const fragment = project.segments[index];
      if (fragment === undefined) throw fragmentNotFound(projectId, fragmentId);
      await this.projects.save(projectId, entry.managedSourcePath, {
        ...project,
        selectedSegmentId:
          project.selectedSegmentId === fragmentId
            ? null
            : project.selectedSegmentId,
        segments: project.segments.filter(
          (segment) => segment.id !== fragmentId,
        ),
      });
      return { projectId, index, fragment };
    });
  }

  restoreFragment(
    projectId: string,
    fragmentId: string,
    deleted: DeletedFragment,
  ): Promise<Segment> {
    return this.enqueue(async () => {
      if (
        deleted.projectId !== projectId ||
        deleted.fragment.id !== fragmentId
      ) {
        throw new ApiRouteError(
          400,
          'invalid_restore',
          'The deleted fragment snapshot does not match.',
          false,
        );
      }
      const { entry, project } = await this.loadThumbnailProject(projectId);
      const existing = project.segments.find(
        (segment) => segment.id === fragmentId,
      );
      if (existing !== undefined) return existing;
      const issue = validateFragmentTiming(
        project.segments,
        deleted.fragment,
        project.source.durationSeconds,
      );
      if (issue !== null)
        throw new ApiRouteError(409, issue.code, issue.message, false);
      const metadata = await this.catalogueMetadata.read();
      const knownTags = new Set(metadata.tags.map((tag) => tag.id));
      if (deleted.fragment.tagIds.some((tagId) => !knownTags.has(tagId))) {
        throw new ApiRouteError(
          409,
          'unknown_tag',
          'A deleted fragment tag no longer exists.',
          false,
        );
      }
      const segments = [...project.segments];
      segments.splice(
        Math.min(deleted.index, segments.length),
        0,
        deleted.fragment,
      );
      await this.projects.save(projectId, entry.managedSourcePath, {
        ...project,
        segments,
      });
      return deleted.fragment;
    });
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

  async getThumbnailManifest(projectId: string): Promise<ThumbnailManifestV1> {
    const { entry, project } = await this.loadThumbnailProject(projectId);
    const identity = thumbnailJobIdentity(entry.fingerprint);
    const durationSeconds = project.source.durationSeconds;
    const manifest =
      durationSeconds === null
        ? undefined
        : await readCompatibleThumbnailManifest(
            this.layout.thumbnailsDirectory(entry.managedSourcePath),
            { ...identity, durationSeconds },
          );

    if (manifest !== undefined) return manifest;

    // Reconciliation durably queues missing, stale, or corrupt output.
    await this.jobQueue.refresh();
    throw new ApiRouteError(
      404,
      'thumbnail_not_ready',
      'Timeline thumbnails are not ready yet.',
      true,
      { projectId },
    );
  }

  async openThumbnailPage(
    projectId: string,
    fileName: string,
  ): Promise<ManagedThumbnailPage> {
    const manifest = await this.getThumbnailManifest(projectId);
    if (!manifest.pages.some(([declared]) => declared === fileName)) {
      throw new ApiRouteError(
        404,
        'thumbnail_page_not_found',
        'The thumbnail sprite page was not found.',
        false,
        { projectId },
      );
    }

    const entry = await this.requireLibraryEntry(projectId);
    const pagePath = resolve(
      this.layout.thumbnailsDirectory(entry.managedSourcePath),
      fileName,
    );
    await this.layout.assertNoSymlinkComponents(pagePath);
    let file: FileHandle | undefined;

    try {
      file = await open(pagePath, constants.O_RDONLY | constants.O_NOFOLLOW);
      const status = await file.stat();
      if (!status.isFile() || !Number.isSafeInteger(status.size)) {
        throw new Error('Thumbnail page is not a regular file');
      }
      return { file, size: status.size };
    } catch (error) {
      await file?.close().catch(() => undefined);
      if (error instanceof ApiRouteError) throw error;
      await this.jobQueue.refresh().catch(() => undefined);
      throw new ApiRouteError(
        404,
        'thumbnail_not_ready',
        'Timeline thumbnails are not ready yet.',
        true,
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

  private async loadThumbnailContext(projectId: string): Promise<{
    destinationDirectory: string;
    project: ProjectDocument;
    sourcePath: string;
  }> {
    const { entry, project } = await this.loadThumbnailProject(projectId);
    return {
      destinationDirectory: this.layout.thumbnailsDirectory(
        entry.managedSourcePath,
      ),
      project,
      sourcePath: this.layout.resolveManagedRelativePath(
        entry.managedSourcePath,
      ),
    };
  }

  private async loadThumbnailProject(projectId: string): Promise<{
    entry: LibraryEntry;
    project: ProjectDocument;
  }> {
    const entry = await this.requireLibraryEntry(projectId);
    return {
      entry,
      project: await this.projects.readRequired(
        projectId,
        entry.managedSourcePath,
      ),
    };
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

function fragmentNotFound(
  projectId: string,
  fragmentId: string,
): ApiRouteError {
  return new ApiRouteError(
    404,
    'fragment_not_found',
    'The fragment was not found.',
    false,
    { projectId, fragmentId },
  );
}
