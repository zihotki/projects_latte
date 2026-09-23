import type { FragmentSearchResponse } from '@cut-on-eight/api-contracts';
import type { ThumbnailManifestV1 } from '@cut-on-eight/legacy-contracts';
import { describe, expect, it, vi } from 'vitest';
import { createSearchModel, type SearchModel } from './search-model.svelte.js';
import type { FragmentSearchApi } from '../domain/search-model.js';

const response = (mode: FragmentSearchResponse['mode'] = 'hybrid') => ({
  mode,
  indexing: { pending: 0 },
  results: [],
});

function api(): FragmentSearchApi {
  return { searchFragments: vi.fn().mockResolvedValue(response()) };
}

describe('SearchModel', () => {
  it('debounces and sends the current query', async () => {
    vi.useFakeTimers();
    try {
      const client = api();
      const model = createSearchModel(client);
      model.setQuery('promenade');

      await vi.advanceTimersByTimeAsync(200);

      expect(client.searchFragments).toHaveBeenCalledWith(
        {
          q: 'promenade',
          tagIds: [],
          collectionIds: [],
          videoIds: [],
          limit: 20,
        },
        expect.any(AbortSignal),
      );
      expect(model.state).toBe('ready');
    } finally {
      vi.useRealTimers();
    }
  });

  it('does not request blank input', async () => {
    vi.useFakeTimers();
    try {
      const client = api();
      const model = createSearchModel(client);
      model.setQuery('   ');
      await vi.advanceTimersByTimeAsync(200);
      expect(client.searchFragments).not.toHaveBeenCalled();
      expect(model.state).toBe('idle');
    } finally {
      vi.useRealTimers();
    }
  });

  it('aborts an in-flight request when the query changes', async () => {
    vi.useFakeTimers();
    try {
      let signal: AbortSignal | undefined;
      const client: FragmentSearchApi = {
        searchFragments: vi.fn((_, nextSignal) => {
          signal = nextSignal;
          return new Promise<FragmentSearchResponse>(() => undefined);
        }),
      };
      const model = createSearchModel(client);
      model.setQuery('first');
      await vi.advanceTimersByTimeAsync(200);
      model.setQuery('second');

      expect(signal?.aborted).toBe(true);
      model.dispose();
    } finally {
      vi.useRealTimers();
    }
  });

  it('keeps lexical results as a ready search response', async () => {
    vi.useFakeTimers();
    try {
      const client = api();
      vi.mocked(client.searchFragments).mockResolvedValue(response('lexical'));
      const model: SearchModel = createSearchModel(client);
      model.setQuery('promenade');
      await vi.advanceTimersByTimeAsync(200);

      expect(model.state).toBe('ready');
      expect(model.response?.mode).toBe('lexical');
      expect(model.error).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it('loads a video bundle for a search result', async () => {
    vi.useFakeTimers();
    try {
      const videoId = '00000000-0000-4000-8000-000000000001';
      const manifest = {
        schemaVersion: 1,
        generatorVersion: 'overview-webp-v2',
        sourceFingerprint: 'bundle-a',
        durationSeconds: 10,
        thumbnail: [160, 90],
        pages: [['sprite-aaaaaaaaaaaaaaaaaaaaaaaa-0.webp', 160, 90]],
        samples: [[5, 0, 0, 0, 160, 90]],
      } as ThumbnailManifestV1;
      const client: FragmentSearchApi = {
        searchFragments: vi.fn().mockResolvedValue({
          ...response(),
          results: [
            {
              id: '00000000-0000-4000-8000-000000000002',
              videoId,
              startUs: 4_000_000,
              endUs: 6_000_000,
            },
          ],
        }),
        loadVideoThumbnailManifest: vi.fn().mockResolvedValue(manifest),
      };
      const model = createSearchModel(client);
      model.setQuery('turn');
      await vi.advanceTimersByTimeAsync(200);
      expect(model.manifests[videoId]).toEqual(manifest);
    } finally {
      vi.useRealTimers();
    }
  });
});
