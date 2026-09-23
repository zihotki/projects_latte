import type {
  FragmentSearchResponse,
  FragmentSearchResultDto,
} from '@cut-on-eight/api-contracts';
import type { FragmentPreview } from './catalogue-model.js';
import type { ThumbnailManifestV1 } from '@cut-on-eight/legacy-contracts';

export interface FragmentSearchFilters {
  readonly tagIds: readonly string[];
  readonly videoIds: readonly string[];
}

export const emptyFragmentSearchFilters: FragmentSearchFilters = {
  tagIds: [],
  videoIds: [],
};

export interface FragmentSearchApi {
  loadVideoThumbnailManifest?(
    videoId: string,
  ): Promise<ThumbnailManifestV1 | null>;
  searchFragments(
    input: {
      q: string;
      tagIds: readonly string[];
      collectionIds: readonly string[];
      videoIds: readonly string[];
      limit: number;
    },
    signal?: AbortSignal,
  ): Promise<FragmentSearchResponse>;
}

export function searchResultPreviews(
  result: FragmentSearchResultDto,
): FragmentPreview[] {
  const preview = result.preview;
  if (preview === null) return [];
  return preview.sampleUs.map((sampleUs, index) => ({
    href: preview.href,
    sampleSeconds: sampleUs / 1_000_000,
    pageFileName: `preview-r${preview.revision}.webp`,
    pageWidth: preview.frameWidth * preview.columns,
    pageHeight: preview.frameHeight * preview.rows,
    x: preview.frameWidth * index,
    y: 0,
    width: preview.frameWidth,
    height: preview.frameHeight,
    identity: `${preview.assetId}:${preview.revision}`,
  }));
}

export function searchResultLabel(result: FragmentSearchResultDto): string {
  return result.title?.trim() || 'Untitled fragment';
}
