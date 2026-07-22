import {
  access,
  mkdir,
  mkdtemp,
  readFile,
  readdir,
  rename,
  symlink,
  unlink,
  writeFile,
} from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { rm } from 'node:fs/promises';
import type { ProjectDocument } from '@cut-on-eight/contracts';
import {
  CorruptPersistedDataError,
  syncDirectory,
  writeJsonAtomic,
} from '../src/storage/atomic-json.js';
import { CatalogRepository } from '../src/storage/catalog-repository.js';
import { JobRepository } from '../src/jobs/job-repository.js';
import {
  LibraryRepository,
  type LibraryDocument,
} from '../src/storage/library-repository.js';
import { StorageLayout } from '../src/storage/layout.js';
import { ProjectRepository } from '../src/storage/project-repository.js';
import { ProjectDeletion } from '../src/storage/project-deletion.js';
import {
  WorkspaceRepository,
  type WorkspaceDocument,
} from '../src/storage/workspace-repository.js';

const projectId = '10000000-0000-4000-8000-000000000001';
const sourceFileName = 'Cross Body Lead.mp4';
const secondProjectId = '10000000-0000-4000-8000-000000000002';
const secondSourceFileName = 'Inside Turn.mp4';
const thumbnailJobId = '20000000-0000-4000-8000-000000000001';
const roots: string[] = [];

async function createRoot(): Promise<string> {
  const root = await mkdtemp(join(tmpdir(), 'cut-on-eight-storage-'));
  roots.push(root);
  return root;
}

function projectDocument(): ProjectDocument {
  return {
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
    playbackPositionSeconds: 12.5,
    selectedSegmentId: null,
    segments: [],
    metadata: { title: null, tags: [], notes: null },
  };
}

function libraryDocument(
  layout: StorageLayout,
  id = projectId,
  fileName = sourceFileName,
): LibraryDocument {
  return {
    schemaVersion: 1,
    entries: [
      {
        id,
        managedSourcePath: layout.forProject(id, fileName).relativeSource,
        fingerprint: {
          realPath: '/Users/example/Videos/Cross Body Lead.mp4',
          size: 123_456,
          modifiedMilliseconds: 1_753_092_000_000,
        },
        importedAt: '2026-07-21T10:00:00.000Z',
      },
    ],
  };
}

function workspaceDocument(id = projectId): WorkspaceDocument {
  return {
    schemaVersion: 1,
    openProjectIds: [id],
    activeProjectId: id,
  };
}

const emptyLibrary: LibraryDocument = { schemaVersion: 1, entries: [] };
const emptyWorkspace: WorkspaceDocument = {
  schemaVersion: 1,
  openProjectIds: [],
  activeProjectId: null,
};

afterEach(async () => {
  await Promise.all(
    roots.splice(0).map((root) => rm(root, { recursive: true })),
  );
});

describe('atomic managed storage', () => {
  it('restores a deletion tombstone after rolling back a prepared catalog transaction', async () => {
    const root = await createRoot();
    const layout = new StorageLayout(root);
    const library = new LibraryRepository(layout);
    const workspace = new WorkspaceRepository(layout);
    const catalog = new CatalogRepository(layout, library, workspace);
    const paths = layout.forProject(projectId, sourceFileName);
    const beforeLibrary = libraryDocument(layout);
    const beforeWorkspace = workspaceDocument();
    await mkdir(paths.directory, { recursive: true });
    await writeFile(paths.source, 'managed source');
    await library.save(emptyLibrary);
    await workspace.save(emptyWorkspace);
    await writeJsonAtomic(layout.catalogTransactionFile, {
      schemaVersion: 1,
      phase: 'prepared',
      before: { library: beforeLibrary, workspace: beforeWorkspace },
      after: { library: emptyLibrary, workspace: emptyWorkspace },
    });
    const relativeDirectory = paths.relativeSource.slice(
      0,
      paths.relativeSource.lastIndexOf('/'),
    );
    const tombstone = join(root, `.deleting-${relativeDirectory}`);
    await rename(paths.directory, tombstone);

    await new ProjectDeletion(layout, library, workspace, catalog).recover();

    await expect(readFile(paths.source, 'utf8')).resolves.toBe(
      'managed source',
    );
    await expect(library.read()).resolves.toEqual(beforeLibrary);
    await expect(workspace.read()).resolves.toEqual(beforeWorkspace);
    await expect(access(tombstone)).rejects.toMatchObject({ code: 'ENOENT' });
  });

  it('persists compact thumbnail jobs as separate atomic records', async () => {
    const root = await createRoot();
    const layout = new StorageLayout(root);
    const paths = layout.forProject(projectId, sourceFileName);
    const jobs = new JobRepository(
      layout,
      () => thumbnailJobId,
      () => new Date('2026-07-22T10:00:00.000Z'),
    );

    await jobs.ensureThumbnailJob(projectId, paths.directory, {
      generatorVersion: 'thumbnail-overview-v1',
      sourceFingerprint: 'sha256:source',
    });

    expect(await readdir(paths.jobsDirectory)).toEqual([
      `${thumbnailJobId}.json`,
    ]);
    expect(
      JSON.parse(
        await readFile(
          join(paths.jobsDirectory, `${thumbnailJobId}.json`),
          'utf8',
        ),
      ),
    ).toMatchObject({
      type: 'generate-thumbnails',
      generatorVersion: 'thumbnail-overview-v1',
      sourceFingerprint: 'sha256:source',
      state: 'queued',
    });
  });

  it('atomically replaces JSON without leaving temporary files', async () => {
    const root = await createRoot();
    const target = join(root, '_system', 'workspace.json');

    await writeJsonAtomic(target, { value: 'before' });
    await writeJsonAtomic(target, { value: 'after' });

    expect(JSON.parse(await readFile(target, 'utf8'))).toEqual({
      value: 'after',
    });
    expect(await readdir(join(root, '_system'))).toEqual(['workspace.json']);
  });

  it('syncs the containing directory after the atomic rename', async () => {
    const root = await createRoot();
    const target = join(root, '_system', 'workspace.json');
    const syncedDirectories: string[] = [];

    await writeJsonAtomic(target, { value: 'durable' }, async (directory) => {
      if (directory === join(root, '_system')) {
        expect(JSON.parse(await readFile(target, 'utf8'))).toEqual({
          value: 'durable',
        });
      }

      syncedDirectories.push(directory);
    });

    expect(syncedDirectories).toEqual([root, join(root, '_system')]);
  });

  it('ignores only explicitly unsupported directory fsync errors', async () => {
    const unsupportedHandle = {
      sync: async () => {
        throw Object.assign(new Error('unsupported'), { code: 'EINVAL' });
      },
      close: async () => undefined,
    };
    const failedHandle = {
      sync: async () => {
        throw Object.assign(new Error('denied'), { code: 'EACCES' });
      },
      close: async () => undefined,
    };

    await expect(
      syncDirectory('/tmp/example', async () => unsupportedHandle),
    ).resolves.toBeUndefined();
    await expect(
      syncDirectory('/tmp/example', async () => failedHandle),
    ).rejects.toMatchObject({ code: 'EACCES' });
  });

  it('cleans up its exclusive temporary file after a failed replacement', async () => {
    const root = await createRoot();
    const systemDirectory = join(root, '_system');
    const targetDirectory = join(systemDirectory, 'workspace.json');

    await mkdir(targetDirectory, { recursive: true });

    await expect(
      writeJsonAtomic(targetDirectory, { value: 1 }),
    ).rejects.toBeDefined();
    expect(await readdir(systemDirectory)).toEqual(['workspace.json']);
  });

  it('restores library, project, and ordered workspace documents', async () => {
    const root = await createRoot();
    const layout = new StorageLayout(root);
    const paths = layout.forProject(projectId, sourceFileName);
    const library = libraryDocument(layout);
    const workspace = workspaceDocument();

    await new LibraryRepository(layout).save(library);
    await new ProjectRepository(layout).save(
      projectId,
      paths.relativeSource,
      projectDocument(),
    );
    await new WorkspaceRepository(layout).save(workspace);

    expect(await new LibraryRepository(layout).read()).toEqual(library);
    expect(
      await new ProjectRepository(layout).read(projectId, paths.relativeSource),
    ).toEqual(projectDocument());
    expect(await new WorkspaceRepository(layout).read()).toEqual(workspace);
  });

  it('rejects absolute, traversal, and escaping managed paths', async () => {
    const root = await createRoot();
    const layout = new StorageLayout(root);

    expect(() => layout.resolveManagedRelativePath('/tmp/video.mp4')).toThrow(
      'safe relative path',
    );
    expect(() =>
      layout.resolveManagedRelativePath('../outside/video.mp4'),
    ).toThrow('safe relative path');
    expect(() =>
      layout.resolveManagedRelativePath('project/../../outside/video.mp4'),
    ).toThrow('safe relative path');
  });

  it('derives the managed folder and sidecar from the full project identity', async () => {
    const root = await createRoot();
    const paths = new StorageLayout(root).forProject(projectId, sourceFileName);

    expect(paths.relativeDirectory).toBe('cross-body-lead--10000000');
    expect(paths.relativeSource).toBe(
      'cross-body-lead--10000000/Cross Body Lead.mp4',
    );
    expect(paths.sidecar).toBe(`${paths.source}.danceclips.json`);
  });

  it('returns empty version-2 projects for missing files', async () => {
    const root = await createRoot();
    const layout = new StorageLayout(root);
    const paths = layout.forProject(projectId, sourceFileName);

    await expect(new LibraryRepository(layout).read()).resolves.toEqual({
      schemaVersion: 1,
      entries: [],
    });
    await expect(new WorkspaceRepository(layout).read()).resolves.toEqual({
      schemaVersion: 1,
      openProjectIds: [],
      activeProjectId: null,
    });
    await expect(
      new ProjectRepository(layout).read(projectId, paths.relativeSource),
    ).resolves.toMatchObject({
      schemaVersion: 3,
      id: projectId,
      source: { fileName: sourceFileName },
      segments: [],
    });
    await expect(
      new ProjectRepository(layout).readRequired(
        projectId,
        paths.relativeSource,
      ),
    ).rejects.toMatchObject({ code: 'missing_project_sidecar' });
  });

  it('reads version 1 and persists its migration on the next save', async () => {
    const root = await createRoot();
    const layout = new StorageLayout(root);
    const paths = layout.forProject(projectId, sourceFileName);
    const legacy = {
      schemaVersion: 1,
      id: projectId,
      source: {
        fileName: sourceFileName,
        durationSeconds: 12,
        width: 1920,
        height: 1080,
        frameRate: '30000/1001',
        hasAudio: true,
      },
      settings: { pauseAfterCreation: false },
      playbackPositionSeconds: 4,
      selectedSegmentId: null,
      segments: [
        {
          id: '20000000-0000-4000-8000-000000000001',
          startSeconds: 3,
          endSeconds: 7,
          exportSelected: true,
        },
      ],
      metadata: { title: null, tags: [], notes: null },
    } as const;
    await writeJsonAtomic(paths.sidecar, legacy);

    const projects = new ProjectRepository(layout);
    const migrated = await projects.read(projectId, paths.relativeSource);

    expect(migrated).toMatchObject({
      schemaVersion: 3,
      source: {
        frameRateNumerator: 30_000,
        frameRateDenominator: 1_001,
        frameRateReliability: 'approximate',
      },
      editor: { timelineZoom: 1, timelineOffsetSeconds: 0 },
      segments: [{ startSeconds: 3, endSeconds: 7 }],
    });
    expect(JSON.parse(await readFile(paths.sidecar, 'utf8'))).toEqual(legacy);

    await projects.save(projectId, paths.relativeSource, migrated);

    expect(JSON.parse(await readFile(paths.sidecar, 'utf8'))).toEqual(migrated);
  });

  it('allows missing managed path components for first-use storage', async () => {
    const root = await createRoot();
    const layout = new StorageLayout(join(root, 'not-created-yet'));

    await expect(
      layout.assertNoSymlinkComponents(layout.libraryFile),
    ).resolves.toBeUndefined();
  });

  it('rejects symlinked project path components before reads and writes', async () => {
    const root = await createRoot();
    const outside = await createRoot();
    const layout = new StorageLayout(root);
    const paths = layout.forProject(projectId, sourceFileName);
    const projects = new ProjectRepository(layout);

    await symlink(outside, paths.directory, 'dir');

    await expect(
      projects.read(projectId, paths.relativeSource),
    ).rejects.toMatchObject({ code: 'unsafe_storage_path' });
    await expect(
      projects.save(projectId, paths.relativeSource, projectDocument()),
    ).rejects.toMatchObject({ code: 'unsafe_storage_path' });
    await expect(
      access(join(outside, `${sourceFileName}.danceclips.json`)),
    ).rejects.toMatchObject({ code: 'ENOENT' });
  });

  it('rejects a symlinked system directory before repository access', async () => {
    const root = await createRoot();
    const outside = await createRoot();
    const layout = new StorageLayout(root);

    await symlink(outside, layout.systemDirectory, 'dir');

    await expect(new LibraryRepository(layout).read()).rejects.toMatchObject({
      code: 'unsafe_storage_path',
    });
    await expect(
      new WorkspaceRepository(layout).save(emptyWorkspace),
    ).rejects.toMatchObject({ code: 'unsafe_storage_path' });
  });

  it('rejects the data root itself when it is a symbolic link', async () => {
    const actualRoot = await createRoot();
    const parent = await createRoot();
    const linkedRoot = join(parent, 'managed');

    await symlink(actualRoot, linkedRoot, 'dir');

    await expect(
      new LibraryRepository(new StorageLayout(linkedRoot)).read(),
    ).rejects.toMatchObject({ code: 'unsafe_storage_path' });
  });

  it('preserves malformed sidecar bytes when save is attempted', async () => {
    const root = await createRoot();
    const layout = new StorageLayout(root);
    const paths = layout.forProject(projectId, sourceFileName);
    const malformedBytes = Buffer.from('{"schemaVersion":1,"broken":');

    await mkdir(paths.directory, { recursive: true });
    await writeFile(paths.sidecar, malformedBytes, { flag: 'wx' });

    await expect(
      new ProjectRepository(layout).save(
        projectId,
        paths.relativeSource,
        projectDocument(),
      ),
    ).rejects.toMatchObject<Partial<CorruptPersistedDataError>>({
      code: 'corrupt_persisted_data',
    });
    expect(await readFile(paths.sidecar)).toEqual(malformedBytes);
  });

  it('rejects an invalid stored library path as corrupt data', async () => {
    const root = await createRoot();
    const layout = new StorageLayout(root);

    await writeJsonAtomic(layout.libraryFile, {
      schemaVersion: 1,
      entries: [
        {
          id: projectId,
          managedSourcePath: '../escaped/video.mp4',
          fingerprint: {
            realPath: '/tmp/video.mp4',
            size: 10,
            modifiedMilliseconds: 1,
          },
          importedAt: '2026-07-21T10:00:00.000Z',
        },
      ],
    });

    await expect(new LibraryRepository(layout).read()).rejects.toMatchObject({
      code: 'corrupt_persisted_data',
    });
  });

  it('rejects a safe but mismatched library project path', async () => {
    const root = await createRoot();
    const layout = new StorageLayout(root);

    await writeJsonAtomic(layout.libraryFile, {
      schemaVersion: 1,
      entries: [
        {
          id: projectId,
          managedSourcePath: '_system/video.mp4',
          fingerprint: {
            realPath: '/tmp/video.mp4',
            size: 10,
            modifiedMilliseconds: 1,
          },
          importedAt: '2026-07-21T10:00:00.000Z',
        },
      ],
    });

    await expect(new LibraryRepository(layout).read()).rejects.toMatchObject({
      code: 'corrupt_persisted_data',
    });
  });

  it('reports invalid caller documents separately from corrupt bytes', async () => {
    const root = await createRoot();
    const workspace = new WorkspaceRepository(new StorageLayout(root));

    await expect(
      workspace.save({
        schemaVersion: 1,
        openProjectIds: [],
        activeProjectId: projectId,
      }),
    ).rejects.toMatchObject({ code: 'invalid_repository_document' });
  });

  it('rolls back both catalog documents when the second write fails', async () => {
    const root = await createRoot();
    const layout = new StorageLayout(root);
    const library = new LibraryRepository(layout);
    const workspace = new WorkspaceRepository(layout);
    let workspaceSaveAttempts = 0;
    const failingWorkspace = {
      read: () => workspace.read(),
      save: async (document: WorkspaceDocument): Promise<void> => {
        workspaceSaveAttempts += 1;

        if (workspaceSaveAttempts === 1) {
          throw new Error('Injected workspace write failure');
        }

        await workspace.save(document);
      },
    };
    const catalog = new CatalogRepository(layout, library, failingWorkspace);

    await expect(
      catalog.commit(libraryDocument(layout), workspaceDocument()),
    ).rejects.toThrow('Injected workspace write failure');
    await expect(library.read()).resolves.toEqual(emptyLibrary);
    await expect(workspace.read()).resolves.toEqual(emptyWorkspace);
    expect(workspaceSaveAttempts).toBe(2);
    await expect(access(layout.catalogTransactionFile)).rejects.toMatchObject({
      code: 'ENOENT',
    });
  });

  it('commits both catalog documents and removes the journal', async () => {
    const root = await createRoot();
    const layout = new StorageLayout(root);
    const libraryAfter = libraryDocument(layout);
    const workspaceAfter = workspaceDocument();

    await new CatalogRepository(layout).commit(libraryAfter, workspaceAfter);

    await expect(new LibraryRepository(layout).read()).resolves.toEqual(
      libraryAfter,
    );
    await expect(new WorkspaceRepository(layout).read()).resolves.toEqual(
      workspaceAfter,
    );
    await expect(access(layout.catalogTransactionFile)).rejects.toMatchObject({
      code: 'ENOENT',
    });
  });

  it('serializes concurrent catalog commits across the full protocol', async () => {
    const root = await createRoot();
    const layout = new StorageLayout(root);
    const library = new LibraryRepository(layout);
    const workspace = new WorkspaceRepository(layout);
    let releaseFirstSave = (): void => undefined;
    let markFirstSaveStarted = (): void => undefined;
    const firstSaveStarted = new Promise<void>((resolve) => {
      markFirstSaveStarted = resolve;
    });
    const firstSaveGate = new Promise<void>((resolve) => {
      releaseFirstSave = resolve;
    });
    let activeSaves = 0;
    let maximumActiveSaves = 0;
    let saveCalls = 0;
    const observedLibrary = {
      read: () => library.read(),
      save: async (document: LibraryDocument): Promise<void> => {
        saveCalls += 1;
        activeSaves += 1;
        maximumActiveSaves = Math.max(maximumActiveSaves, activeSaves);

        try {
          if (saveCalls === 1) {
            markFirstSaveStarted();
            await firstSaveGate;
          }

          await library.save(document);
        } finally {
          activeSaves -= 1;
        }
      },
    };
    const catalog = new CatalogRepository(layout, observedLibrary, workspace);
    const firstCommit = catalog.commit(
      libraryDocument(layout),
      workspaceDocument(),
    );

    await firstSaveStarted;
    const secondLibrary = libraryDocument(
      layout,
      secondProjectId,
      secondSourceFileName,
    );
    const secondWorkspace = workspaceDocument(secondProjectId);
    const secondCommit = catalog.commit(secondLibrary, secondWorkspace);

    await new Promise((resolve) => setTimeout(resolve, 25));
    const savesBeforeRelease = saveCalls;
    releaseFirstSave();
    await Promise.all([firstCommit, secondCommit]);

    expect(savesBeforeRelease).toBe(1);
    expect(maximumActiveSaves).toBe(1);
    await expect(library.read()).resolves.toEqual(secondLibrary);
    await expect(workspace.read()).resolves.toEqual(secondWorkspace);
  });

  it('preserves later workspace saves when cleaning up a committed journal', async () => {
    const root = await createRoot();
    const layout = new StorageLayout(root);
    const libraryAfter = libraryDocument(layout);
    const workspaceAfter = workspaceDocument();
    let cleanupAttempts = 0;
    const removeJournal = async (path: string): Promise<void> => {
      cleanupAttempts += 1;

      if (cleanupAttempts === 1) {
        throw new Error('Injected journal cleanup failure');
      }

      await unlink(path);
    };
    const catalog = new CatalogRepository(
      layout,
      undefined,
      undefined,
      removeJournal,
    );

    await expect(
      catalog.commit(libraryAfter, workspaceAfter),
    ).resolves.toBeUndefined();
    await expect(
      readFile(layout.catalogTransactionFile, 'utf8').then((contents) =>
        JSON.parse(contents),
      ),
    ).resolves.toMatchObject({ phase: 'committed' });

    await new WorkspaceRepository(layout).save(emptyWorkspace);

    await expect(new CatalogRepository(layout).recover()).resolves.toBe(true);
    await expect(new LibraryRepository(layout).read()).resolves.toEqual(
      libraryAfter,
    );
    await expect(new WorkspaceRepository(layout).read()).resolves.toEqual(
      emptyWorkspace,
    );
    await expect(access(layout.catalogTransactionFile)).rejects.toMatchObject({
      code: 'ENOENT',
    });
  });

  it('recovers both before-documents from an interrupted catalog journal', async () => {
    const root = await createRoot();
    const layout = new StorageLayout(root);
    const library = new LibraryRepository(layout);
    const workspace = new WorkspaceRepository(layout);
    const libraryAfter = libraryDocument(layout);
    const workspaceAfter = workspaceDocument();

    await writeJsonAtomic(layout.catalogTransactionFile, {
      schemaVersion: 1,
      phase: 'prepared',
      before: { library: emptyLibrary, workspace: emptyWorkspace },
      after: { library: libraryAfter, workspace: workspaceAfter },
    });
    await library.save(libraryAfter);
    await workspace.save(workspaceAfter);

    await expect(new CatalogRepository(layout).recover()).resolves.toBe(true);
    await expect(library.read()).resolves.toEqual(emptyLibrary);
    await expect(workspace.read()).resolves.toEqual(emptyWorkspace);
    await expect(access(layout.catalogTransactionFile)).rejects.toMatchObject({
      code: 'ENOENT',
    });
  });
});
