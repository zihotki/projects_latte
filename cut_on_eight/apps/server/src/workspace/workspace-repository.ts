import { sql, type Kysely, type Transaction } from 'kysely';
import type { CatalogDatabase } from '../catalog/database-types.js';

type Database = Kysely<CatalogDatabase> | Transaction<CatalogDatabase>;

export class WorkspaceRepository {
  constructor(private readonly database: Database) {}

  async openVideoIds(): Promise<string[]> {
    const rows = await this.database
      .selectFrom('workspace_videos')
      .select('video_id')
      .orderBy('position')
      .execute();
    return rows.map(({ video_id }) => video_id);
  }

  async activeVideoId(): Promise<string | null> {
    return (
      (
        await this.database
          .selectFrom('workspace_state')
          .select('active_video_id')
          .where('id', '=', true)
          .executeTakeFirst()
      )?.active_video_id ?? null
    );
  }

  async open(videoId: string): Promise<void> {
    const current = await this.database
      .selectFrom('workspace_videos')
      .select('video_id')
      .where('video_id', '=', videoId)
      .executeTakeFirst();
    if (current === undefined) {
      const position = await this.nextPosition();
      await this.database
        .insertInto('workspace_videos')
        .values({ video_id: videoId, position, playback_position_us: 0 })
        .execute();
      await this.database
        .insertInto('editor_state')
        .values({
          video_id: videoId,
          selected_fragment_id: null,
          pause_after_creation: false,
          timeline_zoom: 1,
          timeline_offset_us: 0,
        })
        .onConflict((conflict) => conflict.column('video_id').doNothing())
        .execute();
    }
    await this.activate(videoId);
  }

  async activate(videoId: string): Promise<void> {
    const open = await this.database
      .selectFrom('workspace_videos')
      .select('video_id')
      .where('video_id', '=', videoId)
      .executeTakeFirst();
    if (open === undefined) throw new Error('Video is not open');
    await this.database
      .updateTable('workspace_state')
      .set({ active_video_id: videoId, updated_at: new Date() })
      .where('id', '=', true)
      .execute();
  }

  async close(videoId: string): Promise<void> {
    await this.database
      .deleteFrom('workspace_videos')
      .where('video_id', '=', videoId)
      .execute();
    const remaining = await this.database
      .selectFrom('workspace_videos')
      .select('video_id')
      .orderBy('position', 'desc')
      .executeTakeFirst();
    await this.database
      .updateTable('workspace_state')
      .set({
        active_video_id: remaining?.video_id ?? null,
        updated_at: new Date(),
      })
      .where('id', '=', true)
      .execute();
  }

  async nextPosition(): Promise<number> {
    const result = await sql<{ position: number | null }>`
      select max(position) as position from workspace_videos
    `.execute(this.database);
    return Number(result.rows[0]?.position ?? -1) + 1;
  }
}
