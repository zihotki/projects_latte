import { rm } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import { resolve } from 'node:path';
import { afterAll, beforeAll, describe, expect, test, vi } from 'vitest';
import type { PgBoss } from 'pg-boss';
import {
  processingSnapshotSchema,
  uploadAcceptedSchema,
} from '@cut-on-eight/api-contracts';
import type { CutOnEightApp } from '../src/app.js';
import { createApp } from '../src/app.js';
import {
  closeCatalogDatabase,
  createCatalogDatabase,
} from '../src/catalog/database.js';
import { migrateCatalog } from '../src/catalog/migrations/index.js';
import type { ServerConfig } from '../src/config.js';
import { createRuntime } from '../src/runtime.js';
import type { ApiRuntime } from '../src/runtime.js';
import { VideoService } from '../src/videos/video-service.js';
import {
  acquireDatabaseSuiteLock,
  resetCatalogTestState,
} from './database-test-harness.js';

const databaseUrl = process.env.CUT_ON_EIGHT_TEST_DATABASE_URL;
const integration = databaseUrl === undefined ? describe.skip : describe;
const dataRoot = resolve('.local/test-data/video-workspace-api');

if (databaseUrl === undefined) {
  console.warn(
    'Skipping video/workspace integration: CUT_ON_EIGHT_TEST_DATABASE_URL is not configured',
  );
}

integration('video and workspace API', () => {
  let app: CutOnEightApp;
  let runtime: ApiRuntime;
  let videoId: string | undefined;
  let releaseSuiteLock: (() => Promise<void>) | undefined;
  const config: ServerConfig = {
    dataRoot,
    databaseUrl: databaseUrl!,
    qdrantHttpUrl: null,
    qdrantApiKey: null,
    embeddingProfile: {
      id: 'embeddinggemma-v1',
      model: 'google/embeddinggemma-300M',
      dimensions: 768,
      baseUrl: null,
    },
    maxUploadBytes: 1024 * 1024,
    host: '127.0.0.1',
    port: 4318,
  };

  beforeAll(async () => {
    releaseSuiteLock = await acquireDatabaseSuiteLock(databaseUrl!);
    const database = createCatalogDatabase(config);
    await migrateCatalog(database);
    await resetCatalogTestState(database);
    await closeCatalogDatabase(database);
    runtime = await createRuntime(config);
    app = createApp({ config, runtime });
    await app.ready();
  });

  afterAll(async () => {
    try {
      await app?.close();
      if (videoId !== undefined) {
        const database = createCatalogDatabase(config);
        await database.deleteFrom('videos').where('id', '=', videoId).execute();
        await database
          .deleteFrom('assets')
          .where('owner_id', '=', videoId)
          .execute();
        await closeCatalogDatabase(database);
      }
      await rm(dataRoot, { recursive: true, force: true });
    } finally {
      await releaseSuiteLock?.();
    }
  });

  test('publishes upload, opens it and serves ranges', async () => {
    const boundary = 'cut-on-eight-test-boundary';
    const response = await app.inject({
      method: 'POST',
      url: '/api/videos',
      headers: {
        'content-type': `multipart/form-data; boundary=${boundary}`,
      },
      payload: Buffer.concat([
        Buffer.from(
          `--${boundary}\r\nContent-Disposition: form-data; name="source"; filename="demo.mp4"\r\nContent-Type: video/mp4\r\n\r\n`,
        ),
        Buffer.from('managed-video-bytes'),
        Buffer.from(`\r\n--${boundary}--\r\n`),
      ]),
    });
    expect(response.statusCode).toBe(202);
    const accepted = uploadAcceptedSchema.parse(response.json());
    videoId = accepted.video.id;
    expect(accepted.workspace.activeVideoId).toBe(videoId);
    expect(accepted.video.status).toBe('queued');
    const processing = processingSnapshotSchema.parse(
      (await app.inject({ method: 'GET', url: '/api/processing' })).json(),
    );
    expect(processing.items).toContainEqual(
      expect.objectContaining({
        videoId,
        task: 'inspect',
        state: 'queued',
      }),
    );
    expect(accepted.workspace.library.some(({ id }) => id === videoId)).toBe(
      true,
    );
    const source = accepted.workspace.openVideos.find(
      ({ video }) => video.id === videoId,
    )?.source;
    expect(source).not.toBeNull();
    const range = await app.inject({
      method: 'GET',
      url: source!.href,
      headers: { range: 'bytes=8-12' },
    });
    expect(range.statusCode).toBe(206);
    expect(range.body).toBe('video');
  });

  test('counts all active videos while limiting processing rows', async () => {
    const ids = Array.from({ length: 105 }, () => randomUUID());
    try {
      await runtime.db
        .insertInto('videos')
        .values(
          ids.map((id) => ({
            id,
            title: 'Queued test video',
            original_file_name: 'test.mp4',
            status: 'queued' as const,
          })),
        )
        .execute();

      const response = await app.inject({
        method: 'GET',
        url: '/api/processing',
      });
      expect(response.statusCode).toBe(200);
      const snapshot = processingSnapshotSchema.parse(response.json());
      expect(snapshot.activeCount).toBeGreaterThanOrEqual(105);
      expect(snapshot.items).toHaveLength(100);
    } finally {
      await runtime.db.deleteFrom('videos').where('id', 'in', ids).execute();
    }
  });

  test('removes an upload and its source when catalog finalization rolls back', async () => {
    const sourceName = `rollback-${Date.now()}.mp4`;
    const publish = vi.spyOn(runtime.blobs, 'publish');
    const failingBoss = {
      send: vi.fn().mockRejectedValue(new Error('catalog finalization failed')),
    } as unknown as PgBoss;
    const service = new VideoService(
      runtime.db,
      failingBoss,
      runtime.blobs,
      runtime.workspace,
    );
    await expect(
      service.import({
        fileName: sourceName,
        mimeType: 'video/mp4',
        bytes: (async function* () {
          yield Buffer.from('already-published');
        })(),
      }),
    ).rejects.toThrow('catalog finalization failed');
    const failed = await runtime.db
      .selectFrom('videos')
      .select('id')
      .where('original_file_name', '=', sourceName)
      .executeTakeFirst();
    expect(failed).toBeUndefined();
    const key = publish.mock.lastCall?.[1];
    expect(key).toBeDefined();
    if (key === undefined) throw new Error('Expected a published source key');
    await expect(runtime.blobs.stat(key)).rejects.toThrow();
    publish.mockRestore();
  });
});
