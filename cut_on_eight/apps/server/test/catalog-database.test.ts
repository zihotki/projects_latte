import { randomUUID } from 'node:crypto';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import type { Kysely } from 'kysely';
import {
  closeCatalogDatabase,
  createCatalogDatabase,
} from '../src/catalog/database.js';
import type { CatalogDatabase } from '../src/catalog/database-types.js';
import { migrateCatalog } from '../src/catalog/migrations/index.js';

const databaseUrl = process.env.CUT_ON_EIGHT_TEST_DATABASE_URL;
const databaseDescribe = databaseUrl === undefined ? describe.skip : describe;

if (databaseUrl === undefined) {
  console.warn(
    'Skipping catalog database integration: CUT_ON_EIGHT_TEST_DATABASE_URL is not configured',
  );
}

databaseDescribe('catalog database migration', () => {
  let database: Kysely<CatalogDatabase>;
  const videoId = randomUUID();
  const fragmentId = randomUUID();
  const tagId = randomUUID();

  beforeAll(async () => {
    database = createCatalogDatabase({ databaseUrl: databaseUrl! });
    await migrateCatalog(database);
  });

  afterAll(async () => {
    if (database === undefined) {
      return;
    }
    await database
      .deleteFrom('tags')
      .where('id', '=', tagId)
      .execute()
      .catch(() => undefined);
    await database
      .deleteFrom('videos')
      .where('id', '=', videoId)
      .execute()
      .catch(() => undefined);
    await closeCatalogDatabase(database);
  });

  it('enforces fragment timing and canonical tag uniqueness', async () => {
    await database
      .insertInto('videos')
      .values({
        id: videoId,
        source_asset_id: null,
        title: 'Migration test',
        description: null,
        original_file_name: 'migration-test.mp4',
        duration_us: 3_000_000,
        width: 320,
        height: 180,
        has_audio: false,
        status: 'ready',
        revision: 1,
      })
      .execute();

    await database
      .insertInto('fragments')
      .values({
        id: fragmentId,
        video_id: videoId,
        start_us: 1_000,
        end_us: 2_000,
        title: null,
        description: null,
        export_selected: false,
        revision: 1,
        deleted_at: null,
      })
      .execute();

    await expect(
      database
        .insertInto('fragments')
        .values({
          id: randomUUID(),
          video_id: videoId,
          start_us: 2_000,
          end_us: 2_000,
          title: null,
          description: null,
          export_selected: false,
          revision: 1,
          deleted_at: null,
        })
        .execute(),
    ).rejects.toThrow();

    await database
      .insertInto('tags')
      .values({ id: tagId, name: 'dance' })
      .execute();
    await expect(
      database
        .insertInto('tags')
        .values({ id: randomUUID(), name: 'dance' })
        .execute(),
    ).rejects.toThrow();
    await expect(
      database
        .insertInto('tags')
        .values({ id: randomUUID(), name: 'Dance' })
        .execute(),
    ).rejects.toThrow();
  });
});
