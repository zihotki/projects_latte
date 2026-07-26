import type { ServerConfig } from '../config.js';
import {
  createRemoteCallPolicy,
  RemoteCallError,
  type ResilientCall,
} from '../resilience/remote-call.js';

export const fragmentProjectionCollection = 'cut_on_eight_fragments_v1';

export interface FragmentProjection {
  readonly id: string;
  readonly payload: {
    readonly projection_version: 1;
    readonly projection_revision: number;
    readonly fragment_id: string;
    readonly video_id: string;
    readonly fragment_revision: number;
    readonly start_us: number;
    readonly end_us: number;
    readonly fragment_title: string | null;
    readonly fragment_description: string | null;
    readonly fragment_tags: readonly string[];
    readonly source_title: string;
    readonly source_description: string | null;
    readonly source_tags: readonly string[];
    readonly collection_ids: readonly string[];
  };
}

export interface FragmentProjectionStore {
  ensureCollection(): Promise<void>;
  upsert(point: FragmentProjection): Promise<void>;
  delete(fragmentId: string): Promise<void>;
  recreate(): Promise<void>;
  get(fragmentId: string): Promise<FragmentProjection | null>;
  count(): Promise<number>;
}

export function createFragmentProjectionStore(
  config: Pick<ServerConfig, 'qdrantHttpUrl' | 'qdrantApiKey'>,
  resilientCall: ResilientCall = createRemoteCallPolicy(),
): FragmentProjectionStore {
  if (config.qdrantHttpUrl === null) return new DisabledProjectionStore();
  return new QdrantProjectionStore(
    config.qdrantHttpUrl,
    config.qdrantApiKey,
    resilientCall,
  );
}

class DisabledProjectionStore implements FragmentProjectionStore {
  async ensureCollection(): Promise<void> {
    throw unavailable();
  }

  async upsert(point: FragmentProjection): Promise<void> {
    void point;
    throw unavailable();
  }

  async delete(fragmentId: string): Promise<void> {
    void fragmentId;
    throw unavailable();
  }

  async recreate(): Promise<void> {
    throw unavailable();
  }

  async get(fragmentId: string): Promise<FragmentProjection | null> {
    void fragmentId;
    throw unavailable();
  }

  async count(): Promise<number> {
    throw unavailable();
  }
}

class QdrantProjectionStore implements FragmentProjectionStore {
  private collectionReady: Promise<void> | null = null;

  constructor(
    private readonly url: string,
    private readonly apiKey: string | null,
    private readonly resilientCall: ResilientCall,
  ) {}

  async ensureCollection(): Promise<void> {
    this.collectionReady ??= this.ensureCollectionOnce();
    try {
      await this.collectionReady;
    } catch (error) {
      this.collectionReady = null;
      throw error;
    }
  }

  async upsert(point: FragmentProjection): Promise<void> {
    await this.ensureCollection();
    await this.request(
      `/collections/${fragmentProjectionCollection}/points?wait=true&ordering=strong`,
      {
        method: 'PUT',
        body: {
          points: [
            {
              id: point.id,
              vector: {},
              payload: point.payload,
            },
          ],
        },
      },
    );
  }

  async delete(fragmentId: string): Promise<void> {
    await this.ensureCollection();
    await this.request(
      `/collections/${fragmentProjectionCollection}/points/delete?wait=true&ordering=strong`,
      { method: 'POST', body: { points: [fragmentId] } },
    );
  }

  async recreate(): Promise<void> {
    await this.request(`/collections/${fragmentProjectionCollection}`, {
      method: 'DELETE',
      allowNotFound: true,
    });
    await this.createCollection();
    await this.createPayloadIndexes();
    this.collectionReady = Promise.resolve();
  }

  async get(fragmentId: string): Promise<FragmentProjection | null> {
    await this.ensureCollection();
    const points = await this.request<QdrantPoint[]>(
      `/collections/${fragmentProjectionCollection}/points`,
      {
        method: 'POST',
        body: { ids: [fragmentId], with_payload: true, with_vector: false },
      },
    );
    const point = points[0];
    if (point === undefined || point.payload === undefined) return null;
    return {
      id: String(point.id),
      payload: point.payload as FragmentProjection['payload'],
    };
  }

  async count(): Promise<number> {
    await this.ensureCollection();
    const result = await this.request<{ count: number }>(
      `/collections/${fragmentProjectionCollection}/points/count`,
      { method: 'POST', body: { exact: true } },
    );
    return result.count;
  }

  private async ensureCollectionOnce(): Promise<void> {
    const collections = await this.request<{ collections: { name: string }[] }>(
      '/collections',
    );
    if (
      !collections.collections.some(
        ({ name }) => name === fragmentProjectionCollection,
      )
    ) {
      await this.createCollection();
      await this.createPayloadIndexes();
    }
  }

  private async createCollection(): Promise<void> {
    await this.request(`/collections/${fragmentProjectionCollection}`, {
      method: 'PUT',
      body: { vectors: {}, on_disk_payload: true },
    });
  }

  private async createPayloadIndexes(): Promise<void> {
    await Promise.all([
      this.createPayloadIndex('video_id', 'keyword'),
      this.createPayloadIndex('fragment_tags', 'keyword'),
      this.createPayloadIndex('source_tags', 'keyword'),
      this.createPayloadIndex('collection_ids', 'keyword'),
      this.createPayloadIndex('fragment_title', 'text'),
      this.createPayloadIndex('fragment_description', 'text'),
      this.createPayloadIndex('source_title', 'text'),
      this.createPayloadIndex('source_description', 'text'),
    ]);
  }

  private async createPayloadIndex(
    field_name: string,
    field_schema: 'keyword' | 'text',
  ): Promise<void> {
    await this.request(
      `/collections/${fragmentProjectionCollection}/index?wait=true&ordering=strong`,
      { method: 'PUT', body: { field_name, field_schema } },
    );
  }

  private async request<T = unknown>(
    path: string,
    init: {
      readonly method?: 'DELETE' | 'GET' | 'POST' | 'PUT';
      readonly body?: unknown;
      readonly allowNotFound?: boolean;
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
      if (response.status === 404 && init.allowNotFound === true) {
        return undefined as T;
      }
      if (!response.ok) {
        throw new RemoteCallError(response.status, 'Qdrant request failed.');
      }
      const envelope = (await response.json()) as QdrantResponse<T>;
      return envelope.result;
    });
  }
}

interface QdrantResponse<T> {
  readonly result: T;
}

interface QdrantPoint {
  readonly id: string | number;
  readonly payload?: unknown;
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
