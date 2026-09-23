import {
  closeCatalogDatabase,
  createCatalogDatabase,
} from '../catalog/database.js';
import { getServerConfig } from '../config.js';
import { createEmbeddingClient } from './embedding-client.js';
import { createHybridSearchStore } from './hybrid-qdrant-store.js';
import { rebuildSemanticSearch } from './rebuild-semantic-search.js';

const config = getServerConfig();
const requestedProfile = readProfile(process.argv.slice(2));
if (requestedProfile !== config.embeddingProfile.id) {
  throw new Error(
    `Configured embedding profile is ${config.embeddingProfile.id}; cannot rebuild ${requestedProfile}.`,
  );
}

const database = createCatalogDatabase(config);
try {
  const run = await rebuildSemanticSearch({
    database,
    profile: config.embeddingProfile,
    store: createHybridSearchStore(config),
    embeddings: createEmbeddingClient(config.embeddingProfile),
  });
  console.info(
    `Search rebuild ${run.id} is ready; ${run.targetCollection} now backs the active alias.`,
  );
} finally {
  await closeCatalogDatabase(database);
}

function readProfile(arguments_: readonly string[]): string {
  if (arguments_.length === 0) return config.embeddingProfile.id;
  if (arguments_.length === 2 && arguments_[0] === '--profile') {
    return arguments_[1] ?? config.embeddingProfile.id;
  }
  throw new Error('Usage: pnpm search:rebuild -- [--profile <profile-id>]');
}
