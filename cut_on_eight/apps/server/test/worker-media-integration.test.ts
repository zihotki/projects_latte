import { readFile, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import { randomUUID } from 'node:crypto';
import { afterAll, beforeAll, describe, expect, test } from 'vitest';
import type { Kysely } from 'kysely';
import { previewBlobKey, sourceBlobKey } from '../src/blobs/blob-key.js';
import { LocalBlobStore } from '../src/blobs/local-blob-store.js';
import {
  closeCatalogDatabase,
  createCatalogDatabase,
} from '../src/catalog/database.js';
import type { CatalogDatabase } from '../src/catalog/database-types.js';
import { migrateCatalog } from '../src/catalog/migrations/index.js';
import { createGeneratePreviewProcessor } from '../src/jobs/processors/generate-preview.js';
import { createInspectVideoProcessor } from '../src/jobs/processors/inspect-video.js';
import { FragmentPreviewGenerator } from '../src/media/fragment-preview-generator.js';

const databaseUrl = process.env.CUT_ON_EIGHT_TEST_DATABASE_URL;
const integration = databaseUrl === undefined ? describe.skip : describe;
const dataRoot = resolve('.local/test-data/worker-media');

if (databaseUrl === undefined) {
  console.warn(
    'Skipping worker/media integration: CUT_ON_EIGHT_TEST_DATABASE_URL is not configured',
  );
}

describe('fragment preview generator', () => {
  test('creates one five-frame WebP contact sheet', async () => {
    const root = resolve('.local/test-data/preview-generator');
    const store = new LocalBlobStore(root);
    const videoId = randomUUID();
    const fragmentId = randomUUID();
    try {
      const bytes = await readFile(resolve('test/fixtures/tiny.mp4'));
      const staged = await store.writeStaged(
        (async function* () {
          yield bytes;
        })(),
      );
      const source = sourceBlobKey(videoId, 'tiny.mp4');
      await store.publish(staged, source);
      const generated = await store.withLocalPath(source, (sourcePath) =>
        new FragmentPreviewGenerator(store).generate({
          sourcePath,
          startUs: 100_000,
          endUs: 1_900_000,
        }),
      );
      expect(generated.sampleUs).toHaveLength(5);
      const preview = previewBlobKey(videoId, fragmentId, 1);
      await store.publish(generated.staged, preview);
      const range = await store.openRange(preview);
      const chunks: Buffer[] = [];
      for await (const chunk of range.stream) chunks.push(Buffer.from(chunk));
      const webp = Buffer.concat(chunks);
      expect(webp.toString('ascii', 0, 4)).toBe('RIFF');
      expect(webp.toString('ascii', 8, 12)).toBe('WEBP');
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });
});

integration('media workers', () => {
  let database: Kysely<CatalogDatabase>;
  const blobs = new LocalBlobStore(dataRoot);
  const videoId = randomUUID();
  const assetId = randomUUID();
  const fragmentId = randomUUID();

  beforeAll(async () => {
    database = createCatalogDatabase({ databaseUrl: databaseUrl! });
    await migrateCatalog(database);
    const bytes = await readFile(resolve('test/fixtures/tiny.mp4'));
    const staged = await blobs.writeStaged(
      (async function* () {
        yield bytes;
      })(),
    );
    const key = sourceBlobKey(videoId, 'tiny.mp4');
    await blobs.publish(staged, key);
    await database
      .insertInto('assets')
      .values({
        id: assetId,
        storage_key: key,
        owner_kind: 'video',
        owner_id: videoId,
        kind: 'source',
        mime_type: 'video/mp4',
        size_bytes: staged.size,
        sha256: staged.sha256,
        state: 'ready',
      })
      .execute();
    await database
      .insertInto('videos')
      .values({
        id: videoId,
        source_asset_id: assetId,
        title: 'Tiny',
        description: null,
        original_file_name: 'tiny.mp4',
        status: 'queued',
        revision: 1,
      })
      .execute();
  });

  afterAll(async () => {
    await database?.deleteFrom('videos').where('id', '=', videoId).execute();
    await database
      ?.deleteFrom('assets')
      .where('owner_id', '=', videoId)
      .execute();
    if (database !== undefined) await closeCatalogDatabase(database);
    await rm(dataRoot, { recursive: true, force: true });
  });

  test('inspects and generates an idempotent five-frame WebP', async () => {
    const inspect = createInspectVideoProcessor(database, blobs);
    await inspect({ videoId, expectedRevision: 1 });
    await inspect({ videoId, expectedRevision: 1 });
    const video = await database
      .selectFrom('videos')
      .select(['status', 'duration_us'])
      .where('id', '=', videoId)
      .executeTakeFirstOrThrow();
    expect(video.status).toBe('ready');
    expect(Number(video.duration_us)).toBeGreaterThan(1_000_000);

    await database
      .insertInto('fragments')
      .values({
        id: fragmentId,
        video_id: videoId,
        start_us: 100_000,
        end_us: 1_900_000,
        title: null,
        description: null,
        export_selected: false,
        revision: 1,
      })
      .execute();
    await database
      .insertInto('fragment_previews')
      .values({
        fragment_id: fragmentId,
        fragment_revision: 1,
        asset_id: null,
        status: 'pending',
        sample_us: [],
        columns: 1,
        rows: 1,
        frame_width: 320,
        frame_height: 180,
        failure_code: null,
      })
      .execute();
    const generate = createGeneratePreviewProcessor(database, blobs);
    await generate({ videoId, fragmentId, expectedRevision: 1 });
    await generate({ videoId, fragmentId, expectedRevision: 0 });
    const preview = await database
      .selectFrom('fragment_previews')
      .select(['status', 'sample_us', 'columns'])
      .where('fragment_id', '=', fragmentId)
      .executeTakeFirstOrThrow();
    expect(preview.status).toBe('ready');
    expect(preview.sample_us).toHaveLength(5);
    expect(preview.columns).toBe(5);
  });
});
