import {
  spriteCapacity,
  spriteColumns,
  spriteRows,
  thumbnailHeight,
  thumbnailWidth,
  type SamplingPlan,
} from './thumbnail-manifest.js';

export const videoThumbnailProfileVersion = 'overview-webp-v2';

export interface VideoThumbnailManifest {
  readonly schemaVersion: 1;
  readonly profileVersion: typeof videoThumbnailProfileVersion;
  readonly durationSeconds: number;
  readonly thumbnail: readonly [number, number];
  readonly pages: readonly (readonly [string, number, number])[];
  readonly samples: readonly (readonly [
    number,
    number,
    number,
    number,
    number,
    number,
  ])[];
}

export function createVideoThumbnailManifest(
  durationSeconds: number,
  plan: SamplingPlan,
  pageNames: readonly string[],
): VideoThumbnailManifest {
  if (pageNames.length !== plan.pageCount) {
    throw new Error('Thumbnail page count does not match the sampling plan');
  }
  const pageWidth = thumbnailWidth * spriteColumns;
  const pageHeight = thumbnailHeight * spriteRows;
  return {
    schemaVersion: 1,
    profileVersion: videoThumbnailProfileVersion,
    durationSeconds,
    thumbnail: [thumbnailWidth, thumbnailHeight],
    pages: pageNames.map((name) => [name, pageWidth, pageHeight]),
    samples: plan.sampleTimes.map((timeSeconds, index) => {
      const pageCell = index % spriteCapacity;
      return [
        timeSeconds,
        Math.floor(index / spriteCapacity),
        (pageCell % spriteColumns) * thumbnailWidth,
        Math.floor(pageCell / spriteColumns) * thumbnailHeight,
        thumbnailWidth,
        thumbnailHeight,
      ];
    }),
  };
}

export function isVideoThumbnailManifest(
  value: unknown,
): value is VideoThumbnailManifest {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return (
    candidate.schemaVersion === 1 &&
    candidate.profileVersion === videoThumbnailProfileVersion &&
    typeof candidate.durationSeconds === 'number' &&
    Array.isArray(candidate.thumbnail) &&
    Array.isArray(candidate.pages) &&
    Array.isArray(candidate.samples)
  );
}
