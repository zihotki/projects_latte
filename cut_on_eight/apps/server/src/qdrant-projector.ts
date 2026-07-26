import {
  closeCatalogDatabase,
  createCatalogDatabase,
} from './catalog/database.js';
import { getServerConfig } from './config.js';
import { runQdrantProjector } from './events/consumers/qdrant-projector.js';
import {
  createJetStreamManager,
  createJetStreamRuntime,
} from './events/jetstream.js';
import { ensurePipelineTopology } from './events/topology.js';
import { createFragmentProjectionStore } from './search/qdrant-client.js';

const config = getServerConfig();
const database = createCatalogDatabase(config);
const runtime = await createJetStreamRuntime(config);
const topology = await createJetStreamManager(config);
const store = createFragmentProjectionStore(config);
let stopping = false;

process.once('SIGINT', () => {
  stopping = true;
});
process.once('SIGTERM', () => {
  stopping = true;
});

try {
  await ensurePipelineTopology(topology.manager);
  await store.ensureCollection();
  await runQdrantProjector({
    database,
    runtime,
    store,
    stopping: () => stopping,
  });
} finally {
  await topology.close().catch(() => undefined);
  await runtime.close().catch(() => undefined);
  await closeCatalogDatabase(database).catch(() => undefined);
}
