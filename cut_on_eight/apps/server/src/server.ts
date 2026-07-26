import { getServerConfig } from './config.js';
import { createApp } from './app.js';
import {
  closeCatalogDatabase,
  createCatalogDatabase,
} from './catalog/database.js';
import { createHealthProbes } from './api/health-routes.js';
import { shutdownTelemetry } from './observability/telemetry.js';

const config = getServerConfig();
const database = createCatalogDatabase(config);
const app = createApp({
  config,
  healthProbes: createHealthProbes(database, config),
});
let shuttingDown = false;

const shutdown = async (): Promise<void> => {
  if (shuttingDown) {
    return;
  }
  shuttingDown = true;
  try {
    await app.close();
    await closeCatalogDatabase(database);
    await shutdownTelemetry();
    process.exitCode = 0;
  } catch (error) {
    app.log.error(error);
    process.exitCode = 1;
  }
};

process.once('SIGINT', () => void shutdown());
process.once('SIGTERM', () => void shutdown());

try {
  await app.recover();
  await app.listen({ host: config.host, port: config.port });
} catch (error) {
  app.log.error(error);
  await closeCatalogDatabase(database).catch(() => undefined);
  await shutdownTelemetry().catch(() => undefined);
  process.exitCode = 1;
}
