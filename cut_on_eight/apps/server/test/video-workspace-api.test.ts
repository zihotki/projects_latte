import { rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import { afterAll, beforeAll, describe, expect, test } from 'vitest';
import { uploadAcceptedSchema } from '@cut-on-eight/api-contracts';
import type { CutOnEightApp } from '../src/app.js';
import { createApp } from '../src/app.js';
import {
  closeCatalogDatabase,
  createCatalogDatabase,
} from '../src/catalog/database.js';
import { migrateCatalog } from '../src/catalog/migrations/index.js';
import type { ServerConfig } from '../src/config.js';
import { createRuntime } from '../src/runtime.js';

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
  let videoId: string | undefined;
  const config: ServerConfig = {
    dataRoot,
    databaseUrl: databaseUrl!,
    qdrantHttpUrl: null,
    qdrantApiKey: null,
    maxUploadBytes: 1024 * 1024,
    host: '127.0.0.1',
    port: 4318,
  };

  beforeAll(async () => {
    const database = createCatalogDatabase(config);
    await migrateCatalog(database);
    await closeCatalogDatabase(database);
    const runtime = await createRuntime(config);
    app = createApp({ config, runtime });
    await app.ready();
  });

  afterAll(async () => {
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
    const source = accepted.workspace.openVideos[0]?.source;
    expect(source).not.toBeNull();
    const range = await app.inject({
      method: 'GET',
      url: source!.href,
      headers: { range: 'bytes=8-12' },
    });
    expect(range.statusCode).toBe(206);
    expect(range.body).toBe('video');
  });
});
