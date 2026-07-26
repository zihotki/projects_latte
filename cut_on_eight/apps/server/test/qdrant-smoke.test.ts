import { randomUUID } from 'node:crypto';
import { afterAll, beforeAll, describe, expect, test } from 'vitest';
import type { Kysely } from 'kysely';
import {
  closeCatalogDatabase,
  createCatalogDatabase,
} from '../src/catalog/database.js';
import type { CatalogDatabase } from '../src/catalog/database-types.js';
import { migrateCatalog } from '../src/catalog/migrations/index.js';
import { appendFragmentProjectionEvent } from '../src/search/fragment-projection.js';
import {
  createFragmentProjectionStore,
  type FragmentProjectionStore,
} from '../src/search/qdrant-client.js';
import { rebuildFragmentProjection } from '../src/search/rebuild.js';
import { OutboxRelay } from '../src/events/outbox-relay.js';
import { runQdrantProjector } from '../src/events/consumers/qdrant-projector.js';
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

if (
  databaseUrl === undefined ||
  qdrantHttpUrl === undefined ||
  natsUrl === undefined
) {
  console.warn(
    'Skipping Qdrant smoke: PostgreSQL, Qdrant, and NATS test URLs are required',
  );
}

integration('Qdrant fragment projection', () => {
  let database: Kysely<CatalogDatabase>;
  let store: FragmentProjectionStore;
  let runtime: Awaited<ReturnType<typeof createJetStreamRuntime>>;
  let topology: Awaited<ReturnType<typeof createJetStreamManager>>;
  let releaseSuiteLock: (() => Promise<void>) | undefined;
  const videoId = randomUUID();
  const firstId = randomUUID();
  const secondId = randomUUID();
  const fragmentTagId = randomUUID();
  const videoTagId = randomUUID();

  beforeAll(async () => {
    releaseSuiteLock = await acquireDatabaseSuiteLock(databaseUrl!);
    database = createCatalogDatabase({ databaseUrl: databaseUrl! });
    await migrateCatalog(database);
    await resetCatalogTestState(database);
    store = createFragmentProjectionStore({
      qdrantHttpUrl,
      qdrantApiKey: null,
    });
    await store.recreate();
    runtime = await createJetStreamRuntime({ natsUrl: natsUrl! });
    topology = await createJetStreamManager({ natsUrl: natsUrl! });
    await ensurePipelineTopology(topology.manager);

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
      .values([
        {
          id: firstId,
          video_id: videoId,
          start_us: 100_000,
          end_us: 2_000_000,
          title: 'opening turn',
          description: 'Clean turn into promenade',
          export_selected: false,
          revision: 1,
        },
        {
          id: secondId,
          video_id: videoId,
          start_us: 3_000_000,
          end_us: 5_000_000,
          title: 'closing line',
          description: null,
          export_selected: false,
          revision: 1,
        },
      ])
      .execute();
    await database
      .insertInto('tags')
      .values([
        { id: fragmentTagId, name: 'turn' },
        { id: videoTagId, name: 'waltz' },
      ])
      .execute();
    await database
      .insertInto('fragment_tags')
      .values({ fragment_id: firstId, tag_id: fragmentTagId })
      .execute();
    await database
      .insertInto('video_tags')
      .values({ video_id: videoId, tag_id: videoTagId })
      .execute();
  });

  afterAll(async () => {
    try {
      await closeCatalogDatabase(database);
      await topology?.close();
      await runtime?.close();
    } finally {
      await releaseSuiteLock?.();
    }
  });

  test('relays immutable events into the eventual Qdrant projection', async () => {
    await database.transaction().execute(async (transaction) => {
      await appendFragmentProjectionEvent(transaction, firstId);
      await appendFragmentProjectionEvent(transaction, secondId);
    });
    await projectUntil(() => store.count().then((count) => count === 2));

    expect(await store.count()).toBe(2);
    expect(await store.get(firstId)).toMatchObject({
      id: firstId,
      payload: {
        projection_version: 1,
        projection_revision: 1,
        fragment_id: firstId,
        video_id: videoId,
        fragment_title: 'opening turn',
        fragment_tags: ['turn'],
        source_title: 'Viennese Waltz Practice',
        source_tags: ['waltz'],
      },
    });

    await database.transaction().execute(async (transaction) => {
      await transaction
        .updateTable('fragments')
        .set({
          deleted_at: new Date(),
          purge_after: new Date(Date.now() + 1_000),
          undo_token_hash: 'a'.repeat(64),
        })
        .where('id', '=', firstId)
        .execute();
      await appendFragmentProjectionEvent(transaction, firstId);
    });
    await projectUntil(() =>
      store.get(firstId).then((point) => point === null),
    );
    expect(await store.get(firstId)).toBeNull();

    await store.recreate();
    expect(await rebuildFragmentProjection(database, store)).toBe(1);
    expect(await store.count()).toBe(1);
    expect(await store.get(secondId)).toMatchObject({
      payload: { projection_version: 1, fragment_id: secondId },
    });
  });

  async function projectUntil(
    condition: () => Promise<boolean>,
  ): Promise<void> {
    let stopping = false;
    const projector = runQdrantProjector({
      database,
      runtime,
      store,
      stopping: () => stopping,
    });
    const relay = new OutboxRelay(database, runtime);
    await relay.publishAvailable();
    for (let attempt = 0; attempt < 100; attempt += 1) {
      if (await condition()) {
        stopping = true;
        await projector;
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
    stopping = true;
    await projector;
    throw new Error('Timed out waiting for Qdrant projection');
  }
});
