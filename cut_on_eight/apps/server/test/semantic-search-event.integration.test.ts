import { randomUUID } from 'node:crypto';
import { createServer, type Server } from 'node:http';
import { afterAll, beforeAll, describe, expect, test, vi } from 'vitest';
import type { Kysely } from 'kysely';
import {
  closeCatalogDatabase,
  createCatalogDatabase,
} from '../src/catalog/database.js';
import type { CatalogDatabase } from '../src/catalog/database-types.js';
import { migrateCatalog } from '../src/catalog/migrations/index.js';
import { createEmbeddingClient } from '../src/search/embedding-client.js';
import {
  collectionForProfile,
  createHybridSearchStore,
  type HybridSearchStore,
} from '../src/search/hybrid-qdrant-store.js';
import { createSearchIndexStateStore } from '../src/search/search-index-state.js';
import { runSearchIndexer } from '../src/search/search-indexer.js';
import { rebuildSemanticSearch } from '../src/search/rebuild-semantic-search.js';
import { OutboxRelay } from '../src/events/outbox-relay.js';
import { appendFragmentProjectionEvent } from '../src/search/fragment-projection.js';
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

integration('semantic search event delivery', () => {
  const videoId = randomUUID();
  const fragmentId = randomUUID();
  const profile = {
    id: 'embeddinggemma-v1',
    model: 'fake-embeddinggemma',
    dimensions: 3,
    baseUrl: '',
  };
  let database: Kysely<CatalogDatabase>;
  let runtime: Awaited<ReturnType<typeof createJetStreamRuntime>>;
  let topology: Awaited<ReturnType<typeof createJetStreamManager>>;
  let releaseSuiteLock: (() => Promise<void>) | undefined;
  let embeddings: FakeEmbeddingServer;
  let store: HybridSearchStore;
  let stopIndexer = false;
  let indexer: Promise<void> | undefined;

  beforeAll(async () => {
    releaseSuiteLock = await acquireDatabaseSuiteLock(databaseUrl!);
    database = createCatalogDatabase({ databaseUrl: databaseUrl! });
    await migrateCatalog(database);
    await resetCatalogTestState(database);
    embeddings = await startFakeEmbeddingServer();
    profile.baseUrl = embeddings.baseUrl;
    store = createHybridSearchStore({
      qdrantHttpUrl: qdrantHttpUrl!,
      qdrantApiKey: null,
    });
    runtime = await createJetStreamRuntime({ natsUrl: natsUrl! });
    topology = await createJetStreamManager({ natsUrl: natsUrl! });
    await ensurePipelineTopology(topology.manager);
    await database
      .insertInto('videos')
      .values({
        id: videoId,
        source_asset_id: null,
        title: 'Waltz practice',
        description: null,
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
        start_us: 0,
        end_us: 1_000_000,
        title: 'opening promenade',
        description: null,
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
      stopping: () => stopIndexer,
    });
  });

  afterAll(async () => {
    try {
      stopIndexer = true;
      await indexer;
      await embeddings?.close();
      await topology?.close();
      await runtime?.close();
      await closeCatalogDatabase(database);
    } finally {
      await releaseSuiteLock?.();
    }
  });

  test('retries an unavailable embedding endpoint and converges the durable state', async () => {
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
    const firstPosition = await latestPosition();
    await vi.waitFor(
      () => expect(indexedPosition()).resolves.toBe(firstPosition),
      { timeout: 10_000 },
    );

    embeddings.failRequests = true;
    await database.transaction().execute(async (transaction) => {
      await transaction
        .updateTable('fragments')
        .set({ title: 'recovered promenade', revision: 2 })
        .where('id', '=', fragmentId)
        .execute();
      await appendFragmentProjectionEvent(transaction, fragmentId);
    });
    const secondPosition = await latestPosition();
    await relay.publishAvailable();
    await vi.waitFor(
      () => expect(embeddings.requests).toBeGreaterThanOrEqual(2),
      {
        timeout: 10_000,
      },
    );
    expect(await indexedPosition()).toBe(firstPosition);

    embeddings.failRequests = false;
    await vi.waitFor(
      () => expect(indexedPosition()).resolves.toBe(secondPosition),
      { timeout: 15_000 },
    );
    const matches = await store.query({
      collection: collectionForProfile(profile).name,
      lexicalText: 'recovered',
      denseVector: [1, 0, 0],
      limit: 10,
    });
    expect(matches).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          fragmentId,
          payload: expect.objectContaining({
            fragment_title: 'recovered promenade',
          }),
        }),
      ]),
    );

    const run = await rebuildSemanticSearch({
      database,
      profile,
      store,
      embeddings: createEmbeddingClient(profile),
    });
    expect(run.status).toBe('ready');
    expect(await store.aliasTarget('cut_on_eight_fragments_active')).toBe(
      run.targetCollection,
    );
    expect(run.snapshotHighWaterPosition).toBeGreaterThanOrEqual(
      secondPosition,
    );

    const originalAlias = await store.aliasTarget(
      'cut_on_eight_fragments_active',
    );
    await expect(
      rebuildSemanticSearch({
        database,
        profile,
        store: countMismatchingStore(store),
        embeddings: createEmbeddingClient(profile),
      }),
    ).rejects.toThrow('Search rebuild validation failed');
    expect(await store.aliasTarget('cut_on_eight_fragments_active')).toBe(
      originalAlias,
    );
    await expect(
      database
        .selectFrom('semantic_search_rebuilds')
        .select('status')
        .orderBy('created_at', 'desc')
        .executeTakeFirstOrThrow(),
    ).resolves.toEqual({ status: 'failed' });
  }, 30_000);

  async function latestPosition(): Promise<number> {
    const row = await database
      .selectFrom('integration_events')
      .select('position')
      .orderBy('position', 'desc')
      .executeTakeFirstOrThrow();
    return Number(row.position);
  }

  async function indexedPosition(): Promise<number | null> {
    const row = await database
      .selectFrom('semantic_search_index_state')
      .select('last_source_position')
      .where('profile_id', '=', profile.id)
      .where('fragment_id', '=', fragmentId)
      .executeTakeFirst();
    return row?.last_source_position === null || row === undefined
      ? null
      : Number(row.last_source_position);
  }
});

function countMismatchingStore(store: HybridSearchStore): HybridSearchStore {
  return {
    ensureCollection: (target) => store.ensureCollection(target),
    upsert: (input) => store.upsert(input),
    delete: (collection, fragmentId) => store.delete(collection, fragmentId),
    query: (input) => store.query(input),
    count: async (collection) => (await store.count(collection)) + 1,
    aliasTarget: (alias) => store.aliasTarget(alias),
    setAlias: (alias, collection) => store.setAlias(alias, collection),
  };
}

interface FakeEmbeddingServer {
  readonly baseUrl: string;
  readonly server: Server;
  requests: number;
  failRequests: boolean;
  close(): Promise<void>;
}

async function startFakeEmbeddingServer(): Promise<FakeEmbeddingServer> {
  const state: FakeEmbeddingServer = {
    baseUrl: '',
    server: createServer(),
    requests: 0,
    failRequests: false,
    close: async () => undefined,
  };
  state.server.on('request', (_request, response) => {
    state.requests += 1;
    if (state.failRequests) {
      response.writeHead(503).end();
      return;
    }
    response.setHeader('content-type', 'application/json');
    response.end(
      JSON.stringify({
        data: [{ index: 0, embedding: [1, 0, 0] }],
      }),
    );
  });
  await new Promise<void>((resolve, reject) => {
    state.server.once('error', reject);
    state.server.listen(0, '127.0.0.1', resolve);
  });
  const address = state.server.address();
  if (address === null || typeof address === 'string') {
    throw new Error('Fake embedding endpoint did not expose a TCP port.');
  }
  state.baseUrl = `http://127.0.0.1:${address.port}/v1`;
  state.close = () =>
    new Promise<void>((resolve, reject) =>
      state.server.close((error) =>
        error === undefined ? resolve() : reject(error),
      ),
    );
  return state;
}
