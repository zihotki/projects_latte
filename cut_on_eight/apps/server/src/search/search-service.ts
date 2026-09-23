import {
  fragmentSearchResponseSchema,
  fragmentSearchResultSchema,
  type FragmentSearchQuery,
  type FragmentPreviewDto,
  type FragmentSearchResponse,
  type FragmentSearchResultDto,
} from '@cut-on-eight/api-contracts';
import type { Kysely } from 'kysely';
import type { CatalogDatabase } from '../catalog/database-types.js';
import { safeMicroseconds } from '../catalog/database-types.js';
import type { EmbeddingProfile } from '../config.js';
import type { EmbeddingClient } from './embedding-client.js';
import {
  activeSearchAlias,
  type FragmentSearchPayload,
  type HybridSearchStore,
  type RankedFragmentPoint,
} from './hybrid-qdrant-store.js';

const candidateLimit = 50;

export interface FragmentSearchService {
  search(query: FragmentSearchQuery): Promise<FragmentSearchResponse>;
}

export interface FragmentSearchServiceDependencies {
  readonly database: Kysely<CatalogDatabase>;
  readonly profile: EmbeddingProfile;
  readonly store: HybridSearchStore;
  readonly embeddings: EmbeddingClient;
  readonly countPending?: () => Promise<number>;
  readonly loadMetadata?: (
    fragmentIds: readonly string[],
  ) => Promise<ReadonlyMap<string, SearchResultMetadata>>;
}

export interface SearchResultMetadata {
  readonly previewState: 'pending' | 'ready' | 'failed';
  readonly preview: FragmentPreviewDto | null;
}

export class SearchUnavailableError extends Error {
  readonly code = 'search_unavailable';

  constructor(cause?: unknown) {
    super('Search is temporarily unavailable.', { cause });
    this.name = 'SearchUnavailableError';
  }
}

export function createFragmentSearchService(
  dependencies: FragmentSearchServiceDependencies,
): FragmentSearchService {
  // Reads always use the alias. A rebuild can atomically move it after its
  // target has caught up, without changing API configuration or restarting it.
  const countPending =
    dependencies.countPending ??
    (() =>
      countPendingSearchDocuments(
        dependencies.database,
        dependencies.profile.id,
      ));
  const loadMetadata =
    dependencies.loadMetadata ??
    ((fragmentIds) =>
      loadSearchResultMetadata(dependencies.database, fragmentIds));

  return {
    async search(query): Promise<FragmentSearchResponse> {
      const denseVector = await embedQueryOrDegrade(
        dependencies.embeddings,
        query.q,
      );
      let points: readonly RankedFragmentPoint[];
      try {
        points = await dependencies.store.query({
          collection: activeSearchAlias,
          lexicalText: query.q,
          denseVector,
          limit: candidateLimit,
          filter: {
            tagIds: query.tagIds,
            collectionIds: query.collectionIds,
            videoIds: query.videoIds,
          },
        });
      } catch (error) {
        throw new SearchUnavailableError(error);
      }

      const [pending, metadata] = await Promise.all([
        countPending(),
        loadMetadata(
          points.slice(0, query.limit).map(({ fragmentId }) => fragmentId),
        ),
      ]);
      return fragmentSearchResponseSchema.parse({
        mode: denseVector === undefined ? 'lexical' : 'hybrid',
        indexing: { pending },
        results: mapPoints(points.slice(0, query.limit), metadata),
      });
    },
  };
}

async function embedQueryOrDegrade(
  embeddings: EmbeddingClient,
  query: string,
): Promise<readonly number[] | undefined> {
  if (!embeddings.available()) return undefined;
  try {
    const vectors = await embeddings.embed([query]);
    const vector = vectors[0];
    if (vector === undefined) {
      throw new Error(
        'Embedding response did not contain the requested vector.',
      );
    }
    return vector;
  } catch {
    // Lexical BM25 remains useful while the optional embedding endpoint is down.
    return undefined;
  }
}

async function countPendingSearchDocuments(
  database: Kysely<CatalogDatabase>,
  profileId: string,
): Promise<number> {
  const row = await database
    .selectFrom('semantic_search_index_state')
    .select((expression) =>
      expression.fn.count<number>('fragment_id').as('count'),
    )
    .where('profile_id', '=', profileId)
    .where('status', '=', 'pending')
    .executeTakeFirstOrThrow();
  return Number(row.count);
}

async function loadSearchResultMetadata(
  database: Kysely<CatalogDatabase>,
  fragmentIds: readonly string[],
): Promise<ReadonlyMap<string, SearchResultMetadata>> {
  if (fragmentIds.length === 0) return new Map();
  const rows = await database
    .selectFrom('fragment_previews')
    .select([
      'fragment_id',
      'status',
      'asset_id',
      'fragment_revision',
      'sample_us',
      'columns',
      'rows',
      'frame_width',
      'frame_height',
    ])
    .where('fragment_id', 'in', [...fragmentIds])
    .execute();
  return new Map(
    rows.map((row) => [
      row.fragment_id,
      {
        previewState: row.status,
        preview:
          row.status === 'ready' && row.asset_id !== null
            ? {
                assetId: row.asset_id,
                href: `/api/assets/${encodeURIComponent(row.asset_id)}`,
                revision: row.fragment_revision,
                sampleUs: row.sample_us.map(safeMicroseconds),
                columns: row.columns,
                rows: row.rows,
                frameWidth: row.frame_width,
                frameHeight: row.frame_height,
              }
            : null,
      } satisfies SearchResultMetadata,
    ]),
  );
}

function mapPoints(
  points: readonly RankedFragmentPoint[],
  metadata: ReadonlyMap<string, SearchResultMetadata>,
): FragmentSearchResultDto[] {
  return points.map(({ score, payload }) =>
    fragmentSearchResultSchema.parse({
      id: payload.fragment_id,
      title: payload.fragment_title,
      description: payload.fragment_description,
      tags: tagsFromPayload(payload),
      startUs: payload.start_us,
      endUs: payload.end_us,
      videoId: payload.video_id,
      sourceTitle: payload.source_title,
      collections: [],
      score,
      previewState:
        metadata.get(payload.fragment_id)?.previewState ?? 'pending',
      preview: metadata.get(payload.fragment_id)?.preview ?? null,
    }),
  );
}

function tagsFromPayload(payload: FragmentSearchPayload) {
  return payload.fragment_tag_ids.flatMap((id, index) => {
    const name = payload.fragment_tags[index]?.trim();
    return name === undefined || name === '' ? [] : [{ id, name }];
  });
}
