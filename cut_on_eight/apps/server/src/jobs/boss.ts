import { PgBoss } from 'pg-boss';
import type { ServerConfig } from '../config.js';
import { jobNames } from './job-contracts.js';

export function createBoss(config: Pick<ServerConfig, 'databaseUrl'>): PgBoss {
  return new PgBoss({
    connectionString: config.databaseUrl,
    schema: 'pgboss',
  });
}

export async function createPhase4Queues(boss: PgBoss): Promise<void> {
  await Promise.all(
    Object.values(jobNames).map((name) =>
      boss.createQueue(name, {
        retryLimit: 5,
        retryDelay: 2,
        retryBackoff: true,
      }),
    ),
  );
}
