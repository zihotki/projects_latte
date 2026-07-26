import type { Kysely } from 'kysely';
import type { CatalogDatabase } from '../../catalog/database-types.js';

export function createPurgeFragmentProcessor(
  database: Kysely<CatalogDatabase>,
) {
  return async ({ fragmentId }: { fragmentId: string }): Promise<void> => {
    await database
      .deleteFrom('fragments')
      .where('id', '=', fragmentId)
      .where('deleted_at', 'is not', null)
      .where('purge_after', '<=', new Date())
      .execute();
  };
}
