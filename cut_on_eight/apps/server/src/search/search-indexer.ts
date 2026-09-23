import { jetstream, type JsMsg } from '@nats-io/jetstream';
import type { Kysely } from 'kysely';
import type { CatalogDatabase } from '../catalog/database-types.js';
import type { EmbeddingProfile } from '../config.js';
import type {
  FragmentChangedEvent,
  FragmentDeletedEvent,
} from '../events/contracts.js';
import {
  pipelineStream,
  searchIndexerConsumer,
  type JetStreamRuntime,
} from '../events/jetstream.js';
import { searchIndexerMaxDeliveries } from '../events/topology.js';
import type { EmbeddingClient } from './embedding-client.js';
import {
  buildSearchDocument,
  loadSearchDocument,
  type CurrentFragmentSearchDocument,
} from './search-document.js';
import {
  activeSearchAlias,
  type HybridSearchStore,
  type SearchCollection,
} from './hybrid-qdrant-store.js';
import type { SearchIndexStateStore } from './search-index-state.js';

const decoder = new TextDecoder();

type SearchIndexEvent = FragmentChangedEvent | FragmentDeletedEvent;

export interface SearchIndexerDependencies {
  readonly database: Kysely<CatalogDatabase>;
  readonly runtime: JetStreamRuntime;
  readonly profile: EmbeddingProfile;
  readonly collection: SearchCollection;
  /** Resolves the write target for each delivery so an alias cutover takes
   * effect without restarting the durable consumer. */
  readonly resolveCollection?: () => Promise<SearchCollection>;
  readonly store: HybridSearchStore;
  readonly embeddings: EmbeddingClient;
  readonly indexState: SearchIndexStateStore;
  readonly loadDocument?: (
    database: Kysely<CatalogDatabase>,
    fragmentId: string,
  ) => Promise<CurrentFragmentSearchDocument | null>;
}

export async function runSearchIndexer(
  input: SearchIndexerDependencies & { readonly stopping: () => boolean },
): Promise<void> {
  await input.store.ensureCollection(input.collection);
  await ensureActiveSearchAlias(input.store, input.collection);
  const consumer = await jetstream(input.runtime.connection).consumers.get(
    pipelineStream,
    searchIndexerConsumer,
  );
  while (!input.stopping()) {
    const message = await consumer.next({ expires: 1_000 });
    if (message === null) continue;
    try {
      await processSearchIndexMessage(input, message);
    } catch (error) {
      console.error('Search event could not be indexed', error);
      await handleSearchIndexFailure(input, message);
    }
  }
}

export async function handleSearchIndexFailure(
  input: SearchIndexerDependencies,
  message: JsMsg,
): Promise<void> {
  if (message.info.deliveryCount < searchIndexerMaxDeliveries) {
    message.nak(5_000);
    return;
  }
  let event: SearchIndexEvent;
  try {
    event = parseSearchIndexEvent(message);
  } catch {
    message.term('invalid_search_event');
    return;
  }
  try {
    const collection = await resolveCollection(input);
    await input.indexState.recordFailed({
      profileId: input.profile.id,
      fragmentId: event.aggregate.id,
      collectionName: collection.name,
      fragmentRevision: event.aggregate.revision,
      eventId: event.eventId,
      sourcePosition: event.position,
      failureCode: 'indexing_failed',
    });
    message.term('indexing_failed');
  } catch (error) {
    console.error('Could not record terminal search failure', error);
    message.nak(30_000);
  }
}

export async function ensureActiveSearchAlias(
  store: HybridSearchStore,
  collection: SearchCollection,
): Promise<void> {
  if ((await store.aliasTarget(activeSearchAlias)) === null) {
    await store.setAlias(activeSearchAlias, collection.name);
  }
}

export async function processSearchIndexMessage(
  dependencies: SearchIndexerDependencies,
  message: JsMsg,
): Promise<void> {
  const event = parseSearchIndexEvent(message);
  const fragmentId = event.aggregate.id;
  const collection = await resolveCollection(dependencies);
  // A rebuild can move the active alias while this process is running. Ensure
  // the resolved target in this process before an upsert checks its local
  // collection-ready cache.
  await dependencies.store.ensureCollection(collection);
  if (
    await dependencies.indexState.isAlreadyApplied(
      dependencies.profile.id,
      fragmentId,
      event.position,
    )
  ) {
    await message.ackAck();
    return;
  }

  const loaded =
    event.type === 'fragment.deleted.v1'
      ? null
      : await (dependencies.loadDocument ?? loadSearchDocument)(
          dependencies.database,
          fragmentId,
        );
  if (loaded === null) {
    await dependencies.store.delete(collection.name, fragmentId);
    await dependencies.indexState.recordApplied({
      profileId: dependencies.profile.id,
      fragmentId,
      collectionName: collection.name,
      fragmentRevision: event.aggregate.revision,
      textHash: deletedDocumentHash(),
      eventId: event.eventId,
      sourcePosition: event.position,
    });
    await message.ackAck();
    return;
  }

  await dependencies.indexState.recordPending({
    profileId: dependencies.profile.id,
    fragmentId: loaded.fragmentId,
    collectionName: collection.name,
    fragmentRevision: loaded.fragmentRevision,
    textHash: loaded.document.hash,
    sourcePosition: event.position,
  });
  const denseVector = dependencies.embeddings.available()
    ? await embedDocument(dependencies.embeddings, loaded.document.text)
    : undefined;
  await dependencies.store.upsert({
    collection: collection.name,
    fragmentId: loaded.fragmentId,
    searchText: loaded.document.text,
    denseVector,
    payload: {
      fragment_id: loaded.fragmentId,
      video_id: loaded.videoId,
      fragment_revision: loaded.fragmentRevision,
      start_us: loaded.startUs,
      end_us: loaded.endUs,
      fragment_title: loaded.title,
      fragment_description: loaded.description,
      fragment_tag_ids: loaded.fragmentTagIds,
      fragment_tags: loaded.fragmentTags.map(({ name }) => name),
      source_title: loaded.sourceTitle,
      source_description: loaded.sourceDescription,
      source_tag_ids: loaded.sourceTagIds,
      source_tags: loaded.sourceTags.map(({ name }) => name),
      collection_ids: loaded.collectionIds,
    },
  });
  await dependencies.indexState.recordApplied({
    profileId: dependencies.profile.id,
    fragmentId: loaded.fragmentId,
    collectionName: collection.name,
    fragmentRevision: loaded.fragmentRevision,
    textHash: loaded.document.hash,
    eventId: event.eventId,
    sourcePosition: event.position,
  });
  await message.ackAck();
}

async function resolveCollection(
  dependencies: SearchIndexerDependencies,
): Promise<SearchCollection> {
  return dependencies.resolveCollection === undefined
    ? dependencies.collection
    : dependencies.resolveCollection();
}

async function embedDocument(
  embeddings: EmbeddingClient,
  text: string,
): Promise<readonly number[]> {
  const vectors = await embeddings.embed([text]);
  const vector = vectors[0];
  if (vector === undefined) {
    throw new Error('Embedding response did not contain the requested vector.');
  }
  return vector;
}

function deletedDocumentHash(): string {
  return buildSearchDocument({
    fragmentTitle: null,
    fragmentDescription: null,
    fragmentTags: [],
    sourceTitle: null,
    sourceDescription: null,
    sourceTags: [],
  }).hash;
}

function parseSearchIndexEvent(message: JsMsg): SearchIndexEvent {
  const event = JSON.parse(decoder.decode(message.data)) as unknown;
  if (
    !isRecord(event) ||
    !isRecord(event.aggregate) ||
    !isRecord(event.payload) ||
    typeof event.eventId !== 'string' ||
    typeof event.position !== 'number' ||
    !Number.isSafeInteger(event.position) ||
    typeof event.type !== 'string' ||
    typeof event.aggregate.id !== 'string' ||
    typeof event.aggregate.revision !== 'number'
  ) {
    throw new Error('Invalid search-index event payload');
  }
  if (event.type === 'fragment.deleted.v1') {
    if (event.payload.fragmentId !== event.aggregate.id) {
      throw new Error('Invalid fragment deletion event');
    }
    return event as unknown as FragmentDeletedEvent;
  }
  if (event.type === 'fragment.changed.v1') {
    if (event.payload.fragmentId !== event.aggregate.id) {
      throw new Error('Invalid fragment change event');
    }
    return event as unknown as FragmentChangedEvent;
  }
  throw new Error(`Unsupported search-index event type: ${event.type}`);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
