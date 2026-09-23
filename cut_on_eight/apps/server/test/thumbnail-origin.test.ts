import { afterEach, describe, expect, it } from 'vitest';
import type { Kysely } from 'kysely';
import type { CatalogDatabase } from '../src/catalog/database-types.js';
import { createThumbnailOrigin } from '../src/thumbnails/thumbnail-origin.js';
import type { ThumbnailBundleStore } from '../src/thumbnails/thumbnail-bundle-store.js';

describe('thumbnail origin', () => {
  const apps: Array<ReturnType<typeof createThumbnailOrigin>> = [];
  afterEach(async () => {
    await Promise.all(apps.splice(0).map((app) => app.close()));
  });

  it('reports failed generation without exposing the failure detail', async () => {
    const database = {
      selectFrom: () => ({
        select: () => ({
          where: () => ({
            executeTakeFirst: async () => ({
              status: 'failed',
              storage_key: null,
              manifest: null,
            }),
          }),
        }),
      }),
    } as unknown as Kysely<CatalogDatabase>;
    const app = createThumbnailOrigin({
      database,
      bundles: {} as ThumbnailBundleStore,
    });
    apps.push(app);

    const response = await app.inject({
      method: 'GET',
      url: '/thumbnail-cdn/v1/videos/00000000-0000-4000-8000-000000000001/manifest.json',
    });

    expect(response.statusCode).toBe(404);
    expect(response.headers['x-thumbnail-state']).toBe('failed');
    expect(response.body).not.toContain('failure_code');
  });
});
