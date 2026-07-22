import {
  jobRecordSchema,
  projectDocumentSchema,
  type JobSnapshot,
  type ProjectDocument,
} from '@cut-on-eight/contracts';
import { randomUUID } from 'node:crypto';
import {
  constants,
  copyFile,
  lstat,
  mkdir,
  open,
  readdir,
  rename,
  rm,
  unlink,
} from 'node:fs/promises';
import { basename, join } from 'node:path';
import {
  readJsonValidated,
  syncDirectory,
  writeJsonAtomic,
} from '../storage/atomic-json.js';
import { CatalogRepository } from '../storage/catalog-repository.js';
import {
  LibraryRepository,
  validateLibraryDocument,
  type ImportFingerprint,
  type LibraryDocument,
  type LibraryEntry,
} from '../storage/library-repository.js';
import type { StorageLayout } from '../storage/layout.js';
import { ProjectRepository } from '../storage/project-repository.js';
import {
  WorkspaceRepository,
  type WorkspaceDocument,
} from '../storage/workspace-repository.js';
import { JobRepository } from '../jobs/job-repository.js';
import { thumbnailJobIdentity } from '../jobs/thumbnail-job.js';
import { readCompatibleThumbnailManifest } from '../thumbnails/thumbnail-manifest.js';
import type { SourcePicker } from './source-picker.js';
import { validateMp4Source, type ValidatedSource } from './source-validator.js';

const importMarkerFileName = '.cut-on-eight-import.json';
const uuidPattern =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export type ImportResult =
  | { readonly outcome: 'cancelled' }
  | {
      readonly outcome: 'imported' | 'reopened';
      readonly projectId: string;
    };

export type ImportRecoveryIssue = JobSnapshot['errors'][number];

interface ImportMarker {
  readonly entry: LibraryEntry;
  readonly jobId: string;
  readonly schemaVersion: 1;
}

interface Catalog {
  commit(
    libraryAfter: LibraryDocument,
    workspaceAfter: WorkspaceDocument,
  ): Promise<void>;
  recover(): Promise<boolean>;
}

interface QueuedInspectionWriter {
  createQueuedInspection(
    projectId: string,
    projectDirectory: string,
  ): Promise<{ readonly id: string }>;
  ensureInspectionJob(
    projectId: string,
    projectDirectory: string,
  ): Promise<{ readonly id: string }>;
  ensureThumbnailJob(
    projectId: string,
    projectDirectory: string,
    identity: {
      readonly generatorVersion: string;
      readonly sourceFingerprint: string;
    },
  ): Promise<{ readonly id: string }>;
}

type CopySource = (
  source: string,
  destination: string,
  mode: number,
) => Promise<void>;
type RenameDirectory = (source: string, destination: string) => Promise<void>;
type RemoveDirectory = (
  path: string,
  options: { force: boolean; recursive: boolean },
) => Promise<void>;
type RemoveFile = (path: string) => Promise<void>;
type JsonWriter = (path: string, value: unknown) => Promise<void>;
type IdFactory = () => string;
type Clock = () => Date;
type SyncPath = (path: string) => Promise<void>;

export interface ImportServiceOptions {
  readonly catalog?: Catalog;
  readonly clock?: Clock;
  readonly copySource?: CopySource;
  readonly createId?: IdFactory;
  readonly jobs?: QueuedInspectionWriter;
  readonly library?: LibraryRepository;
  readonly picker: SourcePicker;
  readonly projects?: ProjectRepository;
  readonly removeDirectory?: RemoveDirectory;
  readonly removeFile?: RemoveFile;
  readonly renameDirectory?: RenameDirectory;
  readonly syncDirectory?: SyncPath;
  readonly syncFile?: SyncPath;
  readonly validateSource?: (path: string) => Promise<ValidatedSource>;
  readonly workspace?: WorkspaceRepository;
  readonly writeJson?: JsonWriter;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function hasOnlyKeys(value: Record<string, unknown>, keys: string[]): boolean {
  const actualKeys = Object.keys(value);
  return (
    actualKeys.length === keys.length &&
    keys.every((key) => Object.hasOwn(value, key))
  );
}

function sameFingerprint(
  left: ImportFingerprint,
  right: ImportFingerprint,
): boolean {
  return (
    left.realPath === right.realPath &&
    left.size === right.size &&
    left.modifiedMilliseconds === right.modifiedMilliseconds
  );
}

function sameEntry(left: LibraryEntry, right: LibraryEntry): boolean {
  return (
    left.id === right.id &&
    left.managedSourcePath === right.managedSourcePath &&
    left.importedAt === right.importedAt &&
    sameFingerprint(left.fingerprint, right.fingerprint)
  );
}

function activateProject(
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

function removeProject(
  workspace: WorkspaceDocument,
  projectId: string,
): WorkspaceDocument {
  const openProjectIds = workspace.openProjectIds.filter(
    (openProjectId) => openProjectId !== projectId,
  );
  const activeProjectId =
    workspace.activeProjectId === projectId
      ? (openProjectIds.at(-1) ?? null)
      : workspace.activeProjectId;

  return { schemaVersion: 1, openProjectIds, activeProjectId };
}

async function syncFile(path: string): Promise<void> {
  const handle = await open(path, 'r');

  try {
    await handle.sync();
  } finally {
    await handle.close();
  }
}

function initialProject(
  projectId: string,
  sourceFileName: string,
): ProjectDocument {
  return projectDocumentSchema.parse({
    schemaVersion: 3,
    id: projectId,
    source: {
      fileName: sourceFileName,
      durationSeconds: null,
      width: null,
      height: null,
      frameRateNumerator: null,
      frameRateDenominator: null,
      frameRateReliability: 'approximate',
      hasAudio: null,
      inspectedAt: null,
      inspectorVersion: null,
    },
    editor: { timelineZoom: 1, timelineOffsetSeconds: 0 },
    settings: { pauseAfterCreation: false },
    playbackPositionSeconds: 0,
    selectedSegmentId: null,
    segments: [],
    metadata: { title: null, tags: [], notes: null },
  });
}

function isMissing(error: unknown): boolean {
  return (
    error instanceof Error &&
    'code' in error &&
    (error as NodeJS.ErrnoException).code === 'ENOENT'
  );
}

export class ImportService {
  private readonly catalog: Catalog;
  private readonly clock: Clock;
  private readonly copySource: CopySource;
  private readonly createId: IdFactory;
  private readonly jobs: QueuedInspectionWriter;
  private readonly library: LibraryRepository;
  private readonly projects: ProjectRepository;
  private readonly removeDirectory: RemoveDirectory;
  private readonly removeFile: RemoveFile;
  private readonly renameDirectory: RenameDirectory;
  private readonly syncDirectory: SyncPath;
  private readonly syncFile: SyncPath;
  private readonly validateSource: (path: string) => Promise<ValidatedSource>;
  private readonly workspace: WorkspaceRepository;
  private readonly writeJson: JsonWriter;
  private operationQueue: Promise<void> = Promise.resolve();

  constructor(
    private readonly layout: StorageLayout,
    private readonly options: ImportServiceOptions,
  ) {
    this.library = options.library ?? new LibraryRepository(layout);
    this.workspace = options.workspace ?? new WorkspaceRepository(layout);
    this.projects = options.projects ?? new ProjectRepository(layout);
    this.catalog = options.catalog ?? new CatalogRepository(layout);
    this.jobs = options.jobs ?? new JobRepository(layout);
    this.clock = options.clock ?? (() => new Date());
    this.createId = options.createId ?? randomUUID;
    this.copySource = options.copySource ?? copyFile;
    this.renameDirectory = options.renameDirectory ?? rename;
    this.syncDirectory = options.syncDirectory ?? syncDirectory;
    this.syncFile = options.syncFile ?? syncFile;
    this.removeDirectory = options.removeDirectory ?? rm;
    this.removeFile = options.removeFile ?? unlink;
    this.writeJson = options.writeJson ?? writeJsonAtomic;
    this.validateSource = options.validateSource ?? validateMp4Source;
  }

  async selectAndImport(): Promise<ImportResult> {
    const selectedPath = await this.selectSource();

    if (selectedPath === null) {
      return { outcome: 'cancelled' };
    }

    return this.importSelected(selectedPath);
  }

  selectSource(): Promise<string | null> {
    return this.options.picker.selectMp4();
  }

  importSelected(selectedPath: string): Promise<ImportResult> {
    return this.enqueue(() => this.importSelectedUnlocked(selectedPath));
  }

  recover(): Promise<readonly ImportRecoveryIssue[]> {
    return this.enqueue(() => this.recoverUnlocked());
  }

  reconcileThumbnailJobs(): Promise<readonly ImportRecoveryIssue[]> {
    return this.enqueue(() => this.ensureThumbnailJobsForInspectedProjects());
  }

  private enqueue<T>(operation: () => Promise<T>): Promise<T> {
    const result = this.operationQueue.then(operation);
    this.operationQueue = result.then(
      () => undefined,
      () => undefined,
    );
    return result;
  }

  private async importSelectedUnlocked(
    selectedPath: string,
  ): Promise<ImportResult> {
    await this.recoverUnlocked();
    const source = await this.validateSource(selectedPath);
    let library = await this.library.read();

    while (true) {
      const duplicate = library.entries.find((entry) =>
        sameFingerprint(entry.fingerprint, source.fingerprint),
      );

      if (duplicate === undefined) {
        break;
      }

      if (await this.isUsableDuplicate(duplicate)) {
        const paths = this.layout.forProject(
          duplicate.id,
          basename(duplicate.managedSourcePath),
        );
        await this.jobs.ensureInspectionJob(duplicate.id, paths.directory);
        const workspace = await this.workspace.read();
        await this.catalog.commit(
          library,
          activateProject(workspace, duplicate.id),
        );
        return { outcome: 'reopened', projectId: duplicate.id };
      }

      const workspace = await this.workspace.read();
      library = {
        schemaVersion: 1,
        entries: library.entries.filter((entry) => entry.id !== duplicate.id),
      };
      await this.catalog.commit(
        library,
        removeProject(workspace, duplicate.id),
      );
    }

    const sourceFileName = basename(source.path);
    const allocation = await this.allocateImport(sourceFileName);
    const { projectId, paths, temporaryDirectory } = allocation;
    const temporarySource = join(temporaryDirectory, sourceFileName);
    const temporarySidecar = `${temporarySource}.danceclips.json`;
    let promoted = false;

    try {
      const entry: LibraryEntry = {
        id: projectId,
        managedSourcePath: paths.relativeSource,
        fingerprint: source.fingerprint,
        importedAt: this.clock().toISOString(),
      };

      await this.copySource(
        source.path,
        temporarySource,
        constants.COPYFILE_FICLONE,
      );
      const managedSource = await this.validateSource(temporarySource);
      const sourceAfterCopy = await this.validateSource(source.path);

      if (
        managedSource.fingerprint.size !== source.fingerprint.size ||
        !sameFingerprint(sourceAfterCopy.fingerprint, source.fingerprint)
      ) {
        throw new Error('The selected source changed during import');
      }

      await this.syncFile(temporarySource);

      await this.writeJson(
        temporarySidecar,
        initialProject(projectId, sourceFileName),
      );
      const job = await this.jobs.createQueuedInspection(
        projectId,
        temporaryDirectory,
      );
      const marker: ImportMarker = {
        schemaVersion: 1,
        entry,
        jobId: job.id,
      };
      await this.writeJson(
        join(temporaryDirectory, importMarkerFileName),
        marker,
      );
      await this.renameDirectory(temporaryDirectory, paths.directory);
      promoted = true;
      await this.syncDirectory(this.layout.dataRoot);

      const workspace = await this.workspace.read();
      await this.catalog.commit(
        { schemaVersion: 1, entries: [...library.entries, entry] },
        activateProject(workspace, projectId),
      );
      await this.removeFile(join(paths.directory, importMarkerFileName)).catch(
        () => undefined,
      );
      return { outcome: 'imported', projectId };
    } catch (error) {
      if (
        promoted &&
        !(await this.isIndexed(projectId, paths.relativeSource))
      ) {
        try {
          await this.renameDirectory(paths.directory, temporaryDirectory);
          promoted = false;
        } catch {
          // Leave the promoted marker for deterministic startup reconciliation.
        }
      }

      if (!promoted) {
        await this.removeDirectory(temporaryDirectory, {
          recursive: true,
          force: true,
        }).catch(() => undefined);
      }

      throw error;
    }
  }

  private async isUsableDuplicate(entry: LibraryEntry): Promise<boolean> {
    const sourceFileName = basename(entry.managedSourcePath);
    const paths = this.layout.forProject(entry.id, sourceFileName);

    try {
      await this.layout.assertNoSymlinkComponents(paths.source);
      await this.layout.assertNoSymlinkComponents(paths.sidecar);
      const managedSource = await this.validateSource(paths.source);

      if (managedSource.fingerprint.size !== entry.fingerprint.size) {
        return false;
      }

      await this.projects.readRequired(entry.id, entry.managedSourcePath);
      return true;
    } catch {
      return false;
    }
  }

  private async isIndexed(
    projectId: string,
    managedSourcePath: string,
  ): Promise<boolean> {
    try {
      const library = await this.library.read();
      return library.entries.some(
        (entry) =>
          entry.id === projectId ||
          entry.managedSourcePath === managedSourcePath,
      );
    } catch {
      // If catalog state cannot be read, preserve the promoted folder and its
      // marker. Recovery can reconcile it without risking indexed media.
      return true;
    }
  }

  private async allocateImport(sourceFileName: string): Promise<{
    projectId: string;
    paths: ReturnType<StorageLayout['forProject']>;
    temporaryDirectory: string;
  }> {
    await this.layout.assertNoSymlinkComponents(this.layout.dataRoot);
    await mkdir(this.layout.dataRoot, { recursive: true });
    await this.layout.assertNoSymlinkComponents(this.layout.dataRoot);

    for (let attempt = 0; attempt < 16; attempt += 1) {
      const projectId = this.createId();
      const paths = this.layout.forProject(projectId, sourceFileName);
      const temporaryDirectory = `${paths.directory}.importing`;

      try {
        await lstat(paths.directory);
        continue;
      } catch (error) {
        if (!isMissing(error)) {
          throw error;
        }
      }

      try {
        await mkdir(temporaryDirectory, { recursive: false, mode: 0o700 });
        return { projectId, paths, temporaryDirectory };
      } catch (error) {
        if (
          error instanceof Error &&
          'code' in error &&
          (error as NodeJS.ErrnoException).code === 'EEXIST'
        ) {
          continue;
        }

        throw error;
      }
    }

    throw new Error('Unable to allocate a collision-safe import directory');
  }

  private async recoverUnlocked(): Promise<readonly ImportRecoveryIssue[]> {
    await this.catalog.recover();
    let entries;

    try {
      await this.layout.assertNoSymlinkComponents(this.layout.dataRoot);
      entries = await readdir(this.layout.dataRoot, { withFileTypes: true });
    } catch (error) {
      if (isMissing(error)) {
        return [];
      }

      throw error;
    }

    for (const entry of entries) {
      if (!entry.isDirectory() || !entry.name.endsWith('.importing')) {
        continue;
      }

      const temporaryDirectory = join(this.layout.dataRoot, entry.name);
      await this.layout.assertNoSymlinkComponents(temporaryDirectory);
      await this.removeDirectory(temporaryDirectory, {
        recursive: true,
        force: true,
      });
    }

    for (const entry of entries) {
      if (!entry.isDirectory() || entry.name.endsWith('.importing')) {
        continue;
      }

      await this.reconcileMarker(join(this.layout.dataRoot, entry.name));
    }

    return this.ensureThumbnailJobsForInspectedProjects();
  }

  private async ensureThumbnailJobsForInspectedProjects(): Promise<
    readonly ImportRecoveryIssue[]
  > {
    const library = await this.library.read();
    const issues: ImportRecoveryIssue[] = [];

    for (const entry of library.entries) {
      let project;
      try {
        project = await this.projects.readRequired(
          entry.id,
          entry.managedSourcePath,
        );
      } catch {
        // Existing unavailable projects remain isolated during recovery.
        continue;
      }

      if (
        project.source.durationSeconds === null ||
        project.source.inspectedAt === null
      ) {
        continue;
      }

      const projectDirectory = this.layout.forProject(
        entry.id,
        project.source.fileName,
      ).directory;
      try {
        const identity = thumbnailJobIdentity(entry.fingerprint);
        const compatible = await readCompatibleThumbnailManifest(
          this.layout.thumbnailsDirectory(entry.managedSourcePath),
          {
            ...identity,
            durationSeconds: project.source.durationSeconds,
          },
        );
        if (compatible !== undefined) continue;
        await this.jobs.ensureThumbnailJob(
          entry.id,
          projectDirectory,
          identity,
        );
      } catch {
        issues.push({
          code: 'thumbnail_queue_failed',
          message: 'Thumbnail generation could not be queued during recovery.',
          projectId: entry.id,
        });
      }
    }

    return issues;
  }

  private async reconcileMarker(projectDirectory: string): Promise<void> {
    const markerFile = join(projectDirectory, importMarkerFileName);
    await this.layout.assertNoSymlinkComponents(markerFile);
    const marker = await readJsonValidated(markerFile, (value) =>
      this.validateMarker(value, projectDirectory),
    );

    if (marker === undefined) {
      return;
    }

    const sourceFileName = basename(marker.entry.managedSourcePath);
    const paths = this.layout.forProject(marker.entry.id, sourceFileName);
    const library = await this.library.read();
    const indexed = library.entries.find(
      (entry) => entry.id === marker.entry.id,
    );

    if (indexed !== undefined) {
      if (!sameEntry(indexed, marker.entry)) {
        throw new Error('Import marker conflicts with the indexed project');
      }

      await this.removeFile(markerFile).catch(() => undefined);
      return;
    }

    if (
      library.entries.some(
        (entry) =>
          entry.managedSourcePath === marker.entry.managedSourcePath ||
          sameFingerprint(entry.fingerprint, marker.entry.fingerprint),
      )
    ) {
      throw new Error('Import marker conflicts with the managed library');
    }

    const managedSource = await this.validateSource(paths.source);

    if (managedSource.fingerprint.size !== marker.entry.fingerprint.size) {
      throw new Error('Recovered import source does not match its marker');
    }

    await this.projects.readRequired(
      marker.entry.id,
      marker.entry.managedSourcePath,
    );
    const job = await readJsonValidated(
      this.layout.jobFile(marker.entry.managedSourcePath, marker.jobId),
      (value) => jobRecordSchema.parse(value),
    );

    if (job === undefined || job.projectId !== marker.entry.id) {
      throw new Error('Recovered import job does not match its marker');
    }

    const workspace = await this.workspace.read();
    await this.catalog.commit(
      { schemaVersion: 1, entries: [...library.entries, marker.entry] },
      activateProject(workspace, marker.entry.id),
    );
    await this.removeFile(markerFile).catch(() => undefined);
  }

  private validateMarker(
    value: unknown,
    projectDirectory: string,
  ): ImportMarker {
    if (
      !isRecord(value) ||
      !hasOnlyKeys(value, ['schemaVersion', 'entry', 'jobId']) ||
      value.schemaVersion !== 1 ||
      typeof value.jobId !== 'string' ||
      !uuidPattern.test(value.jobId)
    ) {
      throw new Error('Import marker is invalid');
    }

    const library = validateLibraryDocument(
      { schemaVersion: 1, entries: [value.entry] },
      this.layout,
    );
    const entry = library.entries[0];

    if (entry === undefined) {
      throw new Error('Import marker has no library entry');
    }

    const paths = this.layout.forProject(
      entry.id,
      basename(entry.managedSourcePath),
    );

    if (paths.directory !== projectDirectory) {
      throw new Error('Import marker does not match its project directory');
    }

    return { schemaVersion: 1, entry, jobId: value.jobId };
  }
}
