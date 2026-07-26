import type { Kysely } from 'kysely';
import type { CatalogDatabase } from '../catalog/database-types.js';
import {
  claimPublicationBatch,
  markPublicationPublished,
  releasePublication,
  type PublishedEvent,
} from './event-store.js';
import type { JetStreamPublisher } from './jetstream.js';

export class OutboxRelay {
  constructor(
    private readonly database: Kysely<CatalogDatabase>,
    private readonly publisher: JetStreamPublisher,
    private readonly now: () => Date = () => new Date(),
  ) {}

  async publishAvailable(limit = 32): Promise<number> {
    const startedAt = this.now();
    const events = await claimPublicationBatch(
      this.database,
      startedAt,
      new Date(startedAt.getTime() + 60_000),
      limit,
    );
    for (const event of events) await this.publish(event);
    return events.length;
  }

  private async publish(event: PublishedEvent): Promise<void> {
    try {
      const acknowledgement = await this.publisher.publish(event);
      await markPublicationPublished(
        this.database,
        event.eventId,
        acknowledgement.stream,
        acknowledgement.sequence,
      );
    } catch (error) {
      const message = error instanceof Error ? error : new Error(String(error));
      const delay = Math.min(
        60_000,
        1_000 * 2 ** Math.min(event.publication.attempts, 6),
      );
      await releasePublication(
        this.database,
        event.eventId,
        new Date(this.now().getTime() + delay),
        message,
      );
    }
  }
}
