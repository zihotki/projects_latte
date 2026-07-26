import {
  closeCatalogDatabase,
  createCatalogDatabase,
} from '../catalog/database.js';
import { getServerConfig } from '../config.js';
import { rebuildFragmentProjection } from './rebuild.js';
import { createFragmentProjectionStore } from './qdrant-client.js';

const config = getServerConfig();
const database = createCatalogDatabase(config);

try {
  const count = await rebuildFragmentProjection(
    database,
    createFragmentProjectionStore(config),
  );
  console.info(`Rebuilt ${count} Qdrant fragment projections.`);
} finally {
  await closeCatalogDatabase(database);
}
