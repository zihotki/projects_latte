import { fromKysely, type PgBoss } from 'pg-boss';
import type { Transaction } from 'kysely';
import type { CatalogDatabase } from '../../catalog/database-types.js';
import { envelope } from '../job-envelope.js';
import { jobNames } from '../job-contracts.js';

export interface DeleteAssetJob {
  readonly assetId: string;
  readonly storageKey: string;
}

export async function queueAssetDeletion(
  transaction: Transaction<CatalogDatabase>,
  boss: Pick<PgBoss, 'send'>,
  assetId: string | null,
): Promise<void> {
  if (assetId === null) return;
  const asset = await transaction
    .selectFrom('assets')
    .select('storage_key')
    .where('id', '=', assetId)
    .executeTakeFirst();
  if (asset === undefined) return;
  await transaction
    .updateTable('assets')
    .set({ state: 'deleting', updated_at: new Date() })
    .where('id', '=', assetId)
    .execute();
  await boss.send(
    jobNames.deleteAsset,
    envelope({ assetId, storageKey: asset.storage_key }),
    {
      db: fromKysely(transaction),
      singletonKey: assetId,
    },
  );
}
