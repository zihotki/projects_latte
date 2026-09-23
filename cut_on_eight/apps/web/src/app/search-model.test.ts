import type { FragmentSearchResponse } from '@cut-on-eight/api-contracts';
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
});
