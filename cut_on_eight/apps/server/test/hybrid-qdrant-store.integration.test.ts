import { randomUUID } from 'node:crypto';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import {
  createHybridSearchStore,
  type HybridSearchStore,
} from '../src/search/hybrid-qdrant-store.js';

const qdrantHttpUrl = process.env.QDRANT_HTTPURI;
const integration = qdrantHttpUrl === undefined ? describe.skip : describe;

if (qdrantHttpUrl === undefined) {
  console.warn('Skipping hybrid Qdrant test: QDRANT_HTTPURI is required');
}

integration('hybrid Qdrant store', () => {
  const collection = `cut_on_eight_hybrid_test_${randomUUID().replaceAll('-', '')}`;
  const matchingId = randomUUID();
  const otherId = randomUUID();
  const matchingTagId = randomUUID();
  let store: HybridSearchStore;

  beforeAll(async () => {
    store = createHybridSearchStore({
      qdrantHttpUrl: qdrantHttpUrl!,
      qdrantApiKey: null,
    });
    await store.ensureCollection({ name: collection, dimensions: 3 });
    await store.upsert({
      collection,
      fragmentId: matchingId,
      searchText: 'promenade into a waltz turn',
      denseVector: [1, 0, 0],
      payload: payload(matchingId, matchingTagId),
    });
    await store.upsert({
      collection,
      fragmentId: otherId,
      searchText: 'closing line',
      denseVector: [0, 1, 0],
      payload: payload(otherId, randomUUID()),
    });
  });

  afterAll(async () => {
    await fetch(new URL(`/collections/${collection}`, qdrantHttpUrl!), {
      method: 'DELETE',
    });
  });

  it('fuses dense and BM25 candidates under the same tag filter', async () => {
    const points = await store.query({
      collection,
      lexicalText: 'promenade',
      denseVector: [1, 0, 0],
      filter: { tagIds: [matchingTagId] },
      limit: 10,
    });

    expect(points).toHaveLength(1);
    expect(points[0]).toMatchObject({ fragmentId: matchingId });
  });
});

function payload(fragmentId: string, tagId: string) {
  return {
    fragment_id: fragmentId,
    video_id: randomUUID(),
    fragment_revision: 1,
    start_us: 0,
    end_us: 1_000_000,
    fragment_title: 'fragment',
    fragment_description: null,
    fragment_tag_ids: [tagId],
    fragment_tags: ['waltz'],
    source_title: 'source',
    source_description: null,
    source_tag_ids: [],
    source_tags: [],
    collection_ids: [],
  };
}
