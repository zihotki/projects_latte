import { sql } from 'kysely';
import {
  closeCatalogDatabase,
  createCatalogDatabase,
} from './catalog/database.js';
import { getServerConfig } from './config.js';
import { shutdownTelemetry } from './observability/telemetry.js';

const config = getServerConfig();
const database = createCatalogDatabase(config);
const workerId = `worker-${process.pid}`;
let stopping = false;
let heartbeatTimer: NodeJS.Timeout | undefined;

async function heartbeat(): Promise<void> {
  await sql`
    insert into worker_heartbeats (worker_id, last_seen_at)
    values (${workerId}, now())
    on conflict (worker_id)
    do update set last_seen_at = excluded.last_seen_at
  `.execute(database);
}

async function shutdown(): Promise<void> {
  if (stopping) {
    return;
  }
  stopping = true;
  if (heartbeatTimer !== undefined) {
    clearInterval(heartbeatTimer);
  }
  try {
    await closeCatalogDatabase(database);
    await shutdownTelemetry();
    process.exitCode = 0;
  } catch (error) {
    console.error('Worker shutdown failed', error);
    process.exitCode = 1;
  }
}

process.once('SIGINT', () => void shutdown());
process.once('SIGTERM', () => void shutdown());

try {
  await heartbeat();
  console.info('Phase 4 worker ready; no Slice 1 job handlers are registered');
  heartbeatTimer = setInterval(() => {
    void heartbeat().catch((error) => {
      console.error('Worker heartbeat failed', error);
    });
  }, 5_000);
} catch (error) {
  console.error('Worker startup failed', error);
  await closeCatalogDatabase(database).catch(() => undefined);
  await shutdownTelemetry().catch(() => undefined);
  process.exitCode = 1;
}
