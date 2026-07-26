import { type Kysely, type Transaction } from 'kysely';
import type { CatalogDatabase } from '../catalog/database-types.js';
import { safeMicroseconds } from '../catalog/database-types.js';
import type { FragmentProjection } from './qdrant-client.js';
import { appendEvent } from '../events/event-store.js';
import type {
  FragmentChangedEvent,
  FragmentDeletedEvent,
  FragmentProjectionPayload,
} from '../events/contracts.js';

export const projectionVersion = 1 as const;

type Database = Kysely<CatalogDatabase> | Transaction<CatalogDatabase>;

export type ProjectionWork =
  | { readonly kind: 'skip' }
  | { readonly kind: 'delete' }
  | { readonly kind: 'upsert'; readonly point: FragmentProjection };

export async function appendFragmentProjectionEvent(
  transaction: Transaction<CatalogDatabase>,
  fragmentId: string,
): Promise<FragmentChangedEvent | FragmentDeletedEvent | null> {
  const fragment = await transaction
    .selectFrom('fragments')
    .innerJoin('videos', 'videos.id', 'fragments.video_id')
    .select([
      'fragments.id',
      'fragments.revision',
      'fragments.deleted_at',
      'videos.status as source_status',
    ])
    .where('fragments.id', '=', fragmentId)
    .executeTakeFirst();
  if (fragment === undefined) return null;
  if (fragment.deleted_at !== null || fragment.source_status === 'deleting') {
    return appendEvent(transaction, {
      type: 'fragment.deleted.v1',
      schemaVersion: 1,
      aggregate: {
        type: 'fragment',
        id: fragment.id,
        revision: fragment.revision,
      },
      correlationId: null,
      causationId: null,
      payload: { fragmentId: fragment.id },
    }) as Promise<FragmentDeletedEvent>;
  }
  const work = await buildProjectionWork(
    transaction,
    fragmentId,
    fragment.revision,
  );
  if (work.kind !== 'upsert') return null;
  return appendEvent(transaction, {
    type: 'fragment.changed.v1',
    schemaVersion: 1,
    aggregate: {
      type: 'fragment',
      id: fragment.id,
      revision: fragment.revision,
    },
    correlationId: null,
    causationId: null,
    payload: toEventPayload(work.point),
  }) as Promise<FragmentChangedEvent>;
}

export async function loadProjectionWork(
  database: Database,
  fragmentId: string,
  expectedProjectionRevision: number,
): Promise<ProjectionWork> {
  const state = await database
    .selectFrom('search_projection_state')
    .select('projection_revision')
    .where('fragment_id', '=', fragmentId)
    .executeTakeFirst();
  if (state === undefined) return { kind: 'delete' };
  if (state.projection_revision !== expectedProjectionRevision) {
    return { kind: 'skip' };
  }
  return buildProjectionWork(database, fragmentId, expectedProjectionRevision);
}

async function buildProjectionWork(
  database: Database,
  fragmentId: string,
  projectionRevision: number,
): Promise<ProjectionWork> {
  const fragment = await database
    .selectFrom('fragments')
    .innerJoin('videos', 'videos.id', 'fragments.video_id')
    .select([
      'fragments.id',
      'fragments.video_id',
      'fragments.start_us',
      'fragments.end_us',
      'fragments.title as fragment_title',
      'fragments.description as fragment_description',
      'fragments.revision as fragment_revision',
      'fragments.deleted_at',
      'videos.title as source_title',
      'videos.description as source_description',
      'videos.status as source_status',
    ])
    .where('fragments.id', '=', fragmentId)
    .executeTakeFirst();
  if (
    fragment === undefined ||
    fragment.deleted_at !== null ||
    fragment.source_status === 'deleting'
  ) {
    return { kind: 'delete' };
  }

  const [fragmentTags, sourceTags] = await Promise.all([
    fragmentTagsFor(database, fragmentId),
    videoTagsFor(database, fragment.video_id),
  ]);
  return {
    kind: 'upsert',
    point: {
      id: fragment.id,
      payload: {
        projection_version: projectionVersion,
        projection_revision: projectionRevision,
        fragment_id: fragment.id,
        video_id: fragment.video_id,
        fragment_revision: fragment.fragment_revision,
        start_us: safeMicroseconds(fragment.start_us),
        end_us: safeMicroseconds(fragment.end_us),
        fragment_title: fragment.fragment_title,
        fragment_description: fragment.fragment_description,
        fragment_tags: fragmentTags,
        source_title: fragment.source_title,
        source_description: fragment.source_description,
        source_tags: sourceTags,
        // Collections are introduced by a later Phase 4 slice.
        collection_ids: [],
      },
    },
  };
}

export async function markProjectionReady(
  database: Kysely<CatalogDatabase>,
  fragmentId: string,
  expectedProjectionRevision: number,
): Promise<void> {
  await database
    .updateTable('search_projection_state')
    .set({
      projection_version: projectionVersion,
      status: 'ready',
      last_failure_code: null,
      updated_at: new Date(),
    })
    .where('fragment_id', '=', fragmentId)
    .where('projection_revision', '=', expectedProjectionRevision)
    .execute();
}

function toEventPayload(point: FragmentProjection): FragmentProjectionPayload {
  return {
    projectionVersion: point.payload.projection_version,
    fragmentId: point.payload.fragment_id,
    videoId: point.payload.video_id,
    fragmentRevision: point.payload.fragment_revision,
    startUs: point.payload.start_us,
    endUs: point.payload.end_us,
    fragmentTitle: point.payload.fragment_title,
    fragmentDescription: point.payload.fragment_description,
    fragmentTags: point.payload.fragment_tags,
    sourceTitle: point.payload.source_title,
    sourceDescription: point.payload.source_description,
    sourceTags: point.payload.source_tags,
  };
}

export async function markProjectionFailed(
  database: Kysely<CatalogDatabase>,
  fragmentId: string,
  expectedProjectionRevision: number,
): Promise<void> {
  await database
    .updateTable('search_projection_state')
    .set({
      status: 'failed',
      last_failure_code: 'qdrant_projection_failed',
      updated_at: new Date(),
    })
    .where('fragment_id', '=', fragmentId)
    .where('projection_revision', '=', expectedProjectionRevision)
    .execute();
}

async function fragmentTagsFor(
  database: Database,
  fragmentId: string,
): Promise<string[]> {
  const rows = await database
    .selectFrom('fragment_tags')
    .innerJoin('tags', 'tags.id', 'fragment_tags.tag_id')
    .select('tags.name')
    .where('fragment_tags.fragment_id', '=', fragmentId)
    .orderBy('tags.name')
    .execute();
  return rows.map(({ name }) => name);
}

async function videoTagsFor(
  database: Database,
  videoId: string,
): Promise<string[]> {
  const rows = await database
    .selectFrom('video_tags')
    .innerJoin('tags', 'tags.id', 'video_tags.tag_id')
    .select('tags.name')
    .where('video_tags.video_id', '=', videoId)
    .orderBy('tags.name')
    .execute();
  return rows.map(({ name }) => name);
}
