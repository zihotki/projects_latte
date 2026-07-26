import { readFile, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import { randomUUID } from 'node:crypto';
import { afterAll, beforeAll, describe, expect, test, vi } from 'vitest';
import type { PgBoss } from 'pg-boss';
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
import { createPurgeFragmentProcessor } from '../src/jobs/processors/purge-fragment.js';
import { createDeleteAssetProcessor } from '../src/jobs/processors/delete-asset.js';
import { FragmentPreviewGenerator } from '../src/media/fragment-preview-generator.js';
import {
  acquireDatabaseSuiteLock,
  resetCatalogTestState,
} from './database-test-harness.js';

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
  let releaseSuiteLock: (() => Promise<void>) | undefined;
  const blobs = new LocalBlobStore(dataRoot);
  const videoId = randomUUID();
  const assetId = randomUUID();
  const fragmentId = randomUUID();
  const sourceKey = sourceBlobKey(videoId, 'tiny.mp4');

  beforeAll(async () => {
    releaseSuiteLock = await acquireDatabaseSuiteLock(databaseUrl!);
    database = createCatalogDatabase({ databaseUrl: databaseUrl! });
    await migrateCatalog(database);
    await resetCatalogTestState(database);
    const bytes = await readFile(resolve('test/fixtures/tiny.mp4'));
    const staged = await blobs.writeStaged(
      (async function* () {
        yield bytes;
      })(),
    );
    await blobs.publish(staged, sourceKey);
    await database
      .insertInto('assets')
      .values({
        id: assetId,
        storage_key: sourceKey,
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
    try {
      await database?.deleteFrom('videos').where('id', '=', videoId).execute();
      await database
        ?.deleteFrom('assets')
        .where('owner_id', '=', videoId)
        .execute();
      if (database !== undefined) await closeCatalogDatabase(database);
      await rm(dataRoot, { recursive: true, force: true });
    } finally {
      await releaseSuiteLock?.();
    }
  });

  test('inspects and generates an idempotent five-frame WebP', async () => {
    const inspect = createInspectVideoProcessor(database, blobs);
    await database
      .updateTable('videos')
      .set({ title: 'Edited while queued', revision: 2 })
      .where('id', '=', videoId)
      .execute();
    await inspect({ videoId, sourceAssetId: assetId });
    await inspect({ videoId, sourceAssetId: assetId });
    const video = await database
      .selectFrom('videos')
      .select(['status', 'duration_us', 'revision', 'title'])
      .where('id', '=', videoId)
      .executeTakeFirstOrThrow();
    expect(video.status).toBe('ready');
    expect(Number(video.duration_us)).toBeGreaterThan(1_000_000);
    expect(video.revision).toBe(3);
    expect(video.title).toBe('Edited while queued');

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
    const failedGenerate = createGeneratePreviewProcessor(database, blobs, {
      generate: vi
        .fn()
        .mockRejectedValue(new Error('preview generation failed')),
    } as unknown as FragmentPreviewGenerator);
    await expect(
      failedGenerate(
        { videoId, fragmentId, expectedRevision: 1 },
        { terminalFailure: false },
      ),
    ).rejects.toThrow('preview generation failed');
    expect(
      await database
        .selectFrom('fragment_previews')
        .select(['status', 'failure_code'])
        .where('fragment_id', '=', fragmentId)
        .executeTakeFirstOrThrow(),
    ).toMatchObject({
      status: 'pending',
      failure_code: null,
    });
    await expect(
      failedGenerate({ videoId, fragmentId, expectedRevision: 1 }),
    ).rejects.toThrow('preview generation failed');
    expect(
      await database
        .selectFrom('fragment_previews')
        .select(['status', 'failure_code'])
        .where('fragment_id', '=', fragmentId)
        .executeTakeFirstOrThrow(),
    ).toMatchObject({
      status: 'failed',
      failure_code: 'fragment_preview_generation_failed',
    });
    const orphan = await blobs.withLocalPath(sourceKey, (sourcePath) =>
      new FragmentPreviewGenerator(blobs).generate({
        sourcePath,
        startUs: 100_000,
        endUs: 1_900_000,
      }),
    );
    const previewKey = previewBlobKey(videoId, fragmentId, 1);
    await blobs.publish(orphan.staged, previewKey);
    let releaseRetry!: () => void;
    const retryGate = new Promise<void>((resolveRetry) => {
      releaseRetry = resolveRetry;
    });
    const generate = createGeneratePreviewProcessor(database, blobs, {
      async generate() {
        await retryGate;
        return orphan;
      },
    } as unknown as FragmentPreviewGenerator);
    const retry = generate({ videoId, fragmentId, expectedRevision: 1 });
    await vi.waitFor(async () => {
      expect(
        (
          await database
            .selectFrom('fragment_previews')
            .select('status')
            .where('fragment_id', '=', fragmentId)
            .executeTakeFirstOrThrow()
        ).status,
      ).toBe('pending');
    });
    releaseRetry();
    await retry;
    await generate({ videoId, fragmentId, expectedRevision: 0 });
    const preview = await database
      .selectFrom('fragment_previews')
      .select(['status', 'sample_us', 'columns'])
      .where('fragment_id', '=', fragmentId)
      .executeTakeFirstOrThrow();
    expect(preview.status).toBe('ready');
    expect(preview.sample_us).toHaveLength(5);
    expect(preview.columns).toBe(5);

    const asset = await database
      .selectFrom('assets')
      .select(['id', 'storage_key'])
      .where('owner_id', '=', fragmentId)
      .executeTakeFirstOrThrow();
    const send = vi.fn().mockResolvedValue(randomUUID());
    const boss = { send } as unknown as PgBoss;
    const deletedAt = new Date(Date.now() - 2_000);
    await database
      .updateTable('fragments')
      .set({
        deleted_at: deletedAt,
        purge_after: new Date(deletedAt.getTime() + 1_000),
        undo_token_hash: 'a'.repeat(64),
      })
      .where('id', '=', fragmentId)
      .execute();
    await createPurgeFragmentProcessor(database, boss)({ fragmentId });
    expect(
      await database
        .selectFrom('fragments')
        .select('id')
        .where('id', '=', fragmentId)
        .executeTakeFirst(),
    ).toBeUndefined();
    const deleteEnvelope = vi
      .mocked(send)
      .mock.calls.find(([name]) => name === 'asset.delete.v1')?.[1] as {
      payload: { assetId: string; storageKey: string };
    };
    await createDeleteAssetProcessor(database, blobs)(deleteEnvelope.payload);
    expect(
      await database
        .selectFrom('assets')
        .select('id')
        .where('id', '=', asset.id)
        .executeTakeFirst(),
    ).toBeUndefined();
    await expect(blobs.stat(previewKey)).rejects.toThrow();

    const probe = { inspect: vi.fn() };
    await database
      .updateTable('videos')
      .set({ status: 'deleting', revision: 4 })
      .where('id', '=', videoId)
      .execute();
    await createInspectVideoProcessor(
      database,
      blobs,
      probe,
    )({
      videoId,
      sourceAssetId: assetId,
    });
    expect(probe.inspect).not.toHaveBeenCalled();
    expect(
      (
        await database
          .selectFrom('videos')
          .select('status')
          .where('id', '=', videoId)
          .executeTakeFirstOrThrow()
      ).status,
    ).toBe('deleting');
  });
});
