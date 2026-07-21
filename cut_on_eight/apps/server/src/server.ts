import { getServerConfig } from './config.js';
import { createApp } from './app.js';

const config = getServerConfig();
const app = createApp({ config });

const shutdown = async (): Promise<void> => {
  await app.close();
  process.exitCode = 0;
};

process.once('SIGINT', () => void shutdown());
process.once('SIGTERM', () => void shutdown());

try {
  await app.recover();
  await app.listen({ host: config.host, port: config.port });
} catch (error) {
  app.log.error(error);
  process.exitCode = 1;
}
