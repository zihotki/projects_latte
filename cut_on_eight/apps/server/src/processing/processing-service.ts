import type { ProcessingSnapshotDto } from '@cut-on-eight/api-contracts';
import { sql, type Kysely } from 'kysely';
import type { CatalogDatabase, VideoTable } from '../catalog/database-types.js';

export interface ProcessingRow {
  id: string;
  title: string;
  videoStatus: VideoTable['status'];
  videoUpdatedAt: Date;
  videoFailureCode: string | null;
  thumbnailStatus: 'pending' | 'generating' | 'ready' | 'failed' | null;
  thumbnailUpdatedAt: Date | null;
  thumbnailFailureCode: string | null;
}

type Item = ProcessingSnapshotDto['items'][number];

function toItem(row: ProcessingRow): Item | null {
  if (row.videoStatus === 'deleting') return null;
  const base = {
    videoId: row.id,
    videoTitle: row.title,
    updatedAt: row.videoUpdatedAt.toISOString(),
    failureCode: null,
  };
  if (row.videoStatus === 'receiving') {
    return { ...base, task: 'import', state: 'running' };
  }
  if (row.videoStatus === 'queued') {
    return { ...base, task: 'inspect', state: 'queued' };
  }
  if (row.videoStatus === 'processing') {
    return { ...base, task: 'inspect', state: 'running' };
  }
  if (row.videoStatus === 'failed') {
    return {
      ...base,
      task: row.videoFailureCode === 'upload_failed' ? 'import' : 'inspect',
      state: 'failed',
      failureCode: row.videoFailureCode,
    };
  }
  if (row.thumbnailStatus === 'ready') return null;
  return {
    ...base,
    task: 'thumbnails',
    state:
      row.thumbnailStatus === 'failed'
        ? 'failed'
        : row.thumbnailStatus === 'generating'
          ? 'running'
          : row.thumbnailStatus === null
            ? 'waiting'
            : 'queued',
    updatedAt: (row.thumbnailUpdatedAt ?? row.videoUpdatedAt).toISOString(),
    failureCode:
      row.thumbnailStatus === 'failed' ? row.thumbnailFailureCode : null,
  };
}

export function toProcessingSnapshot(
  rows: readonly ProcessingRow[],
  now: Date = new Date(),
  counts?: { activeCount: number; failedCount: number },
): ProcessingSnapshotDto {
  const items = rows.flatMap((row) => {
    const item = toItem(row);
    return item === null ? [] : [item];
  });
  const activeCount = items.filter((item) => item.state !== 'failed').length;
  const failedCount = items.length - activeCount;
  items.sort((left, right) => {
    if (left.state === 'failed' && right.state !== 'failed') return 1;
    if (left.state !== 'failed' && right.state === 'failed') return -1;
    return left.state === 'failed'
      ? right.updatedAt.localeCompare(left.updatedAt)
      : left.updatedAt.localeCompare(right.updatedAt);
  });
  return {
    activeCount: counts?.activeCount ?? activeCount,
    failedCount: counts?.failedCount ?? failedCount,
    observedAt: now.toISOString(),
    items: items.slice(0, 100),
  };
}

export class ProcessingService {
  constructor(private readonly database: Kysely<CatalogDatabase>) {}

  async snapshot(): Promise<ProcessingSnapshotDto> {
    const counts = await sql<{ active_count: number; failed_count: number }>`
      select
        count(*) filter (where video.status in ('receiving', 'queued', 'processing')
          or (video.status = 'ready' and thumbnail.status is distinct from 'ready'
            and thumbnail.status is distinct from 'failed'))::int as active_count,
        count(*) filter (where video.status = 'failed'
          or (video.status = 'ready' and thumbnail.status = 'failed'))::int as failed_count
      from videos as video
      left join video_thumbnail_state as thumbnail on thumbnail.video_id = video.id
      where video.status != 'deleting'
    `.execute(this.database);
    const rows = await this.database
      .selectFrom('videos as video')
      .leftJoin(
        'video_thumbnail_state as thumbnail',
        'thumbnail.video_id',
        'video.id',
      )
      .select([
        'video.id as id',
        'video.title as title',
        'video.status as videoStatus',
        'video.updated_at as videoUpdatedAt',
        'video.processing_failure_code as videoFailureCode',
        'thumbnail.status as thumbnailStatus',
        'thumbnail.updated_at as thumbnailUpdatedAt',
        'thumbnail.failure_code as thumbnailFailureCode',
      ])
      .where('video.status', '!=', 'deleting')
      .where(
        sql<boolean>`video.status != 'ready' or thumbnail.status is distinct from 'ready'`,
      )
      .orderBy(
        sql<number>`case when video.status = 'failed' or thumbnail.status = 'failed' then 1 else 0 end`,
        'asc',
      )
      .orderBy(
        sql<Date>`case when video.status = 'failed' or thumbnail.status = 'failed' then null when video.status = 'ready' then coalesce(thumbnail.updated_at, video.updated_at) else video.updated_at end`,
        'asc',
      )
      .orderBy(
        sql<Date>`case when video.status = 'failed' then video.updated_at when video.status = 'ready' and thumbnail.status = 'failed' then coalesce(thumbnail.updated_at, video.updated_at) else null end`,
        'desc',
      )
      .limit(100)
      .execute();
    return toProcessingSnapshot(rows, new Date(), {
      activeCount: counts.rows[0]?.active_count ?? 0,
      failedCount: counts.rows[0]?.failed_count ?? 0,
    });
  }
}
