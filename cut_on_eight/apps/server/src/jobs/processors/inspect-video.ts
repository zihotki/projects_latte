import { sql, type Kysely } from 'kysely';
import { blobKey } from '../../blobs/blob-key.js';
import type { LocalMediaFiles } from '../../blobs/blob-store.js';
import type { CatalogDatabase } from '../../catalog/database-types.js';
import { FfprobeRunner, type ProbeRunner } from '../ffprobe-runner.js';

export interface InspectVideoJob {
  readonly videoId: string;
  readonly sourceAssetId: string;
}

export function createInspectVideoProcessor(
  database: Kysely<CatalogDatabase>,
  files: LocalMediaFiles,
  probe: ProbeRunner = new FfprobeRunner(),
) {
  return async ({ videoId, sourceAssetId }: InspectVideoJob): Promise<void> => {
    await database.connection().execute(async (connection) => {
      const lockKey = `${videoId}:${sourceAssetId}`;
      const lock = await sql<{ locked: boolean }>`
        select pg_try_advisory_lock(hashtextextended(${lockKey}, 0)) as locked
      `.execute(connection);
      if (lock.rows[0]?.locked !== true) return;
      try {
        await inspectClaimedSource(
          connection,
          files,
          probe,
          videoId,
          sourceAssetId,
        );
      } finally {
        await sql`
          select pg_advisory_unlock(hashtextextended(${lockKey}, 0))
        `.execute(connection);
      }
    });
  };
}

async function inspectClaimedSource(
  database: Kysely<CatalogDatabase>,
  files: LocalMediaFiles,
  probe: ProbeRunner,
  videoId: string,
  sourceAssetId: string,
): Promise<void> {
  const claimed = await database
    .updateTable('videos')
    .set({
      status: 'processing',
      processing_failure_code: null,
      processing_failure_retryable: null,
      processing_failure_at: null,
      updated_at: new Date(),
    })
    .where('id', '=', videoId)
    .where('source_asset_id', '=', sourceAssetId)
    .where('status', 'in', ['queued', 'processing', 'failed'])
    .returning('source_asset_id')
    .executeTakeFirst();
  if (claimed === undefined) return;
  const asset = await database
    .selectFrom('assets')
    .select('storage_key')
    .where('id', '=', sourceAssetId)
    .where('owner_kind', '=', 'video')
    .where('owner_id', '=', videoId)
    .where('state', '=', 'ready')
    .executeTakeFirst();
  if (asset === undefined) {
    await failInspection(database, videoId, sourceAssetId);
    throw new Error('The source asset is unavailable');
  }
  try {
    const result = await files.withLocalPath(
      blobKey(asset.storage_key),
      (path) => probe.inspect(path),
    );
    const durationUs = Math.round(result.durationSeconds * 1_000_000);
    if (!Number.isSafeInteger(durationUs) || durationUs <= 0) {
      throw new Error('Inspected duration is outside the supported range');
    }
    await database
      .updateTable('videos')
      .set({
        duration_us: durationUs,
        width: result.width,
        height: result.height,
        frame_rate_numerator: result.frameRateNumerator,
        frame_rate_denominator: result.frameRateDenominator,
        frame_rate_reliability: result.frameRateReliability,
        has_audio: result.hasAudio,
        inspected_at: new Date(),
        inspector_version: 'ffprobe-v1',
        status: 'ready',
        revision: sql`revision + 1`,
        updated_at: new Date(),
      })
      .where('id', '=', videoId)
      .where('source_asset_id', '=', sourceAssetId)
      .where('status', '=', 'processing')
      .execute();
  } catch (error) {
    await failInspection(database, videoId, sourceAssetId);
    throw error;
  }
}

async function failInspection(
  database: Kysely<CatalogDatabase>,
  videoId: string,
  sourceAssetId: string,
): Promise<void> {
  await database
    .updateTable('videos')
    .set({
      status: 'failed',
      processing_failure_code: 'video_inspection_failed',
      processing_failure_retryable: true,
      processing_failure_at: new Date(),
      updated_at: new Date(),
    })
    .where('id', '=', videoId)
    .where('source_asset_id', '=', sourceAssetId)
    .where('status', '=', 'processing')
    .execute();
}
