import {
  closeCatalogDatabase,
  createCatalogDatabase,
} from '../catalog/database.js';
import { getServerConfig } from '../config.js';
import { createJetStreamRuntime } from './jetstream.js';
import { ensurePipelineTopology } from './topology.js';
import { createJetStreamManager } from './jetstream.js';
import { OutboxRelay } from './outbox-relay.js';

const config = getServerConfig();
const database = createCatalogDatabase(config);
const runtime = await createJetStreamRuntime(config);
const topology = await createJetStreamManager(config);
let stopping = false;

process.once('SIGINT', () => {
  stopping = true;
});
process.once('SIGTERM', () => {
  stopping = true;
});

try {
  await ensurePipelineTopology(topology.manager);
  const relay = new OutboxRelay(database, runtime);
  while (!stopping) {
    const published = await relay.publishAvailable();
    if (published === 0)
      await new Promise<void>((resolve) => setTimeout(resolve, 250));
  }
} finally {
  await topology.close().catch(() => undefined);
  await runtime.close().catch(() => undefined);
  await closeCatalogDatabase(database).catch(() => undefined);
}
