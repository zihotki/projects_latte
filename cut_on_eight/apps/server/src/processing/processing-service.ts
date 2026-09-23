import type { ProcessingSnapshotDto } from '@cut-on-eight/api-contracts';
import type { Kysely } from 'kysely';
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
      task: 'inspect',
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
          : 'queued',
    updatedAt: (row.thumbnailUpdatedAt ?? row.videoUpdatedAt).toISOString(),
    failureCode:
      row.thumbnailStatus === 'failed' ? row.thumbnailFailureCode : null,
  };
}

export function toProcessingSnapshot(
  rows: readonly ProcessingRow[],
  now: Date = new Date(),
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
    activeCount,
    failedCount,
    observedAt: now.toISOString(),
    items: items.slice(0, 100),
  };
}

export class ProcessingService {
  constructor(private readonly database: Kysely<CatalogDatabase>) {}

  async snapshot(): Promise<ProcessingSnapshotDto> {
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
      .execute();
    return toProcessingSnapshot(rows);
  }
}
