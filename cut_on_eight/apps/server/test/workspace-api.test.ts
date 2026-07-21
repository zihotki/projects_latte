import type { ProjectDocument } from '@cut-on-eight/contracts';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { createApp } from '../src/app.js';
import type { ServerConfig } from '../src/config.js';
import type { SourcePicker } from '../src/imports/source-picker.js';
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
    schemaVersion: 1,
    id,
    source: {
      fileName,
      durationSeconds: null,
      width: null,
      height: null,
      frameRate: null,
      hasAudio: null,
    },
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
    config: { dataRoot, host: '127.0.0.1', port: 4318 },
    first,
    layout,
    second,
  };
}

const cancelledPicker: SourcePicker = {
  selectMp4: async () => null,
};

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
});
