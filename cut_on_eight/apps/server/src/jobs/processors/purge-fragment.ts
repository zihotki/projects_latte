import { type PgBoss } from 'pg-boss';
import type { Kysely } from 'kysely';
import type { CatalogDatabase } from '../../catalog/database-types.js';
import { queueAssetDeletion } from './asset-deletion.js';

export function createPurgeFragmentProcessor(
  database: Kysely<CatalogDatabase>,
  boss: Pick<PgBoss, 'send'>,
) {
  return async ({ fragmentId }: { fragmentId: string }): Promise<void> => {
    await database.transaction().execute(async (transaction) => {
      const fragment = await transaction
        .selectFrom('fragments')
        .leftJoin(
          'fragment_previews',
          'fragment_previews.fragment_id',
          'fragments.id',
        )
        .select([
          'fragments.deleted_at',
          'fragments.purge_after',
          'fragment_previews.asset_id',
        ])
        .where('fragments.id', '=', fragmentId)
        .forUpdate('fragments')
        .executeTakeFirst();
      if (
        fragment?.deleted_at === null ||
        fragment?.deleted_at === undefined ||
        fragment.purge_after === null ||
        fragment.purge_after.getTime() > Date.now()
      ) {
        return;
      }
      await queueAssetDeletion(transaction, boss, fragment.asset_id);
      await transaction
        .deleteFrom('fragments')
        .where('id', '=', fragmentId)
        .execute();
    });
  };
}
