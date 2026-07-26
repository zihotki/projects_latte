import type { Kysely } from 'kysely';
import { blobKey } from '../../blobs/blob-key.js';
import type { BlobStore } from '../../blobs/blob-store.js';
import type { CatalogDatabase } from '../../catalog/database-types.js';
import type { DeleteAssetJob } from './asset-deletion.js';

export function createDeleteAssetProcessor(
  database: Kysely<CatalogDatabase>,
  blobs: BlobStore,
) {
  return async (job: DeleteAssetJob): Promise<void> => {
    const asset = await database
      .selectFrom('assets')
      .select(['storage_key', 'state'])
      .where('id', '=', job.assetId)
      .executeTakeFirst();
    if (
      asset === undefined ||
      asset.state !== 'deleting' ||
      asset.storage_key !== job.storageKey
    ) {
      return;
    }
    await blobs.delete(blobKey(job.storageKey));
    await database
      .deleteFrom('assets')
      .where('id', '=', job.assetId)
      .where('storage_key', '=', job.storageKey)
      .where('state', '=', 'deleting')
      .execute();
  };
}
