import { v7 as uuidv7 } from 'uuid';
import { sql, type Kysely } from 'kysely';
import type { CatalogDatabase } from '../catalog/database-types.js';
import type { EmbeddingProfile } from '../config.js';
import type { EmbeddingClient } from './embedding-client.js';
import {
  activeSearchAlias,
  collectionForProfile,
  type FragmentSearchPayload,
  type HybridSearchStore,
  type SearchCollection,
} from './hybrid-qdrant-store.js';
import {
  loadSearchDocument,
  type CurrentFragmentSearchDocument,
} from './search-document.js';

const rebuildBatchSize = 100;

export interface SemanticSearchRebuildDependencies {
  readonly database: Kysely<CatalogDatabase>;
  readonly profile: EmbeddingProfile;
  readonly store: HybridSearchStore;
  readonly embeddings: EmbeddingClient;
  readonly loadDocument?: (
    database: Kysely<CatalogDatabase>,
    fragmentId: string,
  ) => Promise<CurrentFragmentSearchDocument | null>;
}

export interface SemanticSearchRebuildRun {
  readonly id: string;
  readonly profileId: string;
  readonly targetCollection: string;
  readonly snapshotHighWaterPosition: number;
  readonly status: 'ready' | 'failed';
}

/**
 * Builds a disposable profile collection from PostgreSQL, catches it up with
 * the durable event log, and only then moves the query alias in one Qdrant
 * alias operation. Failed collections remain available for diagnosis.
 */
export async function rebuildSemanticSearch(
  dependencies: SemanticSearchRebuildDependencies,
): Promise<SemanticSearchRebuildRun> {
  const id = uuidv7();
  const target = rebuildTarget(dependencies.profile, id);
  const snapshotHighWaterPosition = await currentHighWaterPosition(
    dependencies.database,
  );

  await dependencies.database
    .insertInto('semantic_search_rebuilds')
    .values({
      id,
      profile_id: dependencies.profile.id,
      target_collection_name: target.name,
      snapshot_high_water_position: snapshotHighWaterPosition,
      status: 'running',
      error_text: null,
      updated_at: new Date(),
    })
    .execute();

  try {
    await dependencies.store.ensureCollection(target);
    await indexSnapshot(dependencies, target);
    await catchUpEvents(dependencies, target, snapshotHighWaterPosition);

    const [indexedCount, visibleCount] = await Promise.all([
      dependencies.store.count(target.name),
      visibleFragmentCount(dependencies.database),
    ]);
    if (indexedCount !== visibleCount) {
      throw new Error(
        `Search rebuild validation failed: target has ${indexedCount} points but catalog has ${visibleCount} visible fragments.`,
      );
    }

    await dependencies.store.setAlias(activeSearchAlias, target.name);
    await dependencies.database
      .updateTable('semantic_search_rebuilds')
      .set({ status: 'ready', error_text: null, updated_at: new Date() })
      .where('id', '=', id)
      .execute();
    return {
      id,
      profileId: dependencies.profile.id,
      targetCollection: target.name,
      snapshotHighWaterPosition,
      status: 'ready',
    };
  } catch (error) {
    const errorText = safeErrorText(error);
    await dependencies.database
      .updateTable('semantic_search_rebuilds')
      .set({ status: 'failed', error_text: errorText, updated_at: new Date() })
      .where('id', '=', id)
      .execute();
    throw error;
  }
}

function rebuildTarget(
  profile: EmbeddingProfile,
  runId: string,
): SearchCollection {
  const base = collectionForProfile(profile);
  return { ...base, name: `${base.name}_${runId.replaceAll('-', '')}` };
}

async function indexSnapshot(
  dependencies: SemanticSearchRebuildDependencies,
  target: SearchCollection,
): Promise<void> {
  const rows = await dependencies.database
    .selectFrom('fragments')
    .innerJoin('videos', 'videos.id', 'fragments.video_id')
    .select('fragments.id')
    .where('fragments.deleted_at', 'is', null)
    .where('videos.status', '!=', 'deleting')
    .orderBy('fragments.id')
    .execute();
  for (const { id } of rows) {
    await indexCurrentDocument(dependencies, target, id);
  }
}

async function catchUpEvents(
  dependencies: SemanticSearchRebuildDependencies,
  target: SearchCollection,
  initialPosition: number,
): Promise<void> {
  let cursor = initialPosition;
  for (;;) {
    const events = await dependencies.database
      .selectFrom('integration_events')
      .select(['position', 'event_type', 'aggregate_type', 'aggregate_id'])
      .where(sql<boolean>`position > ${cursor}::bigint`)
      .orderBy('position')
      .limit(rebuildBatchSize)
      .execute();
    if (events.length === 0) {
      if ((await currentHighWaterPosition(dependencies.database)) <= cursor)
        return;
      continue;
    }
    for (const event of events) {
      cursor = Number(event.position);
      if (
        event.aggregate_type === 'fragment' &&
        (event.event_type === 'fragment.changed.v1' ||
          event.event_type === 'fragment.deleted.v1')
      ) {
        await indexCurrentDocument(dependencies, target, event.aggregate_id);
      }
    }
  }
}

async function indexCurrentDocument(
  dependencies: SemanticSearchRebuildDependencies,
  target: SearchCollection,
  fragmentId: string,
): Promise<void> {
  const document = await (dependencies.loadDocument ?? loadSearchDocument)(
    dependencies.database,
    fragmentId,
  );
  if (document === null) {
    await dependencies.store.delete(target.name, fragmentId);
    return;
  }
  const denseVector = dependencies.embeddings.available()
    ? await embed(dependencies.embeddings, document.document.text)
    : undefined;
  await dependencies.store.upsert({
    collection: target.name,
    fragmentId: document.fragmentId,
    searchText: document.document.text,
    denseVector,
    payload: payloadFor(document),
  });
}

function payloadFor(
  document: CurrentFragmentSearchDocument,
): FragmentSearchPayload {
  return {
    fragment_id: document.fragmentId,
    video_id: document.videoId,
    fragment_revision: document.fragmentRevision,
    start_us: document.startUs,
    end_us: document.endUs,
    fragment_title: document.title,
    fragment_description: document.description,
    fragment_tag_ids: document.fragmentTagIds,
    fragment_tags: document.fragmentTags.map(({ name }) => name),
    source_title: document.sourceTitle,
    source_description: document.sourceDescription,
    source_tag_ids: document.sourceTagIds,
    source_tags: document.sourceTags.map(({ name }) => name),
    collection_ids: document.collectionIds,
  };
}

async function embed(
  embeddings: EmbeddingClient,
  text: string,
): Promise<readonly number[]> {
  const vector = (await embeddings.embed([text]))[0];
  if (vector === undefined) {
    throw new Error('Embedding response did not contain the requested vector.');
  }
  return vector;
}

async function currentHighWaterPosition(
  database: Kysely<CatalogDatabase>,
): Promise<number> {
  const row = await database
    .selectFrom('integration_events')
    .select((expression) => expression.fn.max('position').as('position'))
    .executeTakeFirstOrThrow();
  return row.position === null ? 0 : Number(row.position);
}

async function visibleFragmentCount(
  database: Kysely<CatalogDatabase>,
): Promise<number> {
  const row = await database
    .selectFrom('fragments')
    .innerJoin('videos', 'videos.id', 'fragments.video_id')
    .select((expression) =>
      expression.fn.count<number>('fragments.id').as('count'),
    )
    .where('fragments.deleted_at', 'is', null)
    .where('videos.status', '!=', 'deleting')
    .executeTakeFirstOrThrow();
  return Number(row.count);
}

function safeErrorText(error: unknown): string {
  return (
    error instanceof Error ? error.message : 'Unknown rebuild failure'
  ).slice(0, 2_000);
}
