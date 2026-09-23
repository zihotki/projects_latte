import type {
  FragmentSearchResponse,
  FragmentSearchResultDto,
} from '@cut-on-eight/api-contracts';
import type { ThumbnailManifestV1 } from '@cut-on-eight/legacy-contracts';
import {
  emptyFragmentSearchFilters,
  type FragmentSearchApi,
  type FragmentSearchFilters,
} from '../domain/search-model.js';

export type SearchState = 'idle' | 'loading' | 'ready' | 'error';

export interface SearchModel {
  readonly query: string;
  readonly filters: FragmentSearchFilters;
  readonly response: FragmentSearchResponse | null;
  readonly state: SearchState;
  readonly error: string | null;
  readonly manifests: Readonly<Record<string, ThumbnailManifestV1>>;
  setQuery(value: string): void;
  setFilters(value: FragmentSearchFilters): void;
  dispose(): void;
}

class SearchModelImpl implements SearchModel {
  query = $state('');
  filters = $state.raw<FragmentSearchFilters>(emptyFragmentSearchFilters);
  response = $state.raw<FragmentSearchResponse | null>(null);
  state = $state<SearchState>('idle');
  error = $state<string | null>(null);
  manifests = $state.raw<Record<string, ThumbnailManifestV1>>({});

  private debounceTimer: ReturnType<typeof setTimeout> | null = null;
  private controller: AbortController | null = null;
  private requestRevision = 0;
  private disposed = false;

  constructor(private readonly api: FragmentSearchApi) {}

  setQuery(value: string): void {
    this.query = value;
    this.scheduleSearch();
  }

  setFilters(value: FragmentSearchFilters): void {
    this.filters = normalizeFilters(value);
    this.scheduleSearch();
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.requestRevision += 1;
    this.clearDebounce();
    this.controller?.abort();
    this.controller = null;
  }

  private scheduleSearch(): void {
    if (this.disposed) return;
    this.requestRevision += 1;
    this.clearDebounce();
    this.controller?.abort();
    this.controller = null;
    this.error = null;

    if (this.query.trim() === '') {
      this.response = null;
      this.state = 'idle';
      return;
    }

    const revision = this.requestRevision;
    this.state = 'loading';
    this.debounceTimer = setTimeout(() => {
      this.debounceTimer = null;
      void this.search(revision);
    }, 200);
  }

  private async search(revision: number): Promise<void> {
    if (this.disposed || revision !== this.requestRevision) return;
    const controller = new AbortController();
    this.controller = controller;
    try {
      const response = await this.api.searchFragments(
        {
          q: this.query.trim(),
          tagIds: this.filters.tagIds,
          collectionIds: [],
          videoIds: this.filters.videoIds,
          limit: 20,
        },
        controller.signal,
      );
      if (!this.isCurrent(revision, controller)) return;
      this.response = response;
      this.state = 'ready';
      void this.loadManifests(response, revision);
    } catch (error) {
      if (!this.isCurrent(revision, controller) || isAbort(error)) return;
      this.error = describeError(error);
      this.state = 'error';
    } finally {
      if (this.controller === controller) this.controller = null;
    }
  }

  private async loadManifests(
    response: FragmentSearchResponse,
    revision: number,
  ): Promise<void> {
    if (this.api.loadVideoThumbnailManifest === undefined) return;
    const ids = [...new Set(response.results.map(({ videoId }) => videoId))];
    const loaded = await Promise.all(
      ids.map(
        async (id) =>
          [
            id,
            await this.api.loadVideoThumbnailManifest!(id).catch(() => null),
          ] as const,
      ),
    );
    if (this.disposed || revision !== this.requestRevision) return;
    this.manifests = {
      ...this.manifests,
      ...Object.fromEntries(
        loaded.flatMap(([id, manifest]) =>
          manifest === null ? [] : [[id, manifest] as const],
        ),
      ),
    };
  }

  private isCurrent(revision: number, controller: AbortController): boolean {
    return (
      !this.disposed &&
      revision === this.requestRevision &&
      this.controller === controller
    );
  }

  private clearDebounce(): void {
    if (this.debounceTimer !== null) clearTimeout(this.debounceTimer);
    this.debounceTimer = null;
  }
}

export function createSearchModel(api: FragmentSearchApi): SearchModel {
  return new SearchModelImpl(api);
}

function normalizeFilters(value: FragmentSearchFilters): FragmentSearchFilters {
  return {
    tagIds: uniqueIds(value.tagIds),
    videoIds: uniqueIds(value.videoIds),
  };
}

function uniqueIds(ids: readonly string[]): string[] {
  return [...new Set(ids.filter((id) => id.trim() !== ''))];
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}

function describeError(error: unknown): string {
  return error instanceof Error ? error.message : 'Search failed.';
}

export type { FragmentSearchResponse, FragmentSearchResultDto };
