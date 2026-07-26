import { getServerConfig } from './config.js';
import { createApp } from './app.js';
import { createHealthProbes } from './api/health-routes.js';
import { shutdownTelemetry } from './observability/telemetry.js';
import { createRuntime } from './runtime.js';

const config = getServerConfig();
const runtime = await createRuntime(config);
const app = createApp({
  config,
  runtime,
  healthProbes: createHealthProbes(runtime.db, config),
});
let shuttingDown = false;

const shutdown = async (): Promise<void> => {
  if (shuttingDown) {
    return;
  }
  shuttingDown = true;
  try {
    await app.close();
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
  await runtime.close().catch(() => undefined);
  await shutdownTelemetry().catch(() => undefined);
  process.exitCode = 1;
}
