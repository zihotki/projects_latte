import {
  editorVideoSchema,
  workspaceSchema,
  type WorkspaceDto,
} from '@cut-on-eight/api-contracts';
import type { Kysely } from 'kysely';
import type { CatalogDatabase } from '../catalog/database-types.js';
import { safeMicroseconds } from '../catalog/database-types.js';
import { CatalogNotFound } from '../domain/models.js';
import { FragmentRepository } from '../fragments/fragment-repository.js';
import { toFragmentDto, toVideoSummaryDto } from '../api/public-mappers.js';
import { VideoRepository } from '../videos/video-repository.js';
import { WorkspaceRepository } from './workspace-repository.js';

export class WorkspaceService {
  constructor(private readonly database: Kysely<CatalogDatabase>) {}

  async snapshot(): Promise<WorkspaceDto> {
    const videos = new VideoRepository(this.database);
    const fragments = new FragmentRepository(this.database);
    const workspace = new WorkspaceRepository(this.database);
    const libraryRecords = await videos.list();
    const library = await Promise.all(
      libraryRecords.map(async (video) =>
        toVideoSummaryDto(video, await videos.tags(video.id)),
      ),
    );
    const openIds = await workspace.openVideoIds();
    const openVideos = [];
    for (const videoId of openIds) {
      const video = libraryRecords.find(({ id }) => id === videoId);
      if (video === undefined) continue;
      const fragmentRecords = await fragments.list(videoId);
      const fragmentDtos = await Promise.all(
        fragmentRecords.map(async (fragment) =>
          toFragmentDto({
            fragment,
            tags: await fragments.tags(fragment.id),
            preview: await fragments.preview(fragment.id),
          }),
        ),
      );
      const workspaceRow = await this.database
        .selectFrom('workspace_videos')
        .select('playback_position_us')
        .where('video_id', '=', videoId)
        .executeTakeFirstOrThrow();
      const editor = await this.database
        .selectFrom('editor_state')
        .selectAll()
        .where('video_id', '=', videoId)
        .executeTakeFirst();
      openVideos.push(
        editorVideoSchema.parse({
          video: library.find(({ id }) => id === videoId),
          source:
            video.sourceAssetId === null
              ? null
              : {
                  assetId: video.sourceAssetId,
                  href: `/api/assets/${encodeURIComponent(video.sourceAssetId)}`,
                },
          fragments: fragmentDtos,
          playbackPositionUs: safeMicroseconds(
            workspaceRow.playback_position_us,
          ),
          editor: {
            selectedFragmentId: editor?.selected_fragment_id ?? null,
            pauseAfterCreation: editor?.pause_after_creation ?? false,
            timelineZoom: editor?.timeline_zoom ?? 1,
            timelineOffsetUs:
              editor === undefined
                ? 0
                : safeMicroseconds(editor.timeline_offset_us),
          },
        }),
      );
    }
    const active = await workspace.activeVideoId();
    return workspaceSchema.parse({
      activeVideoId: openVideos.some(({ video }) => video.id === active)
        ? active
        : null,
      openVideos,
      library,
    });
  }

  async open(videoId: string): Promise<WorkspaceDto> {
    await this.database.transaction().execute(async (transaction) => {
      const video = await new VideoRepository(transaction).find(videoId);
      if (video === null || video.status === 'deleting') {
        throw new CatalogNotFound();
      }
      await new WorkspaceRepository(transaction).open(videoId);
    });
    return this.snapshot();
  }

  async activate(videoId: string): Promise<WorkspaceDto> {
    try {
      await new WorkspaceRepository(this.database).activate(videoId);
    } catch {
      throw new CatalogNotFound();
    }
    return this.snapshot();
  }

  async close(videoId: string): Promise<WorkspaceDto> {
    await new WorkspaceRepository(this.database).close(videoId);
    return this.snapshot();
  }
}
