import { randomUUID } from 'node:crypto';
import { afterEach, describe, expect, test, vi } from 'vitest';
import { createApp, type CutOnEightApp } from '../src/app.js';
import type { ApiRuntime } from '../src/runtime.js';
import type { EmbeddingClient } from '../src/search/embedding-client.js';
import type {
  HybridSearchStore,
  RankedFragmentPoint,
} from '../src/search/hybrid-qdrant-store.js';
import { activeSearchAlias } from '../src/search/hybrid-qdrant-store.js';
import {
  createFragmentSearchService,
  type FragmentSearchServiceDependencies,
  type SearchResultMetadata,
} from '../src/search/search-service.js';

const fragmentId = randomUUID();
const videoId = randomUUID();
const tagId = randomUUID();
const collectionId = randomUUID();

describe('fragment search routes', () => {
  let app: CutOnEightApp | undefined;

  afterEach(async () => {
    await app?.close();
  });

  test('returns hybrid results with validated repeated filters', async () => {
    const store = storeReturning([point()]);
    app = createSearchApp({
      store,
      embeddings: availableEmbeddings(),
      countPending: async () => 2,
      loadMetadata: async () => previewMetadata(),
    });

    const response = await app.inject({
      method: 'GET',
      url: `/api/search/fragments?q=promenade&tagIds=${tagId}&collectionIds=${collectionId}&videoIds=${videoId}`,
    });

    expect(response.statusCode).toBe(200);
    expect(response.json()).toMatchObject({
      mode: 'hybrid',
      indexing: { pending: 2 },
      results: [
        {
          id: fragmentId,
          videoId,
          title: 'Promenade',
          tags: [{ id: tagId, name: 'foxtrot' }],
          previewState: 'ready',
          preview: { href: `/api/assets/${fragmentId}` },
        },
      ],
    });
    expect(store.query).toHaveBeenCalledWith(
      expect.objectContaining({
        collection: activeSearchAlias,
        denseVector: [0.1, 0.2],
        limit: 50,
        filter: {
          tagIds: [tagId],
          collectionIds: [collectionId],
          videoIds: [videoId],
        },
      }),
    );
  });

  test('uses lexical Qdrant search when embeddings are unavailable', async () => {
    const store = storeReturning([point()]);
    app = createSearchApp({
      store,
      embeddings: {
        available: () => false,
        embed: vi.fn(),
      },
      countPending: async () => 0,
    });

    const response = await app.inject({
      method: 'GET',
      url: '/api/search/fragments?q=promenade',
    });

    expect(response.statusCode).toBe(200);
    expect(response.json()).toMatchObject({ mode: 'lexical' });
    expect(store.query).toHaveBeenCalledWith(
      expect.objectContaining({
        denseVector: undefined,
        lexicalText: 'promenade',
      }),
    );
  });

  test('rejects invalid exact filters before querying Qdrant', async () => {
    const store = storeReturning([point()]);
    app = createSearchApp({
      store,
      embeddings: availableEmbeddings(),
      countPending: async () => 0,
    });

    const response = await app.inject({
      method: 'GET',
      url: '/api/search/fragments?q=promenade&tagIds=not-a-uuid',
    });

    expect(response.statusCode).toBe(400);
    expect(response.json()).toMatchObject({
      status: 400,
      code: 'invalid_request',
    });
    expect(response.headers['content-type']).toContain(
      'application/problem+json',
    );
    expect(store.query).not.toHaveBeenCalled();
  });

  test('maps Qdrant failures to search_unavailable', async () => {
    const store = storeReturning([]);
    store.query.mockRejectedValueOnce(new Error('Qdrant offline'));
    app = createSearchApp({
      store,
      embeddings: availableEmbeddings(),
      countPending: async () => 0,
    });

    const response = await app.inject({
      method: 'GET',
      url: '/api/search/fragments?q=promenade',
    });

    expect(response.statusCode).toBe(503);
    expect(response.json()).toMatchObject({
      status: 503,
      code: 'search_unavailable',
    });
  });
});

function createSearchApp(
  input: Pick<
    FragmentSearchServiceDependencies,
    'store' | 'embeddings' | 'countPending' | 'loadMetadata'
  >,
): CutOnEightApp {
  const search = createFragmentSearchService({
    database: {} as FragmentSearchServiceDependencies['database'],
    profile: {
      id: 'embeddinggemma-v1',
      model: 'google/embeddinggemma-300M',
      dimensions: 2,
      baseUrl: null,
    },
    loadMetadata: async () => new Map(),
    ...input,
  });
  return createApp({
    runtime: { search, close: async () => undefined } as ApiRuntime,
  });
}

function availableEmbeddings(): EmbeddingClient {
  return {
    available: () => true,
    embed: vi.fn().mockResolvedValue([[0.1, 0.2]]),
  };
}

function storeReturning(points: readonly RankedFragmentPoint[]) {
  return {
    ensureCollection: vi.fn(),
    upsert: vi.fn(),
    delete: vi.fn(),
    query: vi.fn().mockResolvedValue(points),
    count: vi.fn(),
    aliasTarget: vi.fn(),
    setAlias: vi.fn(),
  } satisfies HybridSearchStore & { query: ReturnType<typeof vi.fn> };
}

function point(): RankedFragmentPoint {
  return {
    fragmentId,
    score: 0.9,
    payload: {
      fragment_id: fragmentId,
      video_id: videoId,
      fragment_revision: 1,
      start_us: 10_000,
      end_us: 20_000,
      fragment_title: 'Promenade',
      fragment_description: 'Slow turn',
      fragment_tag_ids: [tagId],
      fragment_tags: ['foxtrot'],
      source_title: 'Practice lesson',
      source_description: null,
      source_tag_ids: [],
      source_tags: [],
      collection_ids: [],
    },
  };
}

function previewMetadata(): ReadonlyMap<string, SearchResultMetadata> {
  return new Map([
    [
      fragmentId,
      {
        previewState: 'ready',
        preview: {
          assetId: fragmentId,
          href: `/api/assets/${fragmentId}`,
          revision: 1,
          sampleUs: [10_000],
          columns: 1,
          rows: 1,
          frameWidth: 120,
          frameHeight: 80,
        },
      },
    ],
  ]);
}
