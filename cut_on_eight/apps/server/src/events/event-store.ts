import { v7 as uuidv7 } from 'uuid';
import { type Kysely, type Transaction } from 'kysely';
import type { CatalogDatabase } from '../catalog/database-types.js';
import type { CatalogEvent, NewCatalogEvent } from './contracts.js';

type Database = Kysely<CatalogDatabase> | Transaction<CatalogDatabase>;

export type PublishedEvent = CatalogEvent & {
  readonly publication: {
    readonly attempts: number;
  };
};

export async function appendEvent(
  transaction: Transaction<CatalogDatabase>,
  event: NewCatalogEvent,
): Promise<CatalogEvent> {
  const eventId = uuidv7();
  const occurredAt = new Date();
  const inserted = await transaction
    .insertInto('integration_events')
    .values({
      event_id: eventId,
      event_type: event.type,
      schema_version: 1,
      aggregate_type: event.aggregate.type,
      aggregate_id: event.aggregate.id,
      aggregate_revision: event.aggregate.revision,
      occurred_at: occurredAt,
      correlation_id: event.correlationId,
      causation_id: event.causationId,
      payload: event.payload as unknown as Record<string, unknown>,
    })
    .returning('position')
    .executeTakeFirstOrThrow();
  await transaction
    .insertInto('event_publications')
    .values({
      event_id: eventId,
      destination: 'jetstream-primary',
      status: 'pending',
      attempts: 0,
    })
    .execute();
  return {
    ...event,
    eventId,
    position: Number(inserted.position),
    occurredAt: occurredAt.toISOString(),
  } as CatalogEvent;
}

export async function claimPublicationBatch(
  database: Kysely<CatalogDatabase>,
  now: Date,
  leaseUntil: Date,
  limit: number,
): Promise<PublishedEvent[]> {
  return database.transaction().execute(async (transaction) => {
    const rows = await transaction
      .selectFrom('event_publications')
      .innerJoin(
        'integration_events',
        'integration_events.event_id',
        'event_publications.event_id',
      )
      .select([
        'event_publications.event_id',
        'event_publications.attempts',
        'integration_events.position',
        'integration_events.event_type',
        'integration_events.schema_version',
        'integration_events.aggregate_type',
        'integration_events.aggregate_id',
        'integration_events.aggregate_revision',
        'integration_events.occurred_at',
        'integration_events.correlation_id',
        'integration_events.causation_id',
        'integration_events.payload',
      ])
      .where('event_publications.destination', '=', 'jetstream-primary')
      .where((expression) =>
        expression.or([
          expression.and([
            expression('event_publications.status', '=', 'pending'),
            expression('event_publications.available_at', '<=', now),
          ]),
          expression.and([
            expression('event_publications.status', '=', 'leased'),
            expression('event_publications.locked_until', '<=', now),
          ]),
        ]),
      )
      .orderBy('integration_events.position')
      .limit(limit)
      .forUpdate()
      .skipLocked()
      .execute();
    if (rows.length === 0) return [];
    await transaction
      .updateTable('event_publications')
      .set((expression) => ({
        status: 'leased',
        attempts: expression('attempts', '+', 1),
        locked_until: leaseUntil,
        last_error: null,
      }))
      .where(
        'event_id',
        'in',
        rows.map((row) => row.event_id),
      )
      .where('destination', '=', 'jetstream-primary')
      .execute();
    return rows.map((row) => ({
      eventId: row.event_id,
      position: Number(row.position),
      type: row.event_type,
      schemaVersion: row.schema_version as 1,
      aggregate: {
        type: row.aggregate_type as CatalogEvent['aggregate']['type'],
        id: row.aggregate_id,
        revision: row.aggregate_revision,
      },
      occurredAt: row.occurred_at.toISOString(),
      correlationId: row.correlation_id,
      causationId: row.causation_id,
      payload: row.payload,
      publication: { attempts: row.attempts + 1 },
    })) as unknown as PublishedEvent[];
  });
}

export async function markPublicationPublished(
  database: Database,
  eventId: string,
  stream: string,
  sequence: number,
): Promise<void> {
  await database
    .updateTable('event_publications')
    .set({
      status: 'published',
      locked_until: null,
      published_at: new Date(),
      broker_stream: stream,
      broker_sequence: sequence,
      last_error: null,
    })
    .where('event_id', '=', eventId)
    .where('destination', '=', 'jetstream-primary')
    .execute();
}

export async function releasePublication(
  database: Database,
  eventId: string,
  availableAt: Date,
  error: Error,
): Promise<void> {
  await database
    .updateTable('event_publications')
    .set({
      status: 'pending',
      locked_until: null,
      available_at: availableAt,
      last_error: error.message.slice(0, 500),
    })
    .where('event_id', '=', eventId)
    .where('destination', '=', 'jetstream-primary')
    .execute();
}
