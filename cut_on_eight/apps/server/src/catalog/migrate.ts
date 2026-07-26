import { getServerConfig } from '../config.js';
import { createBoss, createPhase4Queues } from '../jobs/boss.js';
import { closeCatalogDatabase, createCatalogDatabase } from './database.js';
import { migrateCatalog } from './migrations/index.js';

const config = getServerConfig();
const database = createCatalogDatabase(config);
const boss = createBoss(config);

try {
  await migrateCatalog(database);
  await boss.start();
  await createPhase4Queues(boss);
} finally {
  await boss.stop({ graceful: true }).catch(() => undefined);
  await closeCatalogDatabase(database);
}
