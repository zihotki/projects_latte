import { v7 as uuidv7 } from 'uuid';
import { jetstream } from '@nats-io/jetstream';
import { sql, type SqlBool } from 'kysely';
import {
  closeCatalogDatabase,
  createCatalogDatabase,
} from '../catalog/database.js';
import { getServerConfig } from '../config.js';
import { createJetStreamManager, createJetStreamRuntime } from './jetstream.js';
import { ensurePipelineTopology } from './topology.js';

const config = getServerConfig();
const database = createCatalogDatabase(config);
const runtime = await createJetStreamRuntime(config);
const topology = await createJetStreamManager(config);
const replayId = uuidv7();
const stream = `CUT_ON_EIGHT_REPLAY_${replayId.replaceAll('-', '')}`;
const subjectRoot = `cut_on_eight.replay.${replayId}`;
const purpose =
  process.env.CUT_ON_EIGHT_REPLAY_PURPOSE ?? 'manual projection replay';

try {
  await ensurePipelineTopology(topology.manager);
  const bounds = await database
    .selectFrom('integration_events')
    .select((expression) => [
      expression.fn.min('position').as('first_position'),
      expression.fn.max('position').as('last_position'),
    ])
    .executeTakeFirstOrThrow();
  if (bounds.first_position === null || bounds.last_position === null) {
    console.info('No integration events are available for replay.');
  } else {
    await topology.manager.streams.add({
      name: stream,
      subjects: [`${subjectRoot}.>`],
      storage: 'file',
      retention: 'limits',
      max_age: 7 * 24 * 60 * 60 * 1_000_000_000,
      max_bytes: 1024 * 1024 * 1024,
    });
    await database
      .insertInto('event_replay_runs')
      .values({
        id: replayId,
        start_position: bounds.first_position,
        end_position: bounds.last_position,
        destination_stream: stream,
        purpose: purpose.slice(0, 120),
        status: 'running',
      })
      .execute();
    const publisher = jetstream(runtime.connection);
    let nextPosition = Number(bounds.first_position);
    while (true) {
      const events = await database
        .selectFrom('integration_events')
        .selectAll()
        .where(sql<SqlBool>`position >= ${nextPosition}`)
        .where(sql<SqlBool>`position <= ${bounds.last_position}`)
        .orderBy('position')
        .limit(100)
        .execute();
      if (events.length === 0) break;
      for (const event of events) {
        await publisher.publish(
          `${subjectRoot}.${event.event_type}`,
          new TextEncoder().encode(
            JSON.stringify({
              eventId: event.event_id,
              position: Number(event.position),
              type: event.event_type,
              schemaVersion: event.schema_version,
              aggregate: {
                type: event.aggregate_type,
                id: event.aggregate_id,
                revision: event.aggregate_revision,
              },
              occurredAt: event.occurred_at.toISOString(),
              correlationId: event.correlation_id,
              causationId: event.causation_id,
              payload: event.payload,
            }),
          ),
          { msgID: event.event_id },
        );
        nextPosition = Number(event.position) + 1;
      }
      await database
        .updateTable('event_replay_runs')
        .set({ published_through_position: nextPosition - 1 })
        .where('id', '=', replayId)
        .execute();
    }
    await database
      .updateTable('event_replay_runs')
      .set({ status: 'completed', completed_at: new Date() })
      .where('id', '=', replayId)
      .execute();
    console.info(`Replayed archive to ${stream} on ${subjectRoot}.>`);
  }
} catch (error) {
  await database
    .updateTable('event_replay_runs')
    .set({
      status: 'failed',
      last_error:
        error instanceof Error ? error.message.slice(0, 500) : 'Replay failed',
      completed_at: new Date(),
    })
    .where('id', '=', replayId)
    .execute()
    .catch(() => undefined);
  throw error;
} finally {
  await topology.close().catch(() => undefined);
  await runtime.close().catch(() => undefined);
  await closeCatalogDatabase(database).catch(() => undefined);
}
