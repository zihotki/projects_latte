import type { Kysely, Transaction } from 'kysely';
import { blobKey } from '../blobs/blob-key.js';
import type { CatalogDatabase, VideoRow } from '../catalog/database-types.js';
import { safeMicroseconds } from '../catalog/database-types.js';
import type { AssetRecord, TagRecord, VideoRecord } from '../domain/models.js';

type Database = Kysely<CatalogDatabase> | Transaction<CatalogDatabase>;

export class VideoRepository {
  constructor(private readonly database: Database) {}

  async list(): Promise<VideoRecord[]> {
    const rows = await this.database
      .selectFrom('videos')
      .selectAll()
      .where('status', '!=', 'deleting')
      .where((builder) =>
        builder.or([
          builder('status', '!=', 'receiving'),
          builder('source_asset_id', 'is not', null),
        ]),
      )
      .orderBy('created_at', 'desc')
      .execute();
    return rows.map(toVideoRecord);
  }

  async find(id: string, lock = false): Promise<VideoRecord | null> {
    let query = this.database
      .selectFrom('videos')
      .selectAll()
      .where('id', '=', id);
    if (lock) query = query.forUpdate();
    const row = await query.executeTakeFirst();
    return row === undefined ? null : toVideoRecord(row);
  }

  async tags(videoId: string): Promise<TagRecord[]> {
    return this.database
      .selectFrom('video_tags')
      .innerJoin('tags', 'tags.id', 'video_tags.tag_id')
      .select(['tags.id', 'tags.name'])
      .where('video_tags.video_id', '=', videoId)
      .orderBy('tags.name')
      .execute();
  }

  async asset(assetId: string): Promise<AssetRecord | null> {
    const row = await this.database
      .selectFrom('assets')
      .selectAll()
      .where('id', '=', assetId)
      .where('state', '=', 'ready')
      .executeTakeFirst();
    return row === undefined
      ? null
      : {
          id: row.id,
          key: blobKey(row.storage_key),
          kind: row.kind,
          mimeType: row.mime_type,
          size: safeMicroseconds(row.size_bytes),
          revision: row.revision,
        };
  }
}

export function toVideoRecord(row: VideoRow): VideoRecord {
  return {
    id: row.id,
    title: row.title,
    description: row.description,
    originalFileName: row.original_file_name,
    sourceAssetId: row.source_asset_id,
    durationUs:
      row.duration_us === null ? null : safeMicroseconds(row.duration_us),
    width: row.width,
    height: row.height,
    frameRateNumerator: row.frame_rate_numerator,
    frameRateDenominator: row.frame_rate_denominator,
    frameRateReliability: row.frame_rate_reliability,
    hasAudio: row.has_audio,
    status: row.status,
    revision: row.revision,
  };
}
