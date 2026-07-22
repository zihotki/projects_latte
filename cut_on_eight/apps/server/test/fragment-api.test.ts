import type { ProjectDocument } from '@cut-on-eight/contracts';
import { access, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { createApp } from '../src/app.js';
import { LibraryRepository } from '../src/storage/library-repository.js';
import { StorageLayout } from '../src/storage/layout.js';
import { ProjectRepository } from '../src/storage/project-repository.js';
import { WorkspaceRepository } from '../src/storage/workspace-repository.js';
import { selectFragmentPreviews } from '../src/fragments/fragment-catalogue.js';

const projectId = '10000000-0000-4000-8000-000000000001';
const fragmentId = '20000000-0000-4000-8000-000000000001';
const roots: string[] = [];

function project(): ProjectDocument {
  return {
    schemaVersion: 3,
    id: projectId,
    source: {
      fileName: 'Dance.mp4',
      durationSeconds: 30,
      width: 1920,
      height: 1080,
      frameRateNumerator: 30,
      frameRateDenominator: 1,
      frameRateReliability: 'reliable',
      hasAudio: true,
      inspectedAt: '2026-07-22T10:00:00.000Z',
      inspectorVersion: 'ffprobe-v1',
    },
    editor: { timelineZoom: 1, timelineOffsetSeconds: 0 },
    settings: { pauseAfterCreation: false },
    playbackPositionSeconds: 0,
    selectedSegmentId: null,
    segments: [
      {
        id: fragmentId,
        startSeconds: 4,
        endSeconds: 9,
        exportSelected: true,
        title: null,
        tagIds: [],
      },
    ],
    metadata: { title: null, tags: [], notes: null },
  };
}

afterEach(async () => {
  await Promise.all(
    roots.splice(0).map((root) => rm(root, { recursive: true, force: true })),
  );
});

describe('fragment catalogue API', () => {
  it('aggregates, edits, deletes, restores, and safely deletes managed video data', async () => {
    const dataRoot = await mkdtemp(join(tmpdir(), 'cut-on-eight-fragments-'));
    const externalRoot = await mkdtemp(
      join(tmpdir(), 'cut-on-eight-original-'),
    );
    roots.push(dataRoot, externalRoot);
    const original = join(externalRoot, 'Dance.mp4');
    await writeFile(original, 'external original');
    const layout = new StorageLayout(dataRoot);
    const paths = layout.forProject(projectId, 'Dance.mp4');
    const entry = {
      id: projectId,
      managedSourcePath: paths.relativeSource,
      fingerprint: { realPath: original, size: 17, modifiedMilliseconds: 1 },
      importedAt: '2026-07-22T10:00:00.000Z',
    };
    await new LibraryRepository(layout).save({
      schemaVersion: 1,
      entries: [entry],
    });
    await new ProjectRepository(layout).save(
      projectId,
      paths.relativeSource,
      project(),
    );
    await writeFile(paths.source, 'managed copy');
    await new WorkspaceRepository(layout).save({
      schemaVersion: 1,
      openProjectIds: [projectId],
      activeProjectId: projectId,
    });
    const app = createApp({
      config: { dataRoot, host: '127.0.0.1', port: 4318 },
      picker: { selectMp4: async () => null },
    });

    const listed = await app.inject({ method: 'GET', url: '/api/fragments' });
    expect(listed.statusCode).toBe(200);
    expect(listed.json()).toMatchObject({
      fragments: [{ projectId, ordinal: 1, thumbnailState: 'unavailable' }],
      diagnostics: [],
    });

    const createdTag = await app.inject({
      method: 'POST',
      url: '/api/tags',
      payload: { name: '  SALSA  ' },
    });
    expect(createdTag.statusCode).toBe(200);
    expect(createdTag.json().name).toBe('salsa');

    const updated = await app.inject({
      method: 'PUT',
      url: `/api/projects/${projectId}/fragments/${fragmentId}`,
      payload: {
        startSeconds: 4.1,
        endSeconds: 9.1,
        exportSelected: false,
        title: '  Cross body  ',
        tagIds: [createdTag.json().id],
      },
    });
    expect(updated.statusCode).toBe(200);
    expect(updated.json()).toMatchObject({
      title: 'Cross body',
      tagIds: [createdTag.json().id],
    });

    const deleted = await app.inject({
      method: 'DELETE',
      url: `/api/projects/${projectId}/fragments/${fragmentId}`,
    });
    expect(deleted.statusCode).toBe(200);
    expect(
      (await app.inject({ method: 'GET', url: '/api/fragments' })).json()
        .fragments,
    ).toEqual([]);

    const restored = await app.inject({
      method: 'POST',
      url: `/api/projects/${projectId}/fragments/${fragmentId}/restore`,
      payload: deleted.json(),
    });
    expect(restored.statusCode).toBe(200);

    const removed = await app.inject({
      method: 'DELETE',
      url: `/api/projects/${projectId}`,
    });
    expect(removed.statusCode).toBe(200);
    expect(removed.json()).toMatchObject({
      activeProjectId: null,
      openProjects: [],
      library: [],
    });
    await expect(access(original)).resolves.toBeUndefined();
    await app.close();
  });

  it('selects nearest distinct samples for the five target positions', () => {
    const segment = project()
      .segments[0] as ProjectDocument['segments'][number];
    const previews = selectFragmentPreviews(segment, {
      schemaVersion: 1,
      generatorVersion: 'v1',
      sourceFingerprint: 'fingerprint',
      durationSeconds: 30,
      thumbnail: [160, 90],
      pages: [['sprite-001.webp', 800, 90]],
      samples: [4, 5, 6, 7, 8, 9].map((seconds, index) => [
        seconds,
        0,
        index * 100,
        0,
        100,
        90,
      ]),
    });
    expect(previews.map((preview) => preview.sampleSeconds)).toEqual([
      4, 5, 6, 7, 8,
    ]);
  });
});
