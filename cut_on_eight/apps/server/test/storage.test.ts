import { mkdir, mkdtemp, readFile, readdir, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { rm } from 'node:fs/promises';
import type { ProjectDocument } from '@cut-on-eight/contracts';
import {
  CorruptPersistedDataError,
  writeJsonAtomic,
} from '../src/storage/atomic-json.js';
import {
  LibraryRepository,
  type LibraryDocument,
} from '../src/storage/library-repository.js';
import { StorageLayout } from '../src/storage/layout.js';
import { ProjectRepository } from '../src/storage/project-repository.js';
import {
  WorkspaceRepository,
  type WorkspaceDocument,
} from '../src/storage/workspace-repository.js';

const projectId = '10000000-0000-4000-8000-000000000001';
const sourceFileName = 'Cross Body Lead.mp4';
const roots: string[] = [];

async function createRoot(): Promise<string> {
  const root = await mkdtemp(join(tmpdir(), 'cut-on-eight-storage-'));
  roots.push(root);
  return root;
}

function projectDocument(): ProjectDocument {
  return {
    schemaVersion: 1,
    id: projectId,
    source: {
      fileName: sourceFileName,
      durationSeconds: null,
      width: null,
      height: null,
      frameRate: null,
      hasAudio: null,
    },
    settings: { pauseAfterCreation: false },
    playbackPositionSeconds: 12.5,
    selectedSegmentId: null,
    segments: [],
    metadata: { title: null, tags: [], notes: null },
  };
}

afterEach(async () => {
  await Promise.all(
    roots.splice(0).map((root) => rm(root, { recursive: true })),
  );
});

describe('atomic managed storage', () => {
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
    const library: LibraryDocument = {
      schemaVersion: 1,
      entries: [
        {
          id: projectId,
          managedSourcePath: paths.relativeSource,
          fingerprint: {
            realPath: '/Users/example/Videos/Cross Body Lead.mp4',
            size: 123_456,
            modifiedMilliseconds: 1_753_092_000_000,
          },
          importedAt: '2026-07-21T10:00:00.000Z',
        },
      ],
    };
    const workspace: WorkspaceDocument = {
      schemaVersion: 1,
      openProjectIds: [projectId],
      activeProjectId: projectId,
    };

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

  it('returns empty version-1 documents for missing files', async () => {
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
      schemaVersion: 1,
      id: projectId,
      source: { fileName: sourceFileName },
      segments: [],
    });
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
});
