import type { ProjectDocument } from '@cut-on-eight/contracts';
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { createApp } from '../src/app.js';
import type { ServerConfig } from '../src/config.js';
import type { AppServices } from '../src/services.js';
import {
  LibraryRepository,
  type LibraryDocument,
} from '../src/storage/library-repository.js';
import { StorageLayout } from '../src/storage/layout.js';
import { ProjectRepository } from '../src/storage/project-repository.js';

const projectId = '20000000-0000-4000-8000-000000000001';
const sourceBytes = Buffer.from('0123456789abcdef', 'utf8');
const roots: string[] = [];

async function fixture(): Promise<{ config: ServerConfig }> {
  const dataRoot = await mkdtemp(join(tmpdir(), 'cut-on-eight-range-'));
  roots.push(dataRoot);
  const layout = new StorageLayout(dataRoot);
  const paths = layout.forProject(projectId, 'Managed Source.mp4');
  const project: ProjectDocument = {
    schemaVersion: 2,
    id: projectId,
    source: {
      fileName: 'Managed Source.mp4',
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
  const entry: LibraryDocument['entries'][number] = {
    id: projectId,
    managedSourcePath: paths.relativeSource,
    fingerprint: {
      realPath: '/private/source/Managed Source.mp4',
      size: sourceBytes.length,
      modifiedMilliseconds: 1,
    },
    importedAt: '2026-07-21T10:00:00.000Z',
  };

  await mkdir(paths.directory, { recursive: true });
  await writeFile(paths.source, sourceBytes);
  await new ProjectRepository(layout).save(
    projectId,
    paths.relativeSource,
    project,
  );
  await new LibraryRepository(layout).save({
    schemaVersion: 1,
    entries: [entry],
  });

  return { config: { dataRoot, host: '127.0.0.1', port: 4318 } };
}

afterEach(async () => {
  await Promise.all(
    roots.splice(0).map((root) => rm(root, { recursive: true })),
  );
});

describe('managed MP4 byte-range API', () => {
  it('does not open a managed source for HEAD requests', async () => {
    let sourceOpenCount = 0;
    const unused = async (): Promise<never> => {
      throw new Error('Unexpected service call');
    };
    const services: AppServices = {
      activateProject: unused,
      closeProject: unused,
      getCapabilities: unused,
      getJobs: unused,
      getThumbnailManifest: unused,
      getWorkspace: unused,
      openProject: unused,
      openSource: async () => {
        sourceOpenCount += 1;
        throw new Error('HEAD must not open a source');
      },
      openThumbnailPage: unused,
      recover: async () => undefined,
      retryJob: unused,
      saveProject: unused,
      selectImport: unused,
      subscribeToJobs: () => () => undefined,
    };
    const app = createApp({ services });

    const response = await app.inject({
      method: 'HEAD',
      url: `/api/sources/${projectId}/content`,
    });

    expect(response.statusCode).toBe(404);
    expect(sourceOpenCount).toBe(0);
    await app.close();
  });

  it('streams the complete source with a 200 response', async () => {
    const { config } = await fixture();
    const app = createApp({ config });
    const response = await app.inject({
      method: 'GET',
      url: `/api/sources/${projectId}/content`,
    });

    expect(response.statusCode).toBe(200);
    expect(response.headers).toMatchObject({
      'accept-ranges': 'bytes',
      'content-length': String(sourceBytes.length),
      'content-type': 'video/mp4',
    });
    expect(response.rawPayload).toEqual(sourceBytes);
    await app.close();
  });

  it.each([
    ['normal', 'bytes=2-5', '2345', 'bytes 2-5/16'],
    ['open-ended', 'bytes=10-', 'abcdef', 'bytes 10-15/16'],
    ['suffix', 'bytes=-4', 'cdef', 'bytes 12-15/16'],
  ])('streams a valid %s range', async (_name, range, body, contentRange) => {
    const { config } = await fixture();
    const app = createApp({ config });
    const response = await app.inject({
      method: 'GET',
      url: `/api/sources/${projectId}/content`,
      headers: { range },
    });

    expect(response.statusCode).toBe(206);
    expect(response.headers).toMatchObject({
      'accept-ranges': 'bytes',
      'content-range': contentRange,
      'content-length': String(Buffer.byteLength(body)),
      'content-type': 'video/mp4',
    });
    expect(response.body).toBe(body);
    await app.close();
  });

  it.each(['bytes=16-', 'bytes=5-2', 'bytes=-0', 'bytes=0-1,4-5', 'items=0-1'])(
    'returns 416 for invalid or unsatisfiable range %s',
    async (range) => {
      const { config } = await fixture();
      const app = createApp({ config });
      const response = await app.inject({
        method: 'GET',
        url: `/api/sources/${projectId}/content`,
        headers: { range },
      });

      expect(response.statusCode).toBe(416);
      expect(response.headers).toMatchObject({
        'accept-ranges': 'bytes',
        'content-range': `bytes */${sourceBytes.length}`,
        'content-type': 'application/json; charset=utf-8',
      });
      expect(response.json()).toEqual({
        error: {
          code: 'invalid_range',
          message: 'The requested video byte range is not satisfiable.',
          retryable: false,
        },
      });
      await app.close();
    },
  );
});
