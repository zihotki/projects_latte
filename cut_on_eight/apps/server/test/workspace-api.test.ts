import type { ProjectDocument } from '@cut-on-eight/legacy-contracts';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { createApp } from '../src/app.js';
import type { ServerConfig } from '../src/config.js';
import type { SourcePicker } from '../src/imports/source-picker.js';
import type { ProbeResult } from '../src/jobs/ffprobe-runner.js';
import {
  LibraryRepository,
  type LibraryDocument,
} from '../src/storage/library-repository.js';
import { StorageLayout } from '../src/storage/layout.js';
import { ProjectRepository } from '../src/storage/project-repository.js';
import { WorkspaceRepository } from '../src/storage/workspace-repository.js';

const firstId = '10000000-0000-4000-8000-000000000001';
const secondId = '10000000-0000-4000-8000-000000000002';
const roots: string[] = [];

function project(id: string, fileName: string): ProjectDocument {
  return {
    schemaVersion: 3,
    id,
    source: {
      fileName,
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
  };
}

async function fixture(): Promise<{
  config: ServerConfig;
  first: ProjectDocument;
  layout: StorageLayout;
  second: ProjectDocument;
}> {
  const dataRoot = await mkdtemp(join(tmpdir(), 'cut-on-eight-api-'));
  roots.push(dataRoot);
  const layout = new StorageLayout(dataRoot);
  const first = project(firstId, 'First Dance.mp4');
  const second = project(secondId, 'Second Dance.mp4');
  const entries: LibraryDocument['entries'] = [
    {
      id: first.id,
      managedSourcePath: layout.forProject(first.id, first.source.fileName)
        .relativeSource,
      fingerprint: {
        realPath: '/private/source/First Dance.mp4',
        size: 12,
        modifiedMilliseconds: 1,
      },
      importedAt: '2026-07-21T10:00:00.000Z',
    },
    {
      id: second.id,
      managedSourcePath: layout.forProject(second.id, second.source.fileName)
        .relativeSource,
      fingerprint: {
        realPath: '/private/source/Second Dance.mp4',
        size: 12,
        modifiedMilliseconds: 2,
      },
      importedAt: '2026-07-21T10:01:00.000Z',
    },
  ];

  await new LibraryRepository(layout).save({ schemaVersion: 1, entries });
  await Promise.all(
    entries.map((entry, index) =>
      new ProjectRepository(layout).save(
        entry.id,
        entry.managedSourcePath,
        index === 0 ? first : second,
      ),
    ),
  );
  await new WorkspaceRepository(layout).save({
    schemaVersion: 1,
    openProjectIds: [second.id, first.id],
    activeProjectId: first.id,
  });

  return {
    config: {
      dataRoot,
      databaseUrl: 'postgres://localhost/cut_on_eight_test',
      qdrantHttpUrl: null,
      qdrantApiKey: null,
      host: '127.0.0.1',
      port: 4318,
    },
    first,
    layout,
    second,
  };
}

const cancelledPicker: SourcePicker = {
  selectMp4: async () => null,
};

async function createMp4(fileName: string): Promise<string> {
  const directory = await mkdtemp(join(tmpdir(), 'cut-on-eight-api-source-'));
  roots.push(directory);
  const source = join(directory, fileName);
  const bytes = Buffer.alloc(24);
  bytes.writeUInt32BE(bytes.length, 0);
  bytes.write('ftyp', 4, 'ascii');
  bytes.write('isom', 8, 'ascii');
  await writeFile(source, bytes);
  return source;
}

afterEach(async () => {
  await Promise.all(
    roots.splice(0).map((root) => rm(root, { recursive: true })),
  );
});

describe('managed workspace API', () => {
  it('restores order, activates projects, and never returns filesystem paths', async () => {
    const { config, first, second } = await fixture();
    const app = createApp({ config, picker: cancelledPicker });

    const restored = await app.inject({ method: 'GET', url: '/api/workspace' });
    expect(restored.statusCode).toBe(200);
    expect(restored.json()).toMatchObject({
      activeProjectId: first.id,
      openProjects: [{ id: second.id }, { id: first.id }],
      library: [{ id: first.id }, { id: second.id }],
    });
    expect(restored.body).not.toContain(config.dataRoot);
    expect(restored.body).not.toContain('/private/source');
    expect(restored.body).not.toContain('managedSourcePath');

    const activated = await app.inject({
      method: 'POST',
      url: `/api/projects/${second.id}/activate`,
    });
    expect(activated.statusCode).toBe(200);
    expect(activated.json()).toMatchObject({ activeProjectId: second.id });

    const cancelled = await app.inject({
      method: 'POST',
      url: '/api/imports/select',
    });
    expect(cancelled.statusCode).toBe(200);
    expect(cancelled.json()).toMatchObject({
      outcome: 'cancelled',
      workspace: { activeProjectId: second.id },
    });

    await app.close();
  });

  it('saves before close and reopens a closed managed project', async () => {
    const { config, first, layout } = await fixture();
    const app = createApp({ config, picker: cancelledPicker });
    const changed = { ...first, playbackPositionSeconds: 42.5 };

    const saved = await app.inject({
      method: 'PUT',
      url: `/api/projects/${first.id}`,
      payload: changed,
    });
    expect(saved.statusCode).toBe(200);
    expect(saved.json()).toEqual(changed);

    const closed = await app.inject({
      method: 'POST',
      url: `/api/projects/${first.id}/close`,
      payload: changed,
    });
    expect(closed.statusCode).toBe(200);
    expect(closed.json()).toMatchObject({
      activeProjectId: secondId,
      openProjects: [{ id: secondId }],
    });
    await expect(
      new ProjectRepository(layout).read(
        first.id,
        layout.forProject(first.id, first.source.fileName).relativeSource,
      ),
    ).resolves.toEqual(changed);

    const reopened = await app.inject({
      method: 'POST',
      url: `/api/projects/${first.id}/open`,
    });
    expect(reopened.statusCode).toBe(200);
    expect(reopened.json()).toMatchObject({
      activeProjectId: first.id,
      openProjects: [{ id: secondId }, { id: first.id }],
    });

    await app.close();
  });

  it('does not let a client save replace backend inspection metadata', async () => {
    const { config, first, layout } = await fixture();
    const projects = new ProjectRepository(layout);
    const managedSource = layout.forProject(
      first.id,
      first.source.fileName,
    ).relativeSource;
    const inspected: ProjectDocument = {
      ...first,
      source: {
        ...first.source,
        durationSeconds: 42,
        width: 1920,
        height: 1080,
        frameRateNumerator: 30_000,
        frameRateDenominator: 1_001,
        frameRateReliability: 'reliable',
        hasAudio: true,
        inspectedAt: '2026-07-21T12:00:00.000Z',
        inspectorVersion: 'ffprobe-v1',
      },
    };
    await projects.save(first.id, managedSource, inspected);
    const app = createApp({ config, picker: cancelledPicker });

    const response = await app.inject({
      method: 'PUT',
      url: `/api/projects/${first.id}`,
      payload: {
        ...inspected,
        source: {
          ...inspected.source,
          durationSeconds: 1,
          width: 1,
          frameRateNumerator: 1,
          frameRateDenominator: 1,
          inspectedAt: '2027-01-01T00:00:00.000Z',
          inspectorVersion: 'client',
        },
      },
    });

    expect(response.statusCode).toBe(200);
    expect(response.json().source).toEqual(inspected.source);
    await expect(projects.read(first.id, managedSource)).resolves.toMatchObject(
      {
        source: inspected.source,
      },
    );
    await app.close();
  });

  it('keeps a project open when its save fails and returns a safe error', async () => {
    const { config, first, layout } = await fixture();
    const app = createApp({ config, picker: cancelledPicker });
    const sidecar = layout.forProject(first.id, first.source.fileName).sidecar;
    const corruptBytes = '{ not-json';
    await writeFile(sidecar, corruptBytes, 'utf8');

    const response = await app.inject({
      method: 'POST',
      url: `/api/projects/${first.id}/close`,
      payload: first,
    });
    expect(response.statusCode).toBe(500);
    expect(response.json()).toEqual({
      error: {
        code: 'corrupt_persisted_data',
        message: 'Managed project data is corrupt and was left unchanged.',
        retryable: false,
      },
    });
    expect(response.body).not.toContain(config.dataRoot);
    expect(await readFile(sidecar, 'utf8')).toBe(corruptBytes);
    await expect(new WorkspaceRepository(layout).read()).resolves.toMatchObject(
      {
        openProjectIds: [secondId, first.id],
        activeProjectId: first.id,
      },
    );

    await app.close();
  });

  it('isolates unavailable closed sidecars and refuses to reopen corrupt data', async () => {
    const { config, first, layout, second } = await fixture();
    const workspace = new WorkspaceRepository(layout);
    await workspace.save({
      schemaVersion: 1,
      openProjectIds: [first.id],
      activeProjectId: first.id,
    });
    const sidecar = layout.forProject(
      second.id,
      second.source.fileName,
    ).sidecar;
    const corruptBytes = '{ not-json';
    await writeFile(sidecar, corruptBytes, 'utf8');
    const app = createApp({ config, picker: cancelledPicker });

    const restored = await app.inject({ method: 'GET', url: '/api/workspace' });
    expect(restored.statusCode).toBe(200);
    expect(restored.json()).toMatchObject({
      activeProjectId: first.id,
      openProjects: [{ id: first.id }],
      library: [
        { id: first.id, fileName: first.source.fileName },
        {
          id: second.id,
          fileName: second.source.fileName,
          durationSeconds: null,
        },
      ],
    });

    const reopened = await app.inject({
      method: 'POST',
      url: `/api/projects/${second.id}/open`,
    });
    expect(reopened.statusCode).toBe(500);
    expect(reopened.json()).toMatchObject({
      error: { code: 'project_data_unavailable', retryable: false },
    });
    expect(await readFile(sidecar, 'utf8')).toBe(corruptBytes);
    await expect(workspace.read()).resolves.toMatchObject({
      openProjectIds: [first.id],
      activeProjectId: first.id,
    });

    await rm(sidecar);
    const missing = await app.inject({ method: 'GET', url: '/api/workspace' });
    expect(missing.statusCode).toBe(200);
    expect(missing.json()).toMatchObject({
      openProjects: [{ id: first.id }],
      library: [
        { id: first.id },
        {
          id: second.id,
          fileName: second.source.fileName,
          durationSeconds: null,
        },
      ],
    });

    await app.close();
  });

  it('does not hold workspace mutations while the native picker is open', async () => {
    const { config, first, layout, second } = await fixture();
    const source = await createMp4('Deferred Choice.mp4');
    let releasePicker: (path: string) => void = () => undefined;
    let markPickerStarted: () => void = () => undefined;
    const pickerStarted = new Promise<void>((resolve) => {
      markPickerStarted = resolve;
    });
    const selectedPath = new Promise<string>((resolve) => {
      releasePicker = resolve;
    });
    let releaseInspection: (result: ProbeResult) => void = () => undefined;
    let markInspectionStarted: () => void = () => undefined;
    const inspectionStarted = new Promise<void>((resolve) => {
      markInspectionStarted = resolve;
    });
    const inspection = new Promise<ProbeResult>((resolve) => {
      releaseInspection = resolve;
    });
    const app = createApp({
      config,
      picker: {
        selectMp4: async () => {
          markPickerStarted();
          return selectedPath;
        },
      },
      probeRunner: {
        isAvailable: async () => false,
        inspect: async () => {
          markInspectionStarted();
          return inspection;
        },
      },
    });

    const importing = app.inject({
      method: 'POST',
      url: '/api/imports/select',
    });
    await pickerStarted;

    const changed = { ...first, playbackPositionSeconds: 27 };
    const closed = await app.inject({
      method: 'POST',
      url: `/api/projects/${first.id}/close`,
      payload: changed,
    });
    expect(closed.statusCode).toBe(200);
    expect(closed.json()).toMatchObject({
      activeProjectId: second.id,
      openProjects: [{ id: second.id }],
    });

    releasePicker(source);
    const imported = await importing;
    expect(imported.statusCode).toBe(200);
    expect(imported.json()).toMatchObject({
      outcome: 'imported',
      workspace: {
        openProjects: [
          { id: second.id },
          { source: { fileName: 'Deferred Choice.mp4' } },
        ],
      },
    });
    expect(
      imported
        .json()
        .workspace.openProjects.some(
          (candidate: ProjectDocument) => candidate.id === first.id,
        ),
    ).toBe(false);
    await expect(
      new ProjectRepository(layout).read(
        first.id,
        layout.forProject(first.id, first.source.fileName).relativeSource,
      ),
    ).resolves.toMatchObject({ playbackPositionSeconds: 27 });

    await inspectionStarted;
    let appClosed = false;
    const closing = app.close().then(() => {
      appClosed = true;
    });
    await new Promise<void>((resolve) => setImmediate(resolve));
    expect(appClosed).toBe(false);
    releaseInspection({
      durationSeconds: 60,
      frameRateNumerator: 30,
      frameRateDenominator: 1,
      frameRateReliability: 'reliable',
      hasAudio: true,
      height: 1080,
      width: 1920,
    });
    await closing;
  });

  it('does not close a project when an unrelated sidecar prevents a safe response', async () => {
    const { config, first, layout, second } = await fixture();
    const app = createApp({ config, picker: cancelledPicker });
    const unrelatedSidecar = layout.forProject(
      second.id,
      second.source.fileName,
    ).sidecar;
    await writeFile(unrelatedSidecar, '{ not-json', 'utf8');

    const response = await app.inject({
      method: 'POST',
      url: `/api/projects/${first.id}/close`,
      payload: { ...first, playbackPositionSeconds: 33 },
    });

    expect(response.statusCode).toBe(500);
    await expect(new WorkspaceRepository(layout).read()).resolves.toMatchObject(
      {
        openProjectIds: [second.id, first.id],
        activeProjectId: first.id,
      },
    );
    await expect(
      new ProjectRepository(layout).read(
        first.id,
        layout.forProject(first.id, first.source.fileName).relativeSource,
      ),
    ).resolves.toMatchObject({ playbackPositionSeconds: 0 });
    await app.close();
  });
});
