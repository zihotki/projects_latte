import { randomUUID } from 'node:crypto';
import { afterAll, beforeAll, describe, expect, test, vi } from 'vitest';
import type { Kysely } from 'kysely';
import {
  closeCatalogDatabase,
  createCatalogDatabase,
} from '../src/catalog/database.js';
import type { CatalogDatabase } from '../src/catalog/database-types.js';
import { migrateCatalog } from '../src/catalog/migrations/index.js';
import { appendFragmentProjectionEvent } from '../src/search/fragment-projection.js';
import { createEmbeddingClient } from '../src/search/embedding-client.js';
import {
  collectionForProfile,
  createHybridSearchStore,
  type HybridSearchStore,
} from '../src/search/hybrid-qdrant-store.js';
import { createSearchIndexStateStore } from '../src/search/search-index-state.js';
import { runSearchIndexer } from '../src/search/search-indexer.js';
import { OutboxRelay } from '../src/events/outbox-relay.js';
import {
  createJetStreamManager,
  createJetStreamRuntime,
} from '../src/events/jetstream.js';
import { ensurePipelineTopology } from '../src/events/topology.js';
import {
  acquireDatabaseSuiteLock,
  resetCatalogTestState,
} from './database-test-harness.js';

const databaseUrl = process.env.CUT_ON_EIGHT_TEST_DATABASE_URL;
const qdrantHttpUrl = process.env.QDRANT_HTTPURI;
const natsUrl = process.env.NATS_URL;
const integration =
  databaseUrl === undefined ||
  qdrantHttpUrl === undefined ||
  natsUrl === undefined
    ? describe.skip
    : describe;

integration('semantic search lexical smoke', () => {
  const videoId = randomUUID();
  const fragmentId = randomUUID();
  const profile = {
    id: 'lexical-smoke-v1',
    model: 'unused',
    dimensions: 3,
    baseUrl: null,
  };
  let database: Kysely<CatalogDatabase>;
  let runtime: Awaited<ReturnType<typeof createJetStreamRuntime>>;
  let topology: Awaited<ReturnType<typeof createJetStreamManager>>;
  let store: HybridSearchStore;
  let releaseSuiteLock: (() => Promise<void>) | undefined;
  let stopping = false;
  let indexer: Promise<void> | undefined;

  beforeAll(async () => {
    releaseSuiteLock = await acquireDatabaseSuiteLock(databaseUrl!);
    database = createCatalogDatabase({ databaseUrl: databaseUrl! });
    await migrateCatalog(database);
    await resetCatalogTestState(database);
    runtime = await createJetStreamRuntime({ natsUrl: natsUrl! });
    topology = await createJetStreamManager({ natsUrl: natsUrl! });
    await ensurePipelineTopology(topology.manager);
    store = createHybridSearchStore({
      qdrantHttpUrl: qdrantHttpUrl!,
      qdrantApiKey: null,
    });
    await database
      .insertInto('videos')
      .values({
        id: videoId,
        source_asset_id: null,
        title: 'Viennese Waltz Practice',
        description: 'First rehearsal',
        original_file_name: 'waltz.mp4',
        status: 'ready',
        revision: 1,
      })
      .execute();
    await database
      .insertInto('fragments')
      .values({
        id: fragmentId,
        video_id: videoId,
        start_us: 100_000,
        end_us: 2_000_000,
        title: 'opening turn',
        description: 'Clean turn into promenade',
        export_selected: false,
        revision: 1,
      })
      .execute();

    indexer = runSearchIndexer({
      database,
      runtime,
      profile,
      collection: collectionForProfile(profile),
      store,
      embeddings: createEmbeddingClient(profile),
      indexState: createSearchIndexStateStore(database),
      stopping: () => stopping,
    });
  });

  afterAll(async () => {
    try {
      stopping = true;
      await indexer;
      await topology?.close();
      await runtime?.close();
      await closeCatalogDatabase(database);
    } finally {
      await releaseSuiteLock?.();
    }
  });

  test('indexes and removes fragment state through search-indexer-v1 without embeddings', async () => {
    const relay = new OutboxRelay(database, runtime);
    await database
      .transaction()
      .execute((transaction) =>
        appendFragmentProjectionEvent(transaction, fragmentId),
      );
    await relay.publishAvailable();
    await vi.waitFor(
      () =>
        expect(store.count(collectionForProfile(profile).name)).resolves.toBe(
          1,
        ),
      { timeout: 10_000 },
    );

    const matches = await store.query({
      collection: collectionForProfile(profile).name,
      lexicalText: 'promenade',
      limit: 10,
    });
    expect(matches).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          fragmentId,
          payload: expect.objectContaining({
            fragment_title: 'opening turn',
            source_title: 'Viennese Waltz Practice',
          }),
        }),
      ]),
    );

    await database.transaction().execute(async (transaction) => {
      await transaction
        .updateTable('fragments')
        .set({
          deleted_at: new Date(),
          purge_after: new Date(Date.now() + 1_000),
          undo_token_hash: 'a'.repeat(64),
        })
        .where('id', '=', fragmentId)
        .execute();
      await appendFragmentProjectionEvent(transaction, fragmentId);
    });
    await relay.publishAvailable();
    await vi.waitFor(
      () =>
        expect(store.count(collectionForProfile(profile).name)).resolves.toBe(
          0,
        ),
      { timeout: 10_000 },
    );
  }, 30_000);
});
