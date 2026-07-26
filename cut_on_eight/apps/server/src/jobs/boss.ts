import { PgBoss, type UpdateQueueOptions } from 'pg-boss';
import type { ServerConfig } from '../config.js';
import { jobNames } from './job-contracts.js';

export function createBoss(config: Pick<ServerConfig, 'databaseUrl'>): PgBoss {
  return new PgBoss({
    connectionString: config.databaseUrl,
    schema: 'pgboss',
  });
}

type QueueAdministrator = Pick<PgBoss, 'createQueue' | 'updateQueue'>;

const phase4QueueOptions = {
  retryLimit: 5,
  retryDelay: 2,
  retryBackoff: true,
} satisfies UpdateQueueOptions;

export async function createPhase4Queues(
  boss: QueueAdministrator,
): Promise<void> {
  await Promise.all(
    Object.values(jobNames).map(async (name) => {
      await boss.createQueue(name, phase4QueueOptions);
      await boss.updateQueue(name, phase4QueueOptions);
    }),
  );
}
