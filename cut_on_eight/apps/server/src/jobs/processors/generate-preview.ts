import type { Kysely } from 'kysely';
import { v7 as uuidv7 } from 'uuid';
import { blobKey, previewBlobKey } from '../../blobs/blob-key.js';
import type { BlobStore, LocalMediaFiles } from '../../blobs/blob-store.js';
import type { CatalogDatabase } from '../../catalog/database-types.js';
import { safeMicroseconds } from '../../catalog/database-types.js';
import { FragmentPreviewGenerator } from '../../media/fragment-preview-generator.js';

export interface PreviewJob {
  readonly videoId: string;
  readonly fragmentId: string;
  readonly expectedRevision: number;
}

export function createGeneratePreviewProcessor(
  database: Kysely<CatalogDatabase>,
  blobs: BlobStore & LocalMediaFiles,
  generator = new FragmentPreviewGenerator(blobs),
) {
  return async (job: PreviewJob): Promise<void> => {
    const row = await database
      .selectFrom('fragments')
      .innerJoin('videos', 'videos.id', 'fragments.video_id')
      .innerJoin('assets', 'assets.id', 'videos.source_asset_id')
      .select([
        'fragments.start_us',
        'fragments.end_us',
        'fragments.revision',
        'fragments.deleted_at',
        'assets.storage_key',
      ])
      .where('fragments.id', '=', job.fragmentId)
      .where('fragments.video_id', '=', job.videoId)
      .executeTakeFirst();
    if (
      row === undefined ||
      row.deleted_at !== null ||
      row.revision !== job.expectedRevision
    ) {
      return;
    }
    const existing = await database
      .selectFrom('fragment_previews')
      .select(['fragment_revision', 'status', 'asset_id'])
      .where('fragment_id', '=', job.fragmentId)
      .executeTakeFirst();
    if (
      existing?.fragment_revision === job.expectedRevision &&
      existing.status === 'ready' &&
      existing.asset_id !== null
    ) {
      return;
    }
    const generated = await blobs.withLocalPath(
      blobKey(row.storage_key),
      (sourcePath) =>
        generator.generate({
          sourcePath,
          startUs: safeMicroseconds(row.start_us),
          endUs: safeMicroseconds(row.end_us),
        }),
    );
    const destination = previewBlobKey(
      job.videoId,
      job.fragmentId,
      job.expectedRevision,
    );
    await blobs.publish(generated.staged, destination);
    const assetId = uuidv7();
    let keep = false;
    await database.transaction().execute(async (transaction) => {
      const current = await transaction
        .selectFrom('fragments')
        .select(['revision', 'deleted_at'])
        .where('id', '=', job.fragmentId)
        .forUpdate()
        .executeTakeFirst();
      if (
        current === undefined ||
        current.deleted_at !== null ||
        current.revision !== job.expectedRevision
      ) {
        return;
      }
      await transaction
        .insertInto('assets')
        .values({
          id: assetId,
          storage_key: destination,
          owner_kind: 'fragment',
          owner_id: job.fragmentId,
          kind: 'fragment_preview',
          mime_type: 'image/webp',
          size_bytes: generated.staged.size,
          sha256: generated.staged.sha256,
          revision: job.expectedRevision,
          state: 'ready',
        })
        .execute();
      await transaction
        .updateTable('fragment_previews')
        .set({
          asset_id: assetId,
          status: 'ready',
          sample_us: generated.sampleUs,
          columns: generated.columns,
          rows: generated.rows,
          frame_width: generated.frameWidth,
          frame_height: generated.frameHeight,
          failure_code: null,
          updated_at: new Date(),
        })
        .where('fragment_id', '=', job.fragmentId)
        .where('fragment_revision', '=', job.expectedRevision)
        .execute();
      keep = true;
    });
    if (!keep) await blobs.delete(destination);
  };
}
