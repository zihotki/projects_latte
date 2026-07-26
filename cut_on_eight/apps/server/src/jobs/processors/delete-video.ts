import type { Kysely } from 'kysely';
import { blobKey } from '../../blobs/blob-key.js';
import type { BlobStore } from '../../blobs/blob-store.js';
import type { CatalogDatabase } from '../../catalog/database-types.js';

export function createDeleteVideoProcessor(
  database: Kysely<CatalogDatabase>,
  blobs: BlobStore,
) {
  return async ({
    videoId,
    expectedRevision,
  }: {
    videoId: string;
    expectedRevision: number;
  }) => {
    const video = await database
      .selectFrom('videos')
      .select(['revision', 'status'])
      .where('id', '=', videoId)
      .executeTakeFirst();
    if (
      video === undefined ||
      video.status !== 'deleting' ||
      video.revision !== expectedRevision
    ) {
      return;
    }
    const assets = await database
      .selectFrom('assets')
      .select(['id', 'storage_key'])
      .where((builder) =>
        builder.or([
          builder.and([
            builder('owner_kind', '=', 'video'),
            builder('owner_id', '=', videoId),
          ]),
          builder(
            'owner_id',
            'in',
            database
              .selectFrom('fragments')
              .select('id')
              .where('video_id', '=', videoId),
          ),
        ]),
      )
      .execute();
    for (const asset of assets) await blobs.delete(blobKey(asset.storage_key));
    await database
      .deleteFrom('fragment_previews')
      .where(
        'fragment_id',
        'in',
        database
          .selectFrom('fragments')
          .select('id')
          .where('video_id', '=', videoId),
      )
      .execute();
    await database.deleteFrom('videos').where('id', '=', videoId).execute();
    if (assets.length > 0) {
      await database
        .deleteFrom('assets')
        .where(
          'id',
          'in',
          assets.map(({ id }) => id),
        )
        .execute();
    }
  };
}
