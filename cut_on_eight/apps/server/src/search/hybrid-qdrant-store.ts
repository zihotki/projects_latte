import type { EmbeddingProfile, ServerConfig } from '../config.js';
import {
  createRemoteCallPolicy,
  RemoteCallError,
  type ResilientCall,
} from '../resilience/remote-call.js';

export const semanticVectorName = 'semantic-v1';
export const lexicalVectorName = 'lexical-v1';
export const activeSearchAlias = 'cut_on_eight_fragments_active';

export interface SearchCollection {
  readonly name: string;
  readonly dimensions: number;
}

export interface FragmentSearchPayload {
  readonly fragment_id: string;
  readonly video_id: string;
  readonly fragment_revision: number;
  readonly start_us: number;
  readonly end_us: number;
  readonly fragment_title: string | null;
  readonly fragment_description: string | null;
  readonly fragment_tag_ids: readonly string[];
  readonly fragment_tags: readonly string[];
  readonly source_title: string;
  readonly source_description: string | null;
  readonly source_tag_ids: readonly string[];
  readonly source_tags: readonly string[];
  readonly collection_ids: readonly string[];
}

export interface IndexedFragment {
  readonly collection: string;
  readonly fragmentId: string;
  readonly searchText: string;
  readonly denseVector?: readonly number[];
  readonly payload: FragmentSearchPayload;
}

export interface HybridQuery {
  readonly collection: string;
  readonly lexicalText: string;
  readonly denseVector?: readonly number[];
  readonly limit: number;
  readonly filter?: FragmentSearchFilter;
}

export interface FragmentSearchFilter {
  readonly tagIds?: readonly string[];
  readonly collectionIds?: readonly string[];
  readonly videoIds?: readonly string[];
}

export interface RankedFragmentPoint {
  readonly fragmentId: string;
  readonly score: number;
  readonly payload: FragmentSearchPayload;
}

export interface HybridSearchStore {
  ensureCollection(target: SearchCollection): Promise<void>;
  upsert(input: IndexedFragment): Promise<void>;
  delete(collection: string, fragmentId: string): Promise<void>;
  query(input: HybridQuery): Promise<readonly RankedFragmentPoint[]>;
  count(collection: string): Promise<number>;
  aliasTarget(alias: string): Promise<string | null>;
  setAlias(alias: string, collection: string): Promise<void>;
}

export function collectionForProfile(
  profile: EmbeddingProfile,
): SearchCollection {
  return {
    name: `cut_on_eight_fragments_${profile.id}_v1`,
    dimensions: profile.dimensions,
  };
}

export function createHybridSearchStore(
  config: Pick<ServerConfig, 'qdrantHttpUrl' | 'qdrantApiKey'>,
  resilientCall: ResilientCall = createRemoteCallPolicy(),
): HybridSearchStore {
  if (config.qdrantHttpUrl === null) return new DisabledHybridSearchStore();
  return new QdrantHybridSearchStore(
    config.qdrantHttpUrl,
    config.qdrantApiKey,
    resilientCall,
  );
}

class DisabledHybridSearchStore implements HybridSearchStore {
  async ensureCollection(target: SearchCollection): Promise<void> {
    void target;
    throw unavailable();
  }

  async upsert(input: IndexedFragment): Promise<void> {
    void input;
    throw unavailable();
  }

  async delete(collection: string, fragmentId: string): Promise<void> {
    void collection;
    void fragmentId;
    throw unavailable();
  }

  async query(input: HybridQuery): Promise<readonly RankedFragmentPoint[]> {
    void input;
    throw unavailable();
  }

  async count(collection: string): Promise<number> {
    void collection;
    throw unavailable();
  }

  async aliasTarget(alias: string): Promise<string | null> {
    void alias;
    throw unavailable();
  }

  async setAlias(alias: string, collection: string): Promise<void> {
    void alias;
    void collection;
    throw unavailable();
  }
}

class QdrantHybridSearchStore implements HybridSearchStore {
  private readonly collectionReady = new Map<string, Promise<void>>();

  constructor(
    private readonly url: string,
    private readonly apiKey: string | null,
    private readonly resilientCall: ResilientCall,
  ) {}

  async ensureCollection(target: SearchCollection): Promise<void> {
    const existing = this.collectionReady.get(target.name);
    if (existing !== undefined) return existing;
    const ready = this.ensureCollectionOnce(target);
    this.collectionReady.set(target.name, ready);
    try {
      await ready;
    } catch (error) {
      this.collectionReady.delete(target.name);
      throw error;
    }
  }

  async upsert(input: IndexedFragment): Promise<void> {
    const ready = this.collectionReady.get(input.collection);
    if (ready === undefined) {
      throw new Error(
        `Search collection ${input.collection} must be ensured before indexing.`,
      );
    }
    await ready;
    const vector: Record<string, unknown> = {
      [lexicalVectorName]: { text: input.searchText, model: 'qdrant/bm25' },
    };
    if (input.denseVector !== undefined) {
      vector[semanticVectorName] = input.denseVector;
    }
    await this.request(
      `/collections/${input.collection}/points?wait=true&ordering=strong`,
      {
        method: 'PUT',
        body: {
          points: [{ id: input.fragmentId, vector, payload: input.payload }],
        },
      },
    );
  }

  async delete(collection: string, fragmentId: string): Promise<void> {
    await this.request(
      `/collections/${collection}/points/delete?wait=true&ordering=strong`,
      {
        method: 'POST',
        body: { points: [fragmentId] },
      },
    );
  }

  async query(input: HybridQuery): Promise<readonly RankedFragmentPoint[]> {
    const filter = toQdrantFilter(input.filter);
    const lexical = {
      query: { text: input.lexicalText, model: 'qdrant/bm25' },
      using: lexicalVectorName,
      filter,
      limit: input.limit,
    };
    const prefetch =
      input.denseVector === undefined
        ? [lexical]
        : [
            {
              query: input.denseVector,
              using: semanticVectorName,
              filter,
              limit: input.limit,
            },
            lexical,
          ];
    const result = await this.request<QdrantQueryResult>(
      `/collections/${input.collection}/points/query`,
      {
        method: 'POST',
        body:
          input.denseVector === undefined
            ? { ...lexical, with_payload: true, limit: input.limit }
            : {
                prefetch,
                query: { fusion: 'rrf' },
                with_payload: true,
                limit: input.limit,
              },
      },
    );
    return result.points.map((point) => ({
      fragmentId: String(point.id),
      score: point.score,
      payload: point.payload as FragmentSearchPayload,
    }));
  }

  async count(collection: string): Promise<number> {
    const result = await this.request<{ count: number }>(
      `/collections/${collection}/points/count`,
      { method: 'POST', body: { exact: true } },
    );
    return result.count;
  }

  async aliasTarget(alias: string): Promise<string | null> {
    const aliases = await this.request<{
      aliases: Array<{ alias_name: string; collection_name: string }>;
    }>('/aliases');
    return (
      aliases.aliases.find((item) => item.alias_name === alias)
        ?.collection_name ?? null
    );
  }

  async setAlias(alias: string, collection: string): Promise<void> {
    const aliases = await this.request<{
      aliases: Array<{ alias_name: string }>;
    }>('/aliases');
    const actions: unknown[] = [];
    if (aliases.aliases.some((item) => item.alias_name === alias)) {
      actions.push({ delete_alias: { alias_name: alias } });
    }
    actions.push({
      create_alias: { collection_name: collection, alias_name: alias },
    });
    await this.request('/collections/aliases', {
      method: 'POST',
      body: { actions },
    });
  }

  private async ensureCollectionOnce(target: SearchCollection): Promise<void> {
    const collections = await this.request<{
      collections: Array<{ name: string }>;
    }>('/collections');
    if (collections.collections.some(({ name }) => name === target.name))
      return;
    await this.request(`/collections/${target.name}`, {
      method: 'PUT',
      body: {
        vectors: {
          [semanticVectorName]: { size: target.dimensions, distance: 'Cosine' },
        },
        sparse_vectors: { [lexicalVectorName]: { modifier: 'idf' } },
        on_disk_payload: true,
      },
    });
    await Promise.all([
      this.createPayloadIndex(target.name, 'video_id'),
      this.createPayloadIndex(target.name, 'fragment_tag_ids'),
      this.createPayloadIndex(target.name, 'collection_ids'),
      this.createPayloadIndex(target.name, 'source_tag_ids'),
    ]);
  }

  private async createPayloadIndex(
    collection: string,
    fieldName: string,
  ): Promise<void> {
    await this.request(
      `/collections/${collection}/index?wait=true&ordering=strong`,
      {
        method: 'PUT',
        body: { field_name: fieldName, field_schema: 'keyword' },
      },
    );
  }

  private async request<T = unknown>(
    path: string,
    init: {
      readonly method?: 'DELETE' | 'GET' | 'POST' | 'PUT';
      readonly body?: unknown;
    } = {},
  ): Promise<T> {
    return this.resilientCall.execute(async (signal) => {
      const response = await fetch(new URL(path, this.url), {
        method: init.method ?? 'GET',
        headers: {
          accept: 'application/json',
          ...(init.body === undefined
            ? {}
            : { 'content-type': 'application/json' }),
          ...(this.apiKey === null ? {} : { 'api-key': this.apiKey }),
        },
        body: init.body === undefined ? undefined : JSON.stringify(init.body),
        signal,
      }).catch((error: unknown) => {
        throw toRemoteCallError(error);
      });
      if (!response.ok) {
        const detail = (await response.text()).trim();
        throw new RemoteCallError(
          response.status,
          detail === ''
            ? `Qdrant request failed with HTTP ${response.status}.`
            : `Qdrant request failed with HTTP ${response.status}: ${detail}`,
        );
      }
      const envelope = (await response.json()) as { result: T };
      return envelope.result;
    });
  }
}

function toQdrantFilter(filter: FragmentSearchFilter | undefined): unknown {
  if (filter === undefined) return undefined;
  const must: unknown[] = [];
  if (filter.videoIds !== undefined && filter.videoIds.length > 0) {
    must.push({ key: 'video_id', match: { any: filter.videoIds } });
  }
  if (filter.collectionIds !== undefined && filter.collectionIds.length > 0) {
    must.push({ key: 'collection_ids', match: { any: filter.collectionIds } });
  }
  const should =
    filter.tagIds === undefined || filter.tagIds.length === 0
      ? []
      : [
          { key: 'fragment_tag_ids', match: { any: filter.tagIds } },
          { key: 'source_tag_ids', match: { any: filter.tagIds } },
        ];
  return must.length === 0 && should.length === 0
    ? undefined
    : {
        ...(must.length === 0 ? {} : { must }),
        ...(should.length === 0 ? {} : { should }),
      };
}

interface QdrantQueryResult {
  readonly points: readonly {
    id: string | number;
    score: number;
    payload: unknown;
  }[];
}

function unavailable(): RemoteCallError {
  return new RemoteCallError(null, 'Qdrant is not configured.');
}

function toRemoteCallError(error: unknown): RemoteCallError {
  if (error instanceof RemoteCallError) return error;
  const status =
    typeof error === 'object' &&
    error !== null &&
    'status' in error &&
    typeof error.status === 'number'
      ? error.status
      : null;
  return new RemoteCallError(
    status,
    `Qdrant request failed${error instanceof Error ? `: ${error.message}` : '.'}`,
  );
}
