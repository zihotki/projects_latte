import { realpath } from 'node:fs/promises';
import {
  access,
  mkdir,
  mkdtemp,
  readFile,
  readdir,
  rename,
  rm,
  symlink,
  unlink,
  writeFile,
} from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { ImportService } from '../src/imports/import-service.js';
import {
  MacOsSourcePicker,
  type ProcessRunner,
  type SourcePicker,
} from '../src/imports/source-picker.js';
import { validateMp4Source } from '../src/imports/source-validator.js';
import { JobRepository } from '../src/jobs/job-repository.js';
import { CatalogRepository } from '../src/storage/catalog-repository.js';
import { LibraryRepository } from '../src/storage/library-repository.js';
import { StorageLayout } from '../src/storage/layout.js';
import { ProjectRepository } from '../src/storage/project-repository.js';
import { WorkspaceRepository } from '../src/storage/workspace-repository.js';

const projectId = '10000000-0000-4000-8000-000000000001';
const secondProjectId = '30000000-0000-4000-8000-000000000002';
const jobId = '20000000-0000-4000-8000-000000000001';
const replacementJobId = '20000000-0000-4000-8000-000000000002';
const now = new Date('2026-07-21T12:00:00.000Z');
const roots: string[] = [];

async function createRoot(prefix: string): Promise<string> {
  const root = await mkdtemp(join(tmpdir(), prefix));
  roots.push(root);
  return root;
}

async function createMp4(fileName = 'Cross Body Lead.mp4'): Promise<string> {
  const directory = await createRoot('cut-on-eight-source-');
  const source = join(directory, fileName);
  const bytes = Buffer.alloc(24);
  bytes.writeUInt32BE(bytes.length, 0);
  bytes.write('ftyp', 4, 'ascii');
  bytes.write('isom', 8, 'ascii');
  await writeFile(source, bytes);
  return source;
}

function picker(path: string | null): SourcePicker {
  return { selectMp4: async () => path };
}

function createService(
  layout: StorageLayout,
  source: string | null,
  overrides: Partial<ConstructorParameters<typeof ImportService>[1]> = {},
): ImportService {
  return new ImportService(layout, {
    picker: picker(source),
    createId: () => projectId,
    clock: () => now,
    jobs: new JobRepository(
      layout,
      () => jobId,
      () => now,
    ),
    ...overrides,
  });
}

afterEach(async () => {
  await Promise.all(
    roots.splice(0).map((root) => rm(root, { recursive: true, force: true })),
  );
});

describe('native MP4 picker', () => {
  it('uses fixed osascript arguments and returns the selected path', async () => {
    const calls: Array<{ executable: string; arguments_: readonly string[] }> =
      [];
    const runner: ProcessRunner = async (executable, arguments_) => {
      calls.push({ executable, arguments_ });
      return { stdout: '/Users/example/Dance.mp4\n', stderr: '' };
    };

    await expect(new MacOsSourcePicker(runner).selectMp4()).resolves.toBe(
      '/Users/example/Dance.mp4',
    );
    expect(calls).toHaveLength(1);
    expect(calls[0]?.executable).toBe('osascript');
    expect(calls[0]?.arguments_[0]).toBe('-e');
    expect(calls[0]?.arguments_[1]).toContain('public.mpeg-4');
    expect(calls[0]?.arguments_[1]).not.toContain('/Users/example/Dance.mp4');
  });

  it('maps AppleScript cancellation to null and other failures to a typed error', async () => {
    const cancellation: ProcessRunner = async () => {
      throw Object.assign(new Error('cancelled'), {
        stderr: 'execution error: User canceled. (-128)',
      });
    };
    const failure: ProcessRunner = async () => {
      throw new Error('osascript unavailable');
    };

    await expect(new MacOsSourcePicker(cancellation).selectMp4()).resolves.toBe(
      null,
    );
    await expect(
      new MacOsSourcePicker(failure).selectMp4(),
    ).rejects.toMatchObject({ code: 'native_picker_failed' });
  });
});

describe('MP4 source validation', () => {
  it('returns the canonical fingerprint for a regular ISO base-media MP4', async () => {
    const source = await createMp4();
    const validated = await validateMp4Source(source);

    expect(validated.path).toBe(await realpath(source));
    expect(validated.fingerprint).toMatchObject({
      realPath: await realpath(source),
      size: 24,
    });
    expect(validated.fingerprint.modifiedMilliseconds).toBeGreaterThan(0);
  });

  it('rejects empty, wrong-extension, and forged MP4 selections', async () => {
    const directory = await createRoot('cut-on-eight-invalid-source-');
    const empty = join(directory, 'empty.mp4');
    const wrongExtension = join(directory, 'video.mov');
    const forged = join(directory, 'forged.mp4');
    await writeFile(empty, Buffer.alloc(0));
    await writeFile(wrongExtension, Buffer.alloc(24));
    await writeFile(forged, Buffer.alloc(24));

    await expect(validateMp4Source(empty)).rejects.toMatchObject({
      code: 'invalid_mp4_source',
    });
    await expect(validateMp4Source(wrongExtension)).rejects.toMatchObject({
      code: 'invalid_mp4_source',
    });
    await expect(validateMp4Source(forged)).rejects.toMatchObject({
      code: 'invalid_mp4_source',
    });
  });
});

describe('transactional managed import', () => {
  it('does not create managed state when selection is cancelled', async () => {
    const parent = await createRoot('cut-on-eight-cancel-');
    const dataRoot = join(parent, 'managed');
    const service = createService(new StorageLayout(dataRoot), null);

    await expect(service.selectAndImport()).resolves.toEqual({
      outcome: 'cancelled',
    });
    await expect(access(dataRoot)).rejects.toMatchObject({ code: 'ENOENT' });
  });

  it('creates the managed source, sidecar, queued job, library, and workspace', async () => {
    const source = await createMp4();
    const dataRoot = await createRoot('cut-on-eight-import-');
    const layout = new StorageLayout(dataRoot);
    const paths = layout.forProject(projectId, 'Cross Body Lead.mp4');
    const service = createService(layout, source);

    await expect(service.selectAndImport()).resolves.toEqual({
      outcome: 'imported',
      projectId,
    });
    expect((await readdir(paths.directory)).sort()).toEqual(
      [
        'Cross Body Lead.mp4',
        'Cross Body Lead.mp4.danceclips.json',
        'jobs',
      ].sort(),
    );
    expect(await readFile(paths.source)).toEqual(await readFile(source));
    await expect(
      new ProjectRepository(layout).read(projectId, paths.relativeSource),
    ).resolves.toMatchObject({
      schemaVersion: 2,
      id: projectId,
      source: { fileName: 'Cross Body Lead.mp4' },
    });
    await expect(new LibraryRepository(layout).read()).resolves.toMatchObject({
      entries: [
        {
          id: projectId,
          managedSourcePath: paths.relativeSource,
          importedAt: now.toISOString(),
        },
      ],
    });
    await expect(new WorkspaceRepository(layout).read()).resolves.toEqual({
      schemaVersion: 1,
      openProjectIds: [projectId],
      activeProjectId: projectId,
    });
    expect(await readdir(paths.jobsDirectory)).toEqual([`${jobId}.json`]);
    expect(
      JSON.parse(
        await readFile(join(paths.jobsDirectory, `${jobId}.json`), 'utf8'),
      ),
    ).toMatchObject({
      id: jobId,
      projectId,
      type: 'inspect-source',
      state: 'queued',
      attempts: 0,
    });
  });

  it('reopens and activates an identical fingerprint without copying again', async () => {
    const source = await createMp4();
    const dataRoot = await createRoot('cut-on-eight-duplicate-');
    const layout = new StorageLayout(dataRoot);
    let copies = 0;
    const service = createService(layout, source, {
      copySource: async (...arguments_) => {
        copies += 1;
        const { copyFile } = await import('node:fs/promises');
        await copyFile(...arguments_);
      },
    });

    await service.selectAndImport();
    await new WorkspaceRepository(layout).save({
      schemaVersion: 1,
      openProjectIds: [],
      activeProjectId: null,
    });

    await expect(service.selectAndImport()).resolves.toEqual({
      outcome: 'reopened',
      projectId,
    });
    expect(copies).toBe(1);
    await expect(new WorkspaceRepository(layout).read()).resolves.toEqual({
      schemaVersion: 1,
      openProjectIds: [projectId],
      activeProjectId: projectId,
    });
  });

  it('creates a durable replacement inspection job before reopening a duplicate', async () => {
    const source = await createMp4();
    const dataRoot = await createRoot('cut-on-eight-missing-job-');
    const layout = new StorageLayout(dataRoot);
    const jobIds = [jobId, replacementJobId];
    const service = createService(layout, source, {
      jobs: new JobRepository(
        layout,
        () => jobIds.shift() ?? replacementJobId,
        () => now,
      ),
    });

    await service.selectAndImport();
    const paths = layout.forProject(projectId, 'Cross Body Lead.mp4');
    await rm(paths.jobsDirectory, { recursive: true, force: true });

    await expect(service.selectAndImport()).resolves.toEqual({
      outcome: 'reopened',
      projectId,
    });
    expect(await readdir(paths.jobsDirectory)).toEqual([
      `${replacementJobId}.json`,
    ]);
    expect(
      JSON.parse(
        await readFile(
          join(paths.jobsDirectory, `${replacementJobId}.json`),
          'utf8',
        ),
      ),
    ).toMatchObject({
      id: replacementJobId,
      projectId,
      type: 'inspect-source',
      state: 'queued',
    });
  });

  it('preserves a corrupt job while creating a valid replacement before reopen', async () => {
    const source = await createMp4();
    const dataRoot = await createRoot('cut-on-eight-corrupt-job-');
    const layout = new StorageLayout(dataRoot);
    const jobIds = [jobId, replacementJobId];
    const service = createService(layout, source, {
      jobs: new JobRepository(
        layout,
        () => jobIds.shift() ?? replacementJobId,
        () => now,
      ),
    });

    await service.selectAndImport();
    const paths = layout.forProject(projectId, 'Cross Body Lead.mp4');
    const corruptJob = join(paths.jobsDirectory, `${jobId}.json`);
    const corruptBytes = Buffer.from('{"schemaVersion":1,"broken":');
    await writeFile(corruptJob, corruptBytes);

    await expect(service.selectAndImport()).resolves.toEqual({
      outcome: 'reopened',
      projectId,
    });
    expect(await readFile(corruptJob)).toEqual(corruptBytes);
    expect((await readdir(paths.jobsDirectory)).sort()).toEqual(
      [`${jobId}.json`, `${replacementJobId}.json`].sort(),
    );
  });

  it.each([
    'managed MP4',
    'missing sidecar',
    'corrupt sidecar',
    'symlinked source',
  ] as const)(
    'removes a stale duplicate %s from the catalog and imports a fresh project',
    async (stalePart) => {
      const source = await createMp4();
      const dataRoot = await createRoot('cut-on-eight-stale-duplicate-');
      const layout = new StorageLayout(dataRoot);
      const ids = [projectId, secondProjectId];
      const service = createService(layout, source, {
        createId: () => ids.shift() ?? secondProjectId,
      });

      await service.selectAndImport();
      const stalePaths = layout.forProject(projectId, 'Cross Body Lead.mp4');

      switch (stalePart) {
        case 'managed MP4':
          await writeFile(stalePaths.source, Buffer.from('not an MP4'));
          break;
        case 'missing sidecar':
          await unlink(stalePaths.sidecar);
          break;
        case 'corrupt sidecar':
          await writeFile(stalePaths.sidecar, '{"schemaVersion":1,"broken":');
          break;
        case 'symlinked source':
          await unlink(stalePaths.source);
          await symlink(source, stalePaths.source, 'file');
          break;
      }

      await expect(service.selectAndImport()).resolves.toEqual({
        outcome: 'imported',
        projectId: secondProjectId,
      });
      await expect(new LibraryRepository(layout).read()).resolves.toMatchObject(
        {
          entries: [{ id: secondProjectId }],
        },
      );
      await expect(new WorkspaceRepository(layout).read()).resolves.toEqual({
        schemaVersion: 1,
        openProjectIds: [secondProjectId],
        activeProjectId: secondProjectId,
      });
      await expect(access(stalePaths.directory)).resolves.toBeUndefined();
    },
  );

  it.each([
    [
      'copy',
      { copySource: async () => Promise.reject(new Error('copy failed')) },
    ],
    [
      'sidecar write',
      { writeJson: async () => Promise.reject(new Error('write failed')) },
    ],
  ])('rolls back an injected %s failure', async (_label, overrides) => {
    const source = await createMp4();
    const dataRoot = await createRoot('cut-on-eight-rollback-');
    const layout = new StorageLayout(dataRoot);
    const service = createService(layout, source, overrides);

    await expect(service.selectAndImport()).rejects.toBeDefined();
    expect(await readdir(dataRoot)).toEqual([]);
    await expect(new LibraryRepository(layout).read()).resolves.toEqual({
      schemaVersion: 1,
      entries: [],
    });
    await expect(new WorkspaceRepository(layout).read()).resolves.toEqual({
      schemaVersion: 1,
      openProjectIds: [],
      activeProjectId: null,
    });
  });

  it('cleans stale importing directories during recovery', async () => {
    const dataRoot = await createRoot('cut-on-eight-stale-');
    const stale = join(dataRoot, 'stale--12345678.importing');
    await mkdir(stale);
    await writeFile(join(stale, 'partial.mp4'), 'partial');
    const service = createService(new StorageLayout(dataRoot), null);

    await service.recover();

    await expect(access(stale)).rejects.toMatchObject({ code: 'ENOENT' });
  });

  it('restores one thumbnail job for an inspected project during recovery', async () => {
    const source = await createMp4();
    const dataRoot = await createRoot('cut-on-eight-thumbnail-recovery-');
    const layout = new StorageLayout(dataRoot);
    const service = createService(layout, source);
    await service.selectAndImport();

    const paths = layout.forProject(projectId, 'Cross Body Lead.mp4');
    const projects = new ProjectRepository(layout);
    const current = await projects.readRequired(
      projectId,
      paths.relativeSource,
    );
    await projects.save(projectId, paths.relativeSource, {
      ...current,
      source: {
        ...current.source,
        durationSeconds: 12,
        width: 1280,
        height: 720,
        hasAudio: true,
        inspectedAt: now.toISOString(),
        inspectorVersion: 'ffprobe-v1',
      },
    });
    await rm(paths.jobsDirectory, { recursive: true, force: true });

    await service.recover();
    await service.recover();

    const jobFiles = await readdir(paths.jobsDirectory);
    expect(jobFiles).toEqual([`${jobId}.json`]);
    expect(
      JSON.parse(
        await readFile(join(paths.jobsDirectory, jobFiles[0]!), 'utf8'),
      ),
    ).toMatchObject({
      projectId,
      type: 'generate-thumbnails',
      state: 'queued',
      generatorVersion: 'thumbnail-overview-v1',
      sourceFingerprint: expect.stringMatching(/^sha256:[a-f0-9]{64}$/),
    });
  });

  it('reconciles a promoted import after a crash before catalog commit', async () => {
    const source = await createMp4();
    const dataRoot = await createRoot('cut-on-eight-recovery-');
    const layout = new StorageLayout(dataRoot);
    const realCatalog = new CatalogRepository(layout);
    let renames = 0;
    const interrupted = createService(layout, source, {
      catalog: {
        recover: () => realCatalog.recover(),
        commit: async () => {
          throw new Error('simulated process interruption');
        },
      },
      renameDirectory: async (from, to) => {
        renames += 1;

        if (renames === 2) {
          throw new Error('process stopped before rollback');
        }

        await rename(from, to);
      },
    });

    await expect(interrupted.selectAndImport()).rejects.toThrow(
      'simulated process interruption',
    );
    const paths = layout.forProject(projectId, 'Cross Body Lead.mp4');
    expect(await readdir(paths.directory)).toContain(
      '.cut-on-eight-import.json',
    );

    await createService(layout, null).recover();

    await expect(new LibraryRepository(layout).read()).resolves.toMatchObject({
      entries: [{ id: projectId }],
    });
    await expect(new WorkspaceRepository(layout).read()).resolves.toMatchObject(
      {
        openProjectIds: [projectId],
        activeProjectId: projectId,
      },
    );
    expect(await readdir(paths.directory)).not.toContain(
      '.cut-on-eight-import.json',
    );
  });

  it('does not publish a promoted marker whose sidecar is missing', async () => {
    const source = await createMp4();
    const dataRoot = await createRoot('cut-on-eight-missing-sidecar-marker-');
    const layout = new StorageLayout(dataRoot);
    const realCatalog = new CatalogRepository(layout);
    let renames = 0;
    const interrupted = createService(layout, source, {
      catalog: {
        recover: () => realCatalog.recover(),
        commit: async () => {
          throw new Error('simulated process interruption');
        },
      },
      renameDirectory: async (from, to) => {
        renames += 1;

        if (renames === 2) {
          throw new Error('process stopped before rollback');
        }

        await rename(from, to);
      },
    });

    await expect(interrupted.selectAndImport()).rejects.toBeDefined();
    const paths = layout.forProject(projectId, 'Cross Body Lead.mp4');
    await unlink(paths.sidecar);

    await expect(createService(layout, null).recover()).rejects.toMatchObject({
      code: 'missing_project_sidecar',
    });
    await expect(new LibraryRepository(layout).read()).resolves.toEqual({
      schemaVersion: 1,
      entries: [],
    });
    await expect(access(paths.directory)).resolves.toBeUndefined();
  });

  it('syncs copied media and the data root before catalog visibility', async () => {
    const source = await createMp4();
    const dataRoot = await createRoot('cut-on-eight-durability-order-');
    const layout = new StorageLayout(dataRoot);
    const realCatalog = new CatalogRepository(layout);
    const events: string[] = [];
    const service = createService(layout, source, {
      copySource: async (...arguments_) => {
        events.push('copy');
        const { copyFile } = await import('node:fs/promises');
        await copyFile(...arguments_);
      },
      syncFile: async () => {
        events.push('sync-file');
      },
      renameDirectory: async (from, to) => {
        events.push('rename');
        await rename(from, to);
      },
      syncDirectory: async (directory) => {
        expect(directory).toBe(dataRoot);
        events.push('sync-directory');
      },
      catalog: {
        recover: () => realCatalog.recover(),
        commit: async (library, workspace) => {
          events.push('catalog');
          await realCatalog.commit(library, workspace);
        },
      },
    });

    await service.selectAndImport();

    expect(events).toEqual([
      'copy',
      'sync-file',
      'rename',
      'sync-directory',
      'catalog',
    ]);
  });

  it('removes a leftover marker without deleting an indexed project', async () => {
    const source = await createMp4();
    const dataRoot = await createRoot('cut-on-eight-indexed-recovery-');
    const layout = new StorageLayout(dataRoot);
    const service = createService(layout, source, {
      removeFile: async () => {
        throw new Error('marker cleanup interrupted');
      },
    });

    await service.selectAndImport();
    const paths = layout.forProject(projectId, 'Cross Body Lead.mp4');
    expect(await readdir(paths.directory)).toContain(
      '.cut-on-eight-import.json',
    );

    await createService(layout, null).recover();

    await expect(access(paths.source)).resolves.toBeUndefined();
    await expect(new LibraryRepository(layout).read()).resolves.toMatchObject({
      entries: [{ id: projectId }],
    });
    expect(await readdir(paths.directory)).not.toContain(
      '.cut-on-eight-import.json',
    );
  });

  it('preserves a promoted folder when a failed catalog commit left it indexed', async () => {
    const source = await createMp4();
    const dataRoot = await createRoot('cut-on-eight-partial-catalog-');
    const layout = new StorageLayout(dataRoot);
    const library = new LibraryRepository(layout);
    const realCatalog = new CatalogRepository(layout);
    const service = createService(layout, source, {
      catalog: {
        recover: () => realCatalog.recover(),
        commit: async (libraryAfter) => {
          await library.save(libraryAfter);
          throw new Error('catalog rollback failed');
        },
      },
    });

    await expect(service.selectAndImport()).rejects.toThrow(
      'catalog rollback failed',
    );
    const paths = layout.forProject(projectId, 'Cross Body Lead.mp4');
    await expect(access(paths.source)).resolves.toBeUndefined();
    expect(await readdir(paths.directory)).toContain(
      '.cut-on-eight-import.json',
    );

    await createService(layout, null).recover();

    await expect(access(paths.source)).resolves.toBeUndefined();
    await expect(library.read()).resolves.toMatchObject({
      entries: [{ id: projectId }],
    });
    expect(await readdir(paths.directory)).not.toContain(
      '.cut-on-eight-import.json',
    );
  });
});
