import {
  healthReadySchema,
  problemDetailsSchema,
} from '@cut-on-eight/api-contracts';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import type { Kysely } from 'kysely';
import { createApp } from '../src/app.js';
import {
  closeCatalogDatabase,
  createCatalogDatabase,
} from '../src/catalog/database.js';
import type { CatalogDatabase } from '../src/catalog/database-types.js';
import { migrateCatalog } from '../src/catalog/migrations/index.js';
import { createHealthProbes } from '../src/api/health-routes.js';
import type { ServerConfig } from '../src/config.js';
import {
  acquireDatabaseSuiteLock,
  resetCatalogTestState,
} from './database-test-harness.js';

const databaseUrl = process.env.CUT_ON_EIGHT_TEST_DATABASE_URL;
const databaseDescribe = databaseUrl === undefined ? describe.skip : describe;

if (databaseUrl === undefined) {
  console.warn(
    'Skipping health integration: CUT_ON_EIGHT_TEST_DATABASE_URL is not configured',
  );
}

databaseDescribe('catalog health routes', () => {
  let database: Kysely<CatalogDatabase>;
  let releaseSuiteLock: (() => Promise<void>) | undefined;
  const config: ServerConfig = {
    dataRoot: '/tmp/cut-on-eight-health-integration',
    databaseUrl: databaseUrl!,
    qdrantHttpUrl: 'http://qdrant.invalid',
    qdrantApiKey: null,
    host: '127.0.0.1',
    port: 4318,
  };

  beforeAll(async () => {
    releaseSuiteLock = await acquireDatabaseSuiteLock(databaseUrl!);
    database = createCatalogDatabase(config);
    await migrateCatalog(database);
    await resetCatalogTestState(database);
  });

  afterAll(async () => {
    try {
      await closeCatalogDatabase(database).catch(() => undefined);
    } finally {
      await releaseSuiteLock?.();
    }
  });

  it('reports real PostgreSQL readiness and optional dependency state', async () => {
    const app = createApp({
      config,
      healthProbes: createHealthProbes(database, config, async () => undefined),
    });

    const ready = await app.inject({
      method: 'GET',
      url: '/api/health/ready',
    });

    expect(ready.statusCode).toBe(200);
    expect(healthReadySchema.parse(ready.json())).toMatchObject({
      status: 'ready',
      dependencies: {
        postgres: 'ready',
        qdrant: 'ready',
        worker: 'unavailable',
      },
    });

    await app.close();
  });

  it('returns Problem Details when PostgreSQL is unavailable', async () => {
    const app = createApp({
      config,
      healthProbes: createHealthProbes(database, config, async () => undefined),
    });
    await closeCatalogDatabase(database);

    const unavailable = await app.inject({
      method: 'GET',
      url: '/api/health/ready',
    });

    expect(unavailable.statusCode).toBe(503);
    expect(problemDetailsSchema.parse(unavailable.json())).toMatchObject({
      status: 503,
      code: 'catalog_unavailable',
    });

    await app.close();
  });
});
