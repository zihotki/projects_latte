import type { Kysely } from 'kysely';
import { blobKey } from '../../blobs/blob-key.js';
import type { LocalMediaFiles } from '../../blobs/blob-store.js';
import type { CatalogDatabase } from '../../catalog/database-types.js';
import { FfprobeRunner, type ProbeRunner } from '../ffprobe-runner.js';

export interface InspectVideoJob {
  readonly videoId: string;
  readonly expectedRevision: number;
}

export function createInspectVideoProcessor(
  database: Kysely<CatalogDatabase>,
  files: LocalMediaFiles,
  probe: ProbeRunner = new FfprobeRunner(),
) {
  return async ({
    videoId,
    expectedRevision,
  }: InspectVideoJob): Promise<void> => {
    const row = await database
      .selectFrom('videos')
      .innerJoin('assets', 'assets.id', 'videos.source_asset_id')
      .select(['videos.revision', 'videos.status', 'assets.storage_key'])
      .where('videos.id', '=', videoId)
      .executeTakeFirst();
    if (
      row === undefined ||
      row.revision !== expectedRevision ||
      !['queued', 'processing', 'failed'].includes(row.status)
    ) {
      return;
    }
    await database
      .updateTable('videos')
      .set({
        status: 'processing',
        processing_failure_code: null,
        processing_failure_retryable: null,
        processing_failure_at: null,
        updated_at: new Date(),
      })
      .where('id', '=', videoId)
      .execute();
    try {
      const result = await files.withLocalPath(
        blobKey(row.storage_key),
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
          revision: expectedRevision + 1,
          updated_at: new Date(),
        })
        .where('id', '=', videoId)
        .where('revision', '=', expectedRevision)
        .execute();
    } catch (error) {
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
        .execute();
      throw error;
    }
  };
}
