import { fromKysely, type PgBoss } from 'pg-boss';
import type { Kysely } from 'kysely';
import { v7 as uuidv7 } from 'uuid';
import type {
  VideoSummaryDto,
  WorkspaceDto,
} from '@cut-on-eight/api-contracts';
import { sourceBlobKey } from '../blobs/blob-key.js';
import type { BlobStore, StagedBlob } from '../blobs/blob-store.js';
import type { CatalogDatabase } from '../catalog/database-types.js';
import { CatalogNotFound, StaleRevision } from '../domain/models.js';
import { envelope } from '../jobs/job-envelope.js';
import { jobNames } from '../jobs/job-contracts.js';
import { toVideoSummaryDto } from '../api/public-mappers.js';
import { WorkspaceRepository } from '../workspace/workspace-repository.js';
import { WorkspaceService } from '../workspace/workspace-service.js';
import { VideoRepository } from './video-repository.js';

export interface UploadedSource {
  readonly fileName: string;
  readonly mimeType: string;
  readonly bytes: AsyncIterable<Uint8Array>;
}

export class VideoService {
  constructor(
    private readonly database: Kysely<CatalogDatabase>,
    private readonly boss: PgBoss,
    private readonly blobs: BlobStore,
    private readonly workspace: WorkspaceService,
  ) {}

  async list(): Promise<VideoSummaryDto[]> {
    const repository = new VideoRepository(this.database);
    const videos = await repository.list();
    return Promise.all(
      videos.map(async (video) =>
        toVideoSummaryDto(video, await repository.tags(video.id)),
      ),
    );
  }

  async get(id: string): Promise<VideoSummaryDto> {
    const repository = new VideoRepository(this.database);
    const video = await repository.find(id);
    if (video === null || video.status === 'deleting')
      throw new CatalogNotFound();
    return toVideoSummaryDto(video, await repository.tags(id));
  }

  async import(source: UploadedSource): Promise<{
    video: VideoSummaryDto;
    workspace: WorkspaceDto;
  }> {
    const videoId = uuidv7();
    const assetId = uuidv7();
    const title = source.fileName.replace(/\.mp4$/i, '') || source.fileName;
    await this.database
      .insertInto('videos')
      .values({
        id: videoId,
        source_asset_id: null,
        title,
        description: null,
        original_file_name: source.fileName,
        duration_us: null,
        width: null,
        height: null,
        frame_rate_numerator: null,
        frame_rate_denominator: null,
        has_audio: null,
        status: 'receiving',
      })
      .execute();

    let staged: StagedBlob | undefined;
    let published = false;
    try {
      staged = await this.blobs.writeStaged(source.bytes);
      const destination = sourceBlobKey(videoId, source.fileName);
      await this.blobs.publish(staged, destination);
      published = true;
      const publishedBlob = staged;
      await this.database.transaction().execute(async (transaction) => {
        await transaction
          .insertInto('assets')
          .values({
            id: assetId,
            storage_key: destination,
            owner_kind: 'video',
            owner_id: videoId,
            kind: 'source',
            mime_type: source.mimeType || 'video/mp4',
            size_bytes: publishedBlob.size,
            sha256: publishedBlob.sha256,
            state: 'ready',
          })
          .execute();
        await transaction
          .updateTable('videos')
          .set({
            source_asset_id: assetId,
            status: 'queued',
            updated_at: new Date(),
          })
          .where('id', '=', videoId)
          .execute();
        await new WorkspaceRepository(transaction).open(videoId);
        await this.boss.send(
          jobNames.inspectVideo,
          envelope({ videoId, sourceAssetId: assetId }),
          {
            db: fromKysely(transaction),
            retryLimit: 3,
            singletonKey: `${videoId}:${assetId}`,
          },
        );
      });
    } catch (error) {
      if (!published) {
        if (staged !== undefined) await this.blobs.delete(staged.key);
        await this.database
          .updateTable('videos')
          .set({
            status: 'failed',
            processing_failure_code: 'upload_failed',
            processing_failure_retryable: true,
            processing_failure_at: new Date(),
            updated_at: new Date(),
          })
          .where('id', '=', videoId)
          .where('status', '=', 'receiving')
          .execute();
      }
      throw error;
    }
    return {
      video: await this.get(videoId),
      workspace: await this.workspace.snapshot(),
    };
  }

  async delete(
    videoId: string,
    expectedRevision: number,
  ): Promise<WorkspaceDto> {
    await this.database.transaction().execute(async (transaction) => {
      const video = await new VideoRepository(transaction).find(videoId, true);
      if (video === null) throw new CatalogNotFound();
      if (video.revision !== expectedRevision) throw new StaleRevision();
      await transaction
        .updateTable('videos')
        .set({
          status: 'deleting',
          revision: video.revision + 1,
          updated_at: new Date(),
        })
        .where('id', '=', videoId)
        .execute();
      await new WorkspaceRepository(transaction).close(videoId);
      await this.boss.send(
        jobNames.deleteVideo,
        envelope({ videoId, expectedRevision: video.revision + 1 }),
        { db: fromKysely(transaction), singletonKey: videoId },
      );
    });
    return this.workspace.snapshot();
  }
}
