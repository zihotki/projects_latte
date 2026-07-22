import type {
  ProjectDocument,
  ThumbnailManifestV1,
} from '@cut-on-eight/contracts';
import { mkdir, mkdtemp, rm, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { createApp } from '../src/app.js';
import type { ServerConfig } from '../src/config.js';
import { thumbnailJobIdentity } from '../src/jobs/thumbnail-job.js';
import type { ThumbnailGenerator } from '../src/thumbnails/thumbnail-worker.js';
import {
  LibraryRepository,
  type LibraryEntry,
} from '../src/storage/library-repository.js';
import { StorageLayout } from '../src/storage/layout.js';
import { ProjectRepository } from '../src/storage/project-repository.js';

const firstId = '10000000-0000-4000-8000-000000000001';
const secondId = '10000000-0000-4000-8000-000000000002';
const roots: string[] = [];

const idleGenerator: ThumbnailGenerator = {
  generate: async () => {
    throw new Error('generation disabled in route tests');
  },
};

function project(id: string, fileName: string): ProjectDocument {
  return {
    schemaVersion: 2,
    id,
    source: {
      fileName,
      durationSeconds: 12,
      width: 1280,
      height: 720,
      frameRateNumerator: 30,
      frameRateDenominator: 1,
      frameRateReliability: 'reliable',
      hasAudio: true,
      inspectedAt: '2026-07-21T10:00:00.000Z',
      inspectorVersion: 'ffprobe-v1',
    },
    editor: { timelineZoom: 1, timelineOffsetSeconds: 0 },
    settings: { pauseAfterCreation: false },
    playbackPositionSeconds: 0,
    selectedSegmentId: null,
    segments: [],
    metadata: { title: null, tags: [], notes: null },
  };
}

function webp(width: number, height: number): Buffer {
  const bytes = Buffer.alloc(48);
  bytes.write('RIFF', 0, 'ascii');
  bytes.writeUInt32LE(40, 4);
  bytes.write('WEBPVP8X', 8, 'ascii');
  bytes.writeUInt32LE(10, 16);
  bytes.writeUIntLE(width - 1, 24, 3);
  bytes.writeUIntLE(height - 1, 27, 3);
  bytes.write('VP8 ', 30, 'ascii');
  bytes.writeUInt32LE(10, 34);
  bytes.writeUIntLE(0x2a019d, 41, 3);
  bytes.writeUInt16LE(width, 44);
  bytes.writeUInt16LE(height, 46);
  return bytes;
}

async function fixture(): Promise<{
  config: ServerConfig;
  entries: readonly [LibraryEntry, LibraryEntry];
  layout: StorageLayout;
}> {
  const dataRoot = await mkdtemp(join(tmpdir(), 'cut-on-eight-thumbnail-api-'));
  roots.push(dataRoot);
  const layout = new StorageLayout(dataRoot);
  const first = project(firstId, 'First.mp4');
  const second = project(secondId, 'Second.mp4');
  const entries = [first, second].map((item, index) => ({
    id: item.id,
    managedSourcePath: layout.forProject(item.id, item.source.fileName)
      .relativeSource,
    fingerprint: {
      realPath: `/source/${item.source.fileName}`,
      size: 100 + index,
      modifiedMilliseconds: index + 1,
    },
    importedAt: `2026-07-21T10:0${index}:00.000Z`,
  })) as unknown as readonly [LibraryEntry, LibraryEntry];
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
  return {
    config: { dataRoot, host: '127.0.0.1', port: 4318 },
    entries,
    layout,
  };
}

async function writeSet(
  layout: StorageLayout,
  entry: LibraryEntry,
  options: { corrupt?: boolean; symlinkPage?: boolean } = {},
): Promise<ThumbnailManifestV1> {
  const directory = layout.thumbnailsDirectory(entry.managedSourcePath);
  await mkdir(directory, { recursive: true });
  const identity = thumbnailJobIdentity(entry.fingerprint);
  const manifest: ThumbnailManifestV1 = {
    schemaVersion: 1,
    ...identity,
    durationSeconds: 12,
    thumbnail: [4, 2],
    pages: [['sprite-001.webp', 4, 2]],
    samples: [[0, 0, 0, 0, 4, 2]],
  };
  await writeFile(
    join(directory, 'manifest.json'),
    options.corrupt ? '{broken' : JSON.stringify(manifest),
  );
  if (options.symlinkPage) {
    const outside = join(layout.dataRoot, 'outside.webp');
    await writeFile(outside, webp(4, 2));
    await symlink(outside, join(directory, 'sprite-001.webp'));
  } else {
    await writeFile(join(directory, 'sprite-001.webp'), webp(4, 2));
  }
  return manifest;
}

afterEach(async () => {
  await Promise.all(
    roots.splice(0).map((root) => rm(root, { recursive: true, force: true })),
  );
});

describe('thumbnail routes', () => {
  it('returns a validated manifest and a complete immutable WebP response', async () => {
    const { config, entries, layout } = await fixture();
    const manifest = await writeSet(layout, entries[0]);
    const app = createApp({ config, thumbnailGenerator: idleGenerator });

    const manifestResponse = await app.inject({
      method: 'GET',
      url: `/api/projects/${firstId}/thumbnails/manifest`,
    });
    expect(manifestResponse.statusCode).toBe(200);
    expect(manifestResponse.json()).toEqual(manifest);

    const pageResponse = await app.inject({
      method: 'GET',
      url: `/api/projects/${firstId}/thumbnails/sprite-001.webp`,
      headers: { range: 'bytes=1-2' },
    });
    expect(pageResponse.statusCode).toBe(200);
    expect(pageResponse.rawPayload).toEqual(webp(4, 2));
    expect(pageResponse.headers).toMatchObject({
      'cache-control': 'public, max-age=31536000, immutable',
      'content-type': 'image/webp',
      'content-length': String(webp(4, 2).length),
    });
    await app.close();
  });

  it.each([
    ['missing', {}],
    ['corrupt manifest', { corrupt: true }],
    ['symlink sprite', { symlinkPage: true }],
  ])(
    'reports %s output as not ready and signals regeneration',
    async (_name, options) => {
      const { config, entries, layout } = await fixture();
      if (Object.keys(options).length > 0)
        await writeSet(layout, entries[0], options);
      const app = createApp({ config, thumbnailGenerator: idleGenerator });

      const response = await app.inject({
        method: 'GET',
        url: `/api/projects/${firstId}/thumbnails/manifest`,
      });
      expect(response.statusCode).toBe(404);
      expect(response.json()).toMatchObject({
        error: { code: 'thumbnail_not_ready' },
      });
      const jobs = await app.inject({ method: 'GET', url: '/api/jobs' });
      expect(jobs.json().jobs).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            projectId: firstId,
            type: 'generate-thumbnails',
          }),
        ]),
      );
      await app.close();
    },
  );

  it('rejects undeclared and traversal page names without affecting another project', async () => {
    const { config, entries, layout } = await fixture();
    await writeSet(layout, entries[0], { corrupt: true });
    await writeSet(layout, entries[1]);
    const app = createApp({ config, thumbnailGenerator: idleGenerator });

    const unknown = await app.inject({
      method: 'GET',
      url: `/api/projects/${secondId}/thumbnails/sprite-999.webp`,
    });
    expect(unknown.statusCode).toBe(404);
    expect(unknown.json()).toMatchObject({
      error: { code: 'thumbnail_page_not_found' },
    });

    const traversal = await app.inject({
      method: 'GET',
      url: `/api/projects/${secondId}/thumbnails/%2e%2e%2fsprite-001.webp`,
    });
    expect(traversal.statusCode).toBe(404);

    const healthy = await app.inject({
      method: 'GET',
      url: `/api/projects/${secondId}/thumbnails/manifest`,
    });
    expect(healthy.statusCode).toBe(200);
    await app.close();
  });
});
