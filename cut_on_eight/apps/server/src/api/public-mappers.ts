import {
  fragmentSchema,
  healthReadySchema,
  tagSchema,
  videoSummarySchema,
  type FragmentDto,
  type HealthReadyDto,
  type TagDto,
  type VideoSummaryDto,
} from '@cut-on-eight/api-contracts';
import type {
  FragmentRecord,
  TagRecord,
  VideoRecord,
} from '../domain/models.js';

export function toReadyDto(input: {
  postgres: 'ready' | 'unavailable';
  qdrant: 'ready' | 'degraded' | 'not-configured';
  worker: 'ready' | 'unavailable';
}): HealthReadyDto {
  return healthReadySchema.parse({
    status: input.postgres === 'ready' ? 'ready' : 'unavailable',
    dependencies: input,
  });
}

export function toTagDto(tag: TagRecord): TagDto {
  return tagSchema.parse({ id: tag.id, name: tag.name });
}

export function toVideoSummaryDto(
  video: VideoRecord,
  tags: readonly TagRecord[],
): VideoSummaryDto {
  return videoSummarySchema.parse({
    id: video.id,
    title: video.title,
    description: video.description,
    originalFileName: video.originalFileName,
    durationUs: video.durationUs,
    width: video.width,
    height: video.height,
    frameRateNumerator: video.frameRateNumerator,
    frameRateDenominator: video.frameRateDenominator,
    frameRateReliability: video.frameRateReliability,
    hasAudio: video.hasAudio,
    status: video.status,
    revision: video.revision,
    tags: tags.map(toTagDto),
  });
}

export function toFragmentDto(input: {
  fragment: FragmentRecord;
  tags: readonly TagRecord[];
  preview: null | {
    status: 'pending' | 'ready' | 'failed';
    assetId: string | null;
    revision: number;
    sampleUs: number[];
    columns: number;
    rows: number;
    frameWidth: number;
    frameHeight: number;
  };
}): FragmentDto {
  const { fragment, tags, preview } = input;
  return fragmentSchema.parse({
    id: fragment.id,
    videoId: fragment.videoId,
    startUs: fragment.startUs,
    endUs: fragment.endUs,
    title: fragment.title,
    description: fragment.description,
    exportSelected: fragment.exportSelected,
    revision: fragment.revision,
    tags: tags.map(toTagDto),
    previewState: preview?.status ?? 'pending',
    preview:
      preview?.status === 'ready' && preview.assetId !== null
        ? {
            assetId: preview.assetId,
            href: `/api/assets/${encodeURIComponent(preview.assetId)}`,
            revision: preview.revision,
            sampleUs: preview.sampleUs,
            columns: preview.columns,
            rows: preview.rows,
            frameWidth: preview.frameWidth,
            frameHeight: preview.frameHeight,
          }
        : null,
  });
}
