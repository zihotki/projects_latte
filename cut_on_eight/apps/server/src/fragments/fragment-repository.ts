import type { Kysely, Transaction } from 'kysely';
import type { CatalogDatabase } from '../catalog/database-types.js';
import { safeMicroseconds } from '../catalog/database-types.js';
import type { FragmentRecord, TagRecord } from '../domain/models.js';

type Database = Kysely<CatalogDatabase> | Transaction<CatalogDatabase>;

export class FragmentRepository {
  constructor(private readonly database: Database) {}

  async list(videoId?: string): Promise<FragmentRecord[]> {
    let query = this.database
      .selectFrom('fragments')
      .innerJoin('videos', 'videos.id', 'fragments.video_id')
      .select([
        'fragments.id',
        'fragments.video_id',
        'fragments.start_us',
        'fragments.end_us',
        'fragments.title',
        'fragments.description',
        'fragments.export_selected',
        'fragments.revision',
      ])
      .where('fragments.deleted_at', 'is', null)
      .where('videos.status', '!=', 'deleting');
    if (videoId !== undefined) {
      query = query.where('fragments.video_id', '=', videoId);
    }
    const rows = await query
      .orderBy('fragments.start_us')
      .orderBy('fragments.id')
      .execute();
    return rows.map((row) => ({
      id: row.id,
      videoId: row.video_id,
      startUs: safeMicroseconds(row.start_us),
      endUs: safeMicroseconds(row.end_us),
      title: row.title,
      description: row.description,
      exportSelected: row.export_selected,
      revision: row.revision,
    }));
  }

  async tags(fragmentId: string): Promise<TagRecord[]> {
    return this.database
      .selectFrom('fragment_tags')
      .innerJoin('tags', 'tags.id', 'fragment_tags.tag_id')
      .select(['tags.id', 'tags.name'])
      .where('fragment_tags.fragment_id', '=', fragmentId)
      .orderBy('tags.name')
      .execute();
  }

  async preview(fragmentId: string) {
    const row = await this.database
      .selectFrom('fragment_previews')
      .selectAll()
      .where('fragment_id', '=', fragmentId)
      .executeTakeFirst();
    return row === undefined
      ? null
      : {
          status: row.status,
          assetId: row.asset_id,
          revision: row.fragment_revision,
          sampleUs: row.sample_us.map(safeMicroseconds),
          columns: row.columns,
          rows: row.rows,
          frameWidth: row.frame_width,
          frameHeight: row.frame_height,
        };
  }
}
