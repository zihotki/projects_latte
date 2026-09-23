import {
  closeCatalogDatabase,
  createCatalogDatabase,
} from '../catalog/database.js';
import { getServerConfig } from '../config.js';
import {
  createJetStreamManager,
  createJetStreamRuntime,
} from '../events/jetstream.js';
import { ensurePipelineTopology } from '../events/topology.js';
import { shutdownTelemetry } from '../observability/telemetry.js';
import {
  activeSearchAlias,
  collectionForProfile,
  createHybridSearchStore,
} from './hybrid-qdrant-store.js';
import { createEmbeddingClient } from './embedding-client.js';
import { runSearchIndexer } from './search-indexer.js';
import { createSearchIndexStateStore } from './search-index-state.js';

const config = getServerConfig();
const database = createCatalogDatabase(config);
const runtime = await createJetStreamRuntime(config);
const topology = await createJetStreamManager(config);
const store = createHybridSearchStore(config);
const embeddings = createEmbeddingClient(config.embeddingProfile);
const indexState = createSearchIndexStateStore(database);
const defaultCollection = collectionForProfile(config.embeddingProfile);
let stopping = false;

async function shutdown(): Promise<void> {
  if (stopping) return;
  stopping = true;
  await topology.close().catch(() => undefined);
  await runtime.close().catch(() => undefined);
  await closeCatalogDatabase(database).catch(() => undefined);
  await shutdownTelemetry().catch(() => undefined);
}

process.once('SIGINT', () => void shutdown());
process.once('SIGTERM', () => void shutdown());

try {
  await ensurePipelineTopology(topology.manager);
  await runSearchIndexer({
    database,
    runtime,
    profile: config.embeddingProfile,
    collection: defaultCollection,
    async resolveCollection() {
      const activeTarget = await store.aliasTarget(activeSearchAlias);
      return activeTarget === null
        ? defaultCollection
        : { ...defaultCollection, name: activeTarget };
    },
    store,
    embeddings,
    indexState,
    stopping: () => stopping,
  });
} catch (error) {
  console.error(error);
  process.exitCode = 1;
} finally {
  await shutdown();
}
