import {
  importSelectionResponseSchema,
  projectDocumentSchema,
  projectSummarySchema,
  workspaceSnapshotSchema,
  type ImportSelectionResponse,
  type ProjectDocument,
  type WorkspaceSnapshot,
} from '@cut-on-eight/contracts';
import { constants } from 'node:fs';
import { open, type FileHandle } from 'node:fs/promises';
import type { ServerConfig } from './config.js';
import { ApiRouteError } from './http/api-error.js';
import { ImportService } from './imports/import-service.js';
import type { SourcePicker } from './imports/source-picker.js';
import { CatalogRepository } from './storage/catalog-repository.js';
import {
  LibraryRepository,
  type LibraryDocument,
  type LibraryEntry,
} from './storage/library-repository.js';
import { StorageLayout } from './storage/layout.js';
import { ProjectRepository } from './storage/project-repository.js';
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
  getWorkspace(): Promise<WorkspaceSnapshot>;
  openProject(projectId: string): Promise<WorkspaceSnapshot>;
  openSource(projectId: string): Promise<ManagedSource>;
  recover(): Promise<void>;
  saveProject(
    projectId: string,
    document: ProjectDocument,
  ): Promise<ProjectDocument>;
  selectImport(): Promise<ImportSelectionResponse>;
}

export interface CreateServicesOptions {
  readonly config: ServerConfig;
  readonly picker: SourcePicker;
  readonly probeRunner?: unknown;
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

export function createServices(options: CreateServicesOptions): AppServices {
  void options.probeRunner;
  const layout = new StorageLayout(options.config.dataRoot);
  const library = new LibraryRepository(layout);
  const projects = new ProjectRepository(layout);
  const workspace = new WorkspaceRepository(layout);
  const catalog = new CatalogRepository(layout, library, workspace);
  const imports = new ImportService(layout, {
    catalog,
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
  );
}

class ManagedWorkspaceServices implements AppServices {
  private operationQueue: Promise<void> = Promise.resolve();

  constructor(
    private readonly layout: StorageLayout,
    private readonly library: LibraryRepository,
    private readonly projects: ProjectRepository,
    private readonly workspace: WorkspaceRepository,
    private readonly imports: ImportService,
  ) {}

  recover(): Promise<void> {
    return this.enqueue(() => this.imports.recover());
  }

  getWorkspace(): Promise<WorkspaceSnapshot> {
    return this.enqueue(() => this.snapshot());
  }

  selectImport(): Promise<ImportSelectionResponse> {
    return this.enqueue(async () => {
      const result = await this.imports.selectAndImport();
      const workspaceSnapshot = await this.snapshot();

      return importSelectionResponseSchema.parse({
        ...result,
        workspace: workspaceSnapshot,
      });
    });
  }

  openProject(projectId: string): Promise<WorkspaceSnapshot> {
    return this.enqueue(async () => {
      const entry = await this.requireLibraryEntry(projectId);
      await this.projects.readRequired(entry.id, entry.managedSourcePath);
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
      await this.projects.save(projectId, entry.managedSourcePath, validated);
      return validated;
    });
  }

  closeProject(
    projectId: string,
    document: ProjectDocument,
  ): Promise<WorkspaceSnapshot> {
    return this.enqueue(async () => {
      const validated = projectDocumentSchema.parse(document);
      const entry = await this.requireLibraryEntry(projectId);
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

      await this.projects.save(projectId, entry.managedSourcePath, validated);
      await this.workspace.save(closedWorkspace(current, projectId));
      return this.snapshot();
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

  private async requireLibraryEntry(projectId: string): Promise<LibraryEntry> {
    const library = await this.library.read();
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

  private async snapshot(): Promise<WorkspaceSnapshot> {
    const [library, workspace] = await Promise.all([
      this.library.read(),
      this.workspace.read(),
    ]);
    const projectsById = await this.readLibraryProjects(library);
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

      if (project === undefined) {
        throw new ApiRouteError(
          500,
          'library_project_missing',
          'The managed library refers to a missing project.',
          false,
          { projectId: entry.id },
        );
      }

      return projectSummarySchema.parse({
        id: project.id,
        fileName: project.source.fileName,
        durationSeconds: project.source.durationSeconds,
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
  ): Promise<Map<string, ProjectDocument>> {
    const entries = await Promise.all(
      library.entries.map(async (entry) => {
        const project = await this.projects.readRequired(
          entry.id,
          entry.managedSourcePath,
        );
        return [entry.id, project] as const;
      }),
    );

    return new Map(entries);
  }
}
