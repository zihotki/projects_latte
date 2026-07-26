import { headers, type NatsConnection } from '@nats-io/nats-core';
import { jetstream, jetstreamManager } from '@nats-io/jetstream';
import { connect } from '@nats-io/transport-node';
import { context, propagation } from '@opentelemetry/api';
import type { ServerConfig } from '../config.js';
import type { CatalogEvent } from './contracts.js';
import type { PublishedEvent } from './event-store.js';

const encoder = new TextEncoder();

export const pipelineStream = 'CUT_ON_EIGHT_EVENTS';
export const qdrantProjectorConsumer = 'qdrant-projector-v1';
export const thumbnailGeneratorConsumer = 'thumbnail-generator-v1';

export interface JetStreamPublisher {
  publish(event: PublishedEvent): Promise<{
    stream: string;
    sequence: number;
  }>;
}

export interface JetStreamRuntime extends JetStreamPublisher {
  readonly connection: NatsConnection;
  close(): Promise<void>;
}

export async function createJetStreamRuntime(
  config: Pick<ServerConfig, 'natsUrl'>,
): Promise<JetStreamRuntime> {
  const connection = await connect({ servers: config.natsUrl });
  const client = jetstream(connection);
  return {
    connection,
    async publish(event) {
      const metadata = headers();
      metadata.set('Cut-On-Eight-Event-Id', event.eventId);
      metadata.set('Cut-On-Eight-Source-Position', String(event.position));
      metadata.set('Cut-On-Eight-Aggregate-Id', event.aggregate.id);
      metadata.set(
        'Cut-On-Eight-Aggregate-Revision',
        String(event.aggregate.revision),
      );
      if (event.correlationId !== null)
        metadata.set('Cut-On-Eight-Correlation-Id', event.correlationId);
      if (event.causationId !== null)
        metadata.set('Cut-On-Eight-Causation-Id', event.causationId);
      propagation.inject(context.active(), metadata, {
        set(carrier, key, value) {
          carrier.set(key, value);
        },
      });
      const acknowledgement = await client.publish(
        subjectForEvent(event),
        encoder.encode(JSON.stringify(event)),
        { headers: metadata, msgID: event.eventId },
      );
      return { stream: acknowledgement.stream, sequence: acknowledgement.seq };
    },
    async close() {
      await connection.drain();
    },
  };
}

export async function createJetStreamManager(
  config: Pick<ServerConfig, 'natsUrl'>,
) {
  const connection = await connect({ servers: config.natsUrl });
  return {
    connection,
    manager: await jetstreamManager(connection),
    async close() {
      await connection.drain();
    },
  };
}

export function subjectForEvent(event: Pick<CatalogEvent, 'type'>): string {
  return `cut_on_eight.${event.type}`;
}
