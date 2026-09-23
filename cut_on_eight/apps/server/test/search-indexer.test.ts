import { createHash, randomUUID } from 'node:crypto';
import { describe, expect, it, vi } from 'vitest';
import type { Kysely } from 'kysely';
import type { CatalogDatabase } from '../src/catalog/database-types.js';
import type { EmbeddingClient } from '../src/search/embedding-client.js';
import type {
  HybridSearchStore,
  SearchCollection,
} from '../src/search/hybrid-qdrant-store.js';
import {
  ensureActiveSearchAlias,
  handleSearchIndexFailure,
  processSearchIndexMessage,
  type SearchIndexerDependencies,
} from '../src/search/search-indexer.js';
import type { SearchIndexStateStore } from '../src/search/search-index-state.js';

const fragmentId = randomUUID();
const collection: SearchCollection = {
  name: 'cut_on_eight_fragments_embeddinggemma-v1_v1',
  dimensions: 3,
};

describe('search indexer', () => {
  it('creates the active alias for a fresh collection before consuming events', async () => {
    const fixture = dependencies();
    fixture.store.aliasTarget.mockResolvedValue(null);
    await ensureActiveSearchAlias(fixture.store, collection);

    expect(fixture.store.setAlias).toHaveBeenCalledWith(
      'cut_on_eight_fragments_active',
      collection.name,
    );
  });

  it('keeps an existing rebuild alias', async () => {
    const fixture = dependencies();
    fixture.store.aliasTarget.mockResolvedValue('rebuilt_collection');
    await ensureActiveSearchAlias(fixture.store, collection);
    expect(fixture.store.setAlias).not.toHaveBeenCalled();
  });
  it('records a terminal delivery as failed without marking its position applied', async () => {
    const fixture = dependencies();
    const message = changedMessageAt(46);
    Object.defineProperty(message, 'info', { value: { deliveryCount: 10 } });
    Object.defineProperty(message, 'term', { value: vi.fn() });

    await handleSearchIndexFailure(fixture.dependencies, message);

    expect(fixture.indexState.recordFailed).toHaveBeenCalledWith(
      expect.objectContaining({
        fragmentId,
        sourcePosition: 46,
        failureCode: 'indexing_failed',
      }),
    );
    expect(message.term).toHaveBeenCalledWith('indexing_failed');
    expect(fixture.position).toBeNull();
  });
  it('acknowledges duplicate delivery without another upsert', async () => {
    const fixture = dependencies();
    const message = changedMessageAt(42);

    await processSearchIndexMessage(fixture.dependencies, message);
    await processSearchIndexMessage(fixture.dependencies, changedMessageAt(42));

    expect(fixture.store.upsert).toHaveBeenCalledTimes(1);
    expect(fixture.position).toBe(42);
    expect(message.ackAck).toHaveBeenCalledOnce();
  });

  it('records a deletion only after Qdrant accepts it', async () => {
    const fixture = dependencies();
    fixture.store.delete.mockRejectedValueOnce(new Error('Qdrant unavailable'));

    await expect(
      processSearchIndexMessage(fixture.dependencies, deletedMessageAt(43)),
    ).rejects.toThrow('Qdrant unavailable');
    expect(fixture.indexState.recordApplied).not.toHaveBeenCalled();

    const retry = deletedMessageAt(43);
    await processSearchIndexMessage(fixture.dependencies, retry);

    expect(fixture.store.delete).toHaveBeenCalledWith(
      collection.name,
      fragmentId,
    );
    expect(fixture.position).toBe(43);
    expect(retry.ackAck).toHaveBeenCalledOnce();
  });

  it('leaves a failed embedding delivery unacknowledged and pending', async () => {
    const fixture = dependencies({
      embeddingAvailable: true,
      embeddingFailure: new Error('LM Studio unavailable'),
    });
    const message = changedMessageAt(44);

    await expect(
      processSearchIndexMessage(fixture.dependencies, message),
    ).rejects.toThrow('LM Studio unavailable');

    expect(fixture.store.upsert).not.toHaveBeenCalled();
    expect(fixture.indexState.recordPending).toHaveBeenCalledOnce();
    expect(message.ackAck).not.toHaveBeenCalled();
    expect(fixture.position).toBeNull();
  });

  it('indexes lexical BM25 text without a configured embedding endpoint', async () => {
    const fixture = dependencies({ embeddingAvailable: false });
    const message = changedMessageAt(45);

    await processSearchIndexMessage(fixture.dependencies, message);

    expect(fixture.embeddings.embed).not.toHaveBeenCalled();
    expect(fixture.store.upsert).toHaveBeenCalledWith(
      expect.objectContaining({ denseVector: undefined }),
    );
    expect(fixture.position).toBe(45);
    expect(message.ackAck).toHaveBeenCalledOnce();
  });
});

function dependencies(
  options: {
    readonly embeddingAvailable?: boolean;
    readonly embeddingFailure?: Error;
  } = {},
) {
  let position: number | null = null;
  const indexState: SearchIndexStateStore = {
    isAlreadyApplied: vi.fn(
      async (_profile, _fragment, eventPosition) =>
        position !== null && position >= eventPosition,
    ),
    recordPending: vi.fn(async () => undefined),
    recordFailed: vi.fn(async () => undefined),
    recordApplied: vi.fn(async (state) => {
      position = state.sourcePosition;
    }),
  };
  const store = {
    ensureCollection: vi.fn(),
    upsert: vi.fn(),
    delete: vi.fn(),
    query: vi.fn(),
    aliasTarget: vi.fn(),
    setAlias: vi.fn(),
  } as unknown as {
    [Key in keyof HybridSearchStore]: ReturnType<typeof vi.fn>;
  };
  const embeddings: EmbeddingClient = {
    available: () =>
      options.embeddingAvailable ?? options.embeddingFailure === undefined,
    embed: vi.fn(async () => {
      if (options.embeddingFailure !== undefined)
        throw options.embeddingFailure;
      return [[0.1, 0.2, 0.3]];
    }),
  };
  const dependencies: SearchIndexerDependencies = {
    database: {} as Kysely<CatalogDatabase>,
    runtime: {} as SearchIndexerDependencies['runtime'],
    profile: {
      id: 'embeddinggemma-v1',
      model: 'google/embeddinggemma-300M',
      dimensions: 3,
      baseUrl: 'http://localhost/v1',
    },
    collection,
    store,
    embeddings,
    indexState,
    loadDocument: vi.fn(async () => document()),
  };
  return {
    dependencies,
    embeddings,
    indexState,
    store,
    get position() {
      return position;
    },
  };
}

function document() {
  const text = 'promenade\nwaltz';
  return {
    fragmentId,
    fragmentRevision: 2,
    videoId: randomUUID(),
    startUs: 1_000,
    endUs: 2_000,
    title: 'promenade',
    description: null,
    fragmentTags: [{ id: randomUUID(), name: 'waltz' }],
    sourceTitle: 'lesson',
    sourceDescription: null,
    sourceTags: [],
    fragmentTagIds: [],
    sourceTagIds: [],
    collectionIds: [],
    document: {
      text,
      hash: createHash('sha256').update(text, 'utf8').digest('hex'),
    },
  };
}

function changedMessageAt(position: number) {
  return message({
    eventId: randomUUID(),
    position,
    type: 'fragment.changed.v1',
    schemaVersion: 1,
    aggregate: { type: 'fragment', id: fragmentId, revision: 2 },
    occurredAt: new Date().toISOString(),
    correlationId: null,
    causationId: null,
    payload: { fragmentId },
  });
}

function deletedMessageAt(position: number) {
  return message({
    eventId: randomUUID(),
    position,
    type: 'fragment.deleted.v1',
    schemaVersion: 1,
    aggregate: { type: 'fragment', id: fragmentId, revision: 3 },
    occurredAt: new Date().toISOString(),
    correlationId: null,
    causationId: null,
    payload: { fragmentId },
  });
}

function message(event: unknown) {
  return {
    data: new TextEncoder().encode(JSON.stringify(event)),
    ackAck: vi.fn(async () => true),
  } as unknown as Parameters<typeof processSearchIndexMessage>[1];
}
