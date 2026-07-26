import { jetstream, type JsMsg } from '@nats-io/jetstream';
import type { Kysely } from 'kysely';
import type { CatalogDatabase } from '../../catalog/database-types.js';
import type {
  FragmentChangedEvent,
  FragmentDeletedEvent,
} from '../contracts.js';
import {
  pipelineStream,
  qdrantProjectorConsumer,
  type JetStreamRuntime,
} from '../jetstream.js';
import type { FragmentProjectionStore } from '../../search/qdrant-client.js';

const decoder = new TextDecoder();

type QdrantEvent = FragmentChangedEvent | FragmentDeletedEvent;

export async function runQdrantProjector(input: {
  database: Kysely<CatalogDatabase>;
  runtime: JetStreamRuntime;
  store: FragmentProjectionStore;
  stopping: () => boolean;
}): Promise<void> {
  const client = jetstream(input.runtime.connection);
  const consumer = await client.consumers.get(
    pipelineStream,
    qdrantProjectorConsumer,
  );
  while (!input.stopping()) {
    const message = await consumer.next({ expires: 1_000 });
    if (message === null) continue;
    await processQdrantMessage(input.database, input.store, message);
  }
}

export async function processQdrantMessage(
  database: Kysely<CatalogDatabase>,
  store: FragmentProjectionStore,
  message: JsMsg,
): Promise<void> {
  const event = parseQdrantEvent(message);
  const state = await database
    .selectFrom('search_projection_state')
    .select('last_source_position')
    .where('fragment_id', '=', event.aggregate.id)
    .executeTakeFirst();
  if (
    state?.last_source_position !== null &&
    state !== undefined &&
    Number(state.last_source_position) >= event.position
  ) {
    message.ack();
    return;
  }

  if (event.type === 'fragment.deleted.v1') {
    await store.delete(event.payload.fragmentId);
  } else {
    await store.upsert({
      id: event.payload.fragmentId,
      payload: {
        projection_version: event.payload.projectionVersion,
        projection_revision: event.aggregate.revision,
        fragment_id: event.payload.fragmentId,
        video_id: event.payload.videoId,
        fragment_revision: event.payload.fragmentRevision,
        start_us: event.payload.startUs,
        end_us: event.payload.endUs,
        fragment_title: event.payload.fragmentTitle,
        fragment_description: event.payload.fragmentDescription,
        fragment_tags: event.payload.fragmentTags,
        source_title: event.payload.sourceTitle,
        source_description: event.payload.sourceDescription,
        source_tags: event.payload.sourceTags,
        collection_ids: [],
      },
    });
  }

  const stateUpdate = {
    projection_revision: event.aggregate.revision,
    projection_version: 1,
    status: 'ready' as const,
    last_failure_code: null,
    last_event_id: event.eventId,
    last_aggregate_revision: event.aggregate.revision,
    last_source_position: event.position,
    updated_at: new Date(),
  };
  if (event.type === 'fragment.deleted.v1') {
    // The fragment may already have reached final purge. Its state row is then
    // gone by design, but the idempotent Qdrant delete must still be acknowledged.
    await database
      .updateTable('search_projection_state')
      .set(stateUpdate)
      .where('fragment_id', '=', event.aggregate.id)
      .execute();
  } else {
    await database
      .insertInto('search_projection_state')
      .values({ fragment_id: event.aggregate.id, ...stateUpdate })
      .onConflict((conflict) =>
        conflict.column('fragment_id').doUpdateSet(stateUpdate),
      )
      .execute();
  }
  await message.ackAck();
}

function parseQdrantEvent(message: JsMsg): QdrantEvent {
  const event = JSON.parse(decoder.decode(message.data)) as unknown;
  if (
    !isRecord(event) ||
    typeof event.type !== 'string' ||
    !isRecord(event.aggregate) ||
    typeof event.aggregate.id !== 'string' ||
    typeof event.aggregate.revision !== 'number' ||
    typeof event.position !== 'number' ||
    typeof event.eventId !== 'string' ||
    !isRecord(event.payload)
  ) {
    throw new Error('Invalid Qdrant event payload');
  }
  if (event.type === 'fragment.deleted.v1') {
    if (typeof event.payload.fragmentId !== 'string')
      throw new Error('Invalid fragment deletion event');
    return event as unknown as FragmentDeletedEvent;
  }
  if (event.type === 'fragment.changed.v1') {
    if (
      typeof event.payload.fragmentId !== 'string' ||
      typeof event.payload.videoId !== 'string' ||
      typeof event.payload.fragmentRevision !== 'number'
    ) {
      throw new Error('Invalid fragment projection event');
    }
    return event as unknown as FragmentChangedEvent;
  }
  throw new Error(`Unsupported Qdrant event type: ${event.type}`);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
