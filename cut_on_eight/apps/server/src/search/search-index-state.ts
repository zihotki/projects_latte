import { sql, type Kysely } from 'kysely';
import type { CatalogDatabase } from '../catalog/database-types.js';

export interface AppliedSearchIndexState {
  readonly profileId: string;
  readonly fragmentId: string;
  readonly collectionName: string;
  readonly fragmentRevision: number;
  readonly textHash: string;
  readonly eventId: string;
  readonly sourcePosition: number;
}

export interface PendingSearchIndexState {
  readonly profileId: string;
  readonly fragmentId: string;
  readonly collectionName: string;
  readonly fragmentRevision: number;
  readonly textHash: string;
  readonly sourcePosition: number;
}

export interface FailedSearchIndexState {
  readonly profileId: string;
  readonly fragmentId: string;
  readonly collectionName: string;
  readonly fragmentRevision: number;
  readonly eventId: string;
  readonly sourcePosition: number;
  readonly failureCode: string;
}

export interface SearchIndexStateStore {
  isAlreadyApplied(
    profileId: string,
    fragmentId: string,
    position: number,
  ): Promise<boolean>;
  recordApplied(input: AppliedSearchIndexState): Promise<void>;
  recordPending(input: PendingSearchIndexState): Promise<void>;
  recordFailed(input: FailedSearchIndexState): Promise<void>;
}

export function createSearchIndexStateStore(
  database: Kysely<CatalogDatabase>,
): SearchIndexStateStore {
  return {
    isAlreadyApplied: (profileId, fragmentId, position) =>
      isAlreadyApplied(database, profileId, fragmentId, position),
    recordApplied: (input) => recordApplied(database, input),
    recordPending: (input) => recordPending(database, input),
    recordFailed: (input) => recordFailed(database, input),
  };
}

async function recordFailed(
  database: Kysely<CatalogDatabase>,
  input: FailedSearchIndexState,
): Promise<void> {
  await database
    .insertInto('semantic_search_index_state')
    .values({
      profile_id: input.profileId,
      fragment_id: input.fragmentId,
      collection_name: input.collectionName,
      fragment_revision: input.fragmentRevision,
      text_hash: '0'.repeat(64),
      status: 'failed',
      last_event_id: input.eventId,
      last_source_position: null,
      failure_code: input.failureCode,
      updated_at: new Date(),
    })
    .onConflict((conflict) =>
      conflict
        .columns(['profile_id', 'fragment_id'])
        .doUpdateSet({
          status: 'failed',
          failure_code: input.failureCode,
          updated_at: new Date(),
        })
        .where(
          sql<boolean>`semantic_search_index_state.last_source_position is null or semantic_search_index_state.last_source_position < ${input.sourcePosition}`,
        ),
    )
    .execute();
}

export async function isAlreadyApplied(
  database: Kysely<CatalogDatabase>,
  profileId: string,
  fragmentId: string,
  position: number,
): Promise<boolean> {
  const state = await database
    .selectFrom('semantic_search_index_state')
    .select('last_source_position')
    .where('profile_id', '=', profileId)
    .where('fragment_id', '=', fragmentId)
    .executeTakeFirst();
  return (
    state?.last_source_position !== null &&
    state !== undefined &&
    BigInt(state.last_source_position) >= BigInt(position)
  );
}

export async function recordApplied(
  database: Kysely<CatalogDatabase>,
  input: AppliedSearchIndexState,
): Promise<void> {
  await database
    .insertInto('semantic_search_index_state')
    .values({
      profile_id: input.profileId,
      fragment_id: input.fragmentId,
      collection_name: input.collectionName,
      fragment_revision: input.fragmentRevision,
      text_hash: input.textHash,
      status: 'ready',
      last_event_id: input.eventId,
      last_source_position: input.sourcePosition,
      failure_code: null,
      updated_at: new Date(),
    })
    .onConflict((conflict) =>
      conflict
        .columns(['profile_id', 'fragment_id'])
        .doUpdateSet({
          collection_name: input.collectionName,
          fragment_revision: input.fragmentRevision,
          text_hash: input.textHash,
          status: 'ready',
          last_event_id: input.eventId,
          last_source_position: input.sourcePosition,
          failure_code: null,
          updated_at: new Date(),
        })
        .where(
          sql<boolean>`semantic_search_index_state.last_source_position is null or semantic_search_index_state.last_source_position < excluded.last_source_position`,
        ),
    )
    .execute();
}

async function recordPending(
  database: Kysely<CatalogDatabase>,
  input: PendingSearchIndexState,
): Promise<void> {
  await database
    .insertInto('semantic_search_index_state')
    .values({
      profile_id: input.profileId,
      fragment_id: input.fragmentId,
      collection_name: input.collectionName,
      fragment_revision: input.fragmentRevision,
      text_hash: input.textHash,
      status: 'pending',
      last_event_id: null,
      last_source_position: null,
      failure_code: null,
      updated_at: new Date(),
    })
    .onConflict((conflict) =>
      conflict
        .columns(['profile_id', 'fragment_id'])
        .doUpdateSet({
          collection_name: input.collectionName,
          fragment_revision: input.fragmentRevision,
          text_hash: input.textHash,
          status: 'pending',
          failure_code: null,
          updated_at: new Date(),
        })
        .where(
          sql<boolean>`semantic_search_index_state.last_source_position is null or semantic_search_index_state.last_source_position < ${input.sourcePosition}`,
        ),
    )
    .execute();
}
