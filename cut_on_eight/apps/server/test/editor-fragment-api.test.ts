import { randomUUID } from 'node:crypto';
import { rm } from 'node:fs/promises';
import { afterAll, beforeAll, describe, expect, test, vi } from 'vitest';
import type { PgBoss } from 'pg-boss';
import type { Kysely } from 'kysely';
import {
  deletedFragmentSchema,
  editorVideoSchema,
  fragmentListSchema,
  fragmentSchema,
  tagSchema,
} from '@cut-on-eight/api-contracts';
import { createApp, type CutOnEightApp } from '../src/app.js';
import { LocalBlobStore } from '../src/blobs/local-blob-store.js';
import { previewBlobKey } from '../src/blobs/blob-key.js';
import {
  closeCatalogDatabase,
  createCatalogDatabase,
} from '../src/catalog/database.js';
import type { CatalogDatabase } from '../src/catalog/database-types.js';
import { migrateCatalog } from '../src/catalog/migrations/index.js';
import type { ServerConfig } from '../src/config.js';
import { FragmentService } from '../src/fragments/fragment-service.js';
import type { ApiRuntime } from '../src/runtime.js';
import { VideoService } from '../src/videos/video-service.js';
import { WorkspaceRepository } from '../src/workspace/workspace-repository.js';
import { WorkspaceService } from '../src/workspace/workspace-service.js';
import {
  acquireDatabaseSuiteLock,
  resetCatalogTestState,
} from './database-test-harness.js';

const databaseUrl = process.env.CUT_ON_EIGHT_TEST_DATABASE_URL;
const integration = databaseUrl === undefined ? describe.skip : describe;

if (databaseUrl === undefined) {
  console.warn(
    'Skipping editor/fragment integration: CUT_ON_EIGHT_TEST_DATABASE_URL is not configured',
  );
}

integration('editor and fragment API', () => {
  let database: Kysely<CatalogDatabase>;
  let app: CutOnEightApp;
  let blobs: LocalBlobStore;
  let releaseSuiteLock: (() => Promise<void>) | undefined;
  const videoId = randomUUID();
  const firstId = randomUUID();
  const secondId = randomUUID();
  const thirdId = randomUUID();
  const config: ServerConfig = {
    dataRoot: `${process.cwd()}/.local/test-data/editor-fragment-api`,
    databaseUrl: databaseUrl!,
    qdrantHttpUrl: null,
    qdrantApiKey: null,
    maxUploadBytes: 1024 * 1024,
    host: '127.0.0.1',
    port: 4318,
  };

  beforeAll(async () => {
    releaseSuiteLock = await acquireDatabaseSuiteLock(databaseUrl!);
    database = createCatalogDatabase(config);
    await migrateCatalog(database);
    await resetCatalogTestState(database);
    await database
      .insertInto('videos')
      .values({
        id: videoId,
        source_asset_id: null,
        title: 'Editor test',
        description: null,
        original_file_name: 'editor.mp4',
        duration_us: 10_000_000,
        width: 320,
        height: 180,
        has_audio: false,
        status: 'ready',
        revision: 1,
      })
      .execute();
    await new WorkspaceRepository(database).open(videoId);
    const boss = {
      send: vi.fn().mockResolvedValue(randomUUID()),
    } as unknown as PgBoss;
    blobs = new LocalBlobStore(config.dataRoot);
    const workspace = new WorkspaceService(database);
    const runtime: ApiRuntime = {
      db: database,
      boss,
      blobs,
      workspace,
      fragments: new FragmentService(database, boss, workspace),
      videos: new VideoService(database, boss, blobs, workspace),
      close: async () => undefined,
    };
    app = createApp({ config, runtime });
    await app.ready();
  });

  afterAll(async () => {
    try {
      await app?.close();
      await database?.deleteFrom('videos').where('id', '=', videoId).execute();
      await database
        ?.deleteFrom('assets')
        .where('owner_kind', '=', 'fragment')
        .where('owner_id', 'in', [firstId, secondId, thirdId])
        .execute();
      if (database !== undefined) await closeCatalogDatabase(database);
      await rm(config.dataRoot, { recursive: true, force: true });
    } finally {
      await releaseSuiteLock?.();
    }
  });

  test('enforces overlaps and revisions, then deletes and restores with Undo', async () => {
    const tagResponse = await app.inject({
      method: 'POST',
      url: '/api/tags',
      payload: { name: 'Dance' },
    });
    expect(tagResponse.statusCode).toBe(201);
    const tag = tagSchema.parse(tagResponse.json());
    expect(tag.name).toBe('dance');

    const savedResponse = await app.inject({
      method: 'PATCH',
      url: `/api/videos/${videoId}/editor`,
      payload: editorSave(
        1,
        [
          fragment(firstId, null, 0, 3_000_000, [tag.id]),
          fragment(secondId, null, 1_000_000, 4_000_000, []),
        ],
        firstId,
      ),
    });
    expect(savedResponse.statusCode).toBe(200);
    const saved = editorVideoSchema.parse(savedResponse.json());
    expect(saved.fragments).toHaveLength(2);
    expect(saved.editor.selectedFragmentId).toBe(firstId);

    const overlap = await app.inject({
      method: 'PATCH',
      url: `/api/videos/${videoId}/editor`,
      payload: editorSave(saved.video.revision, [
        ...saved.fragments.map((item) =>
          fragment(
            item.id,
            item.revision,
            item.startUs,
            item.endUs,
            item.tags.map(({ id }) => id),
          ),
        ),
        fragment(thirdId, null, 2_000_000, 5_000_000, []),
      ]),
    });
    expect(overlap.statusCode).toBe(409);
    expect(overlap.json()).toMatchObject({ code: 'fragment_timing_conflict' });

    const first = saved.fragments.find(({ id }) => id === firstId)!;
    const patchedResponse = await app.inject({
      method: 'PATCH',
      url: `/api/fragments/${firstId}`,
      payload: {
        expectedRevision: first.revision,
        startUs: 100_000,
        endUs: 2_900_000,
        title: 'opening',
        description: null,
        exportSelected: true,
        tagIds: [tag.id],
      },
    });
    expect(patchedResponse.statusCode).toBe(200);
    const patched = fragmentSchema.parse(patchedResponse.json());
    expect(patched.title).toBe('opening');

    const stale = await app.inject({
      method: 'PATCH',
      url: `/api/fragments/${firstId}`,
      payload: {
        expectedRevision: first.revision,
        startUs: 100_000,
        endUs: 2_900_000,
        title: 'stale',
        description: null,
        exportSelected: true,
        tagIds: [tag.id],
      },
    });
    expect(stale.statusCode).toBe(409);
    expect(stale.json()).toMatchObject({ code: 'stale_revision' });

    const previewAssetId = randomUUID();
    const previewKey = previewBlobKey(videoId, firstId, patched.revision);
    const stagedPreview = await blobs.writeStaged(
      (async function* () {
        yield Buffer.from('preview');
      })(),
    );
    await blobs.publish(stagedPreview, previewKey);
    await database
      .insertInto('assets')
      .values({
        id: previewAssetId,
        storage_key: previewKey,
        owner_kind: 'fragment',
        owner_id: firstId,
        kind: 'fragment_preview',
        mime_type: 'image/webp',
        size_bytes: stagedPreview.size,
        sha256: stagedPreview.sha256,
        revision: patched.revision,
        state: 'ready',
      })
      .execute();
    await database
      .updateTable('fragment_previews')
      .set({
        asset_id: previewAssetId,
        status: 'ready',
        sample_us: [100_000],
      })
      .where('fragment_id', '=', firstId)
      .execute();
    expect(
      (
        await app.inject({
          method: 'GET',
          url: `/api/assets/${previewAssetId}`,
        })
      ).statusCode,
    ).toBe(200);

    const deletedResponse = await app.inject({
      method: 'DELETE',
      url: `/api/fragments/${firstId}`,
      payload: { expectedRevision: patched.revision },
    });
    const deleted = deletedFragmentSchema.parse(deletedResponse.json());
    const hidden = fragmentListSchema.parse(
      (await app.inject({ method: 'GET', url: '/api/fragments' })).json(),
    );
    expect(hidden.some(({ id }) => id === firstId)).toBe(false);
    expect(
      (
        await app.inject({
          method: 'GET',
          url: `/api/assets/${previewAssetId}`,
        })
      ).statusCode,
    ).toBe(404);

    const restoredResponse = await app.inject({
      method: 'POST',
      url: `/api/fragments/${firstId}/restore`,
      payload: { undoToken: deleted.undoToken },
    });
    const restored = fragmentSchema.parse(restoredResponse.json());
    expect(restored.id).toBe(firstId);
    expect(restored.tags).toEqual([tag]);
    expect(
      (
        await app.inject({
          method: 'GET',
          url: `/api/assets/${previewAssetId}`,
        })
      ).statusCode,
    ).toBe(200);
  });
});

function editorSave(
  expectedVideoRevision: number,
  fragments: ReturnType<typeof fragment>[],
  selectedFragmentId: string | null = null,
) {
  return {
    expectedVideoRevision,
    title: 'Editor test',
    description: null,
    tagIds: [],
    playbackPositionUs: 0,
    editor: {
      selectedFragmentId,
      pauseAfterCreation: false,
      timelineZoom: 1,
      timelineOffsetUs: 0,
    },
    fragments,
  };
}

function fragment(
  id: string,
  expectedRevision: number | null,
  startUs: number,
  endUs: number,
  tagIds: string[],
) {
  return {
    id,
    expectedRevision,
    startUs,
    endUs,
    title: null,
    description: null,
    exportSelected: false,
    tagIds,
  };
}
