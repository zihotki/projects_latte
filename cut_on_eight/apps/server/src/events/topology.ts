import { nanos } from '@nats-io/nats-core';
import {
  AckPolicy,
  DeliverPolicy,
  DiscardPolicy,
  RetentionPolicy,
  StorageType,
  type JetStreamManager,
} from '@nats-io/jetstream';
import {
  pipelineStream,
  searchIndexerConsumer,
  thumbnailGeneratorConsumer,
} from './jetstream.js';

export const searchIndexerMaxDeliveries = 10;

export async function ensurePipelineTopology(
  manager: JetStreamManager,
): Promise<void> {
  await ensureStream(manager);
  await ensureConsumer(manager, searchIndexerConsumer, {
    filter_subject: 'cut_on_eight.fragment.>',
    ack_wait: nanos(60_000),
    max_deliver: searchIndexerMaxDeliveries,
    max_ack_pending: 1,
    backoff: [
      nanos(5_000),
      nanos(30_000),
      nanos(300_000),
      nanos(1_800_000),
      nanos(7_200_000),
      nanos(21_600_000),
      nanos(43_200_000),
      nanos(86_400_000),
      nanos(172_800_000),
    ],
  });
  await ensureConsumer(manager, thumbnailGeneratorConsumer, {
    filter_subject: 'cut_on_eight.video.thumbnails.requested.v1',
    ack_wait: nanos(120_000),
    max_deliver: 5,
    max_ack_pending: 1,
    backoff: [
      nanos(5_000),
      nanos(30_000),
      nanos(300_000),
      nanos(3_600_000),
      nanos(21_600_000),
    ],
  });
}

async function ensureStream(manager: JetStreamManager): Promise<void> {
  try {
    await manager.streams.info(pipelineStream);
  } catch {
    await manager.streams.add({
      name: pipelineStream,
      subjects: ['cut_on_eight.>'],
      retention: RetentionPolicy.Limits,
      storage: StorageType.File,
      discard: DiscardPolicy.Old,
      max_age: nanos(30 * 24 * 60 * 60 * 1_000),
      max_bytes: 1024 * 1024 * 1024,
      duplicate_window: nanos(10 * 60 * 1_000),
    });
  }
}

async function ensureConsumer(
  manager: JetStreamManager,
  durableName: string,
  options: Record<string, unknown>,
): Promise<void> {
  try {
    await manager.consumers.info(pipelineStream, durableName);
  } catch {
    await manager.consumers.add(pipelineStream, {
      durable_name: durableName,
      ack_policy: AckPolicy.Explicit,
      deliver_policy: DeliverPolicy.All,
      ...options,
    });
  }
}
