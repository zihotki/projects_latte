import { createApp } from './app.js';
import { getServerConfig } from './config.js';

const app = createApp();
const config = getServerConfig();

const shutdown = async (): Promise<void> => {
  await app.close();
  process.exitCode = 0;
};

process.once('SIGINT', () => void shutdown());
process.once('SIGTERM', () => void shutdown());

try {
  await app.listen(config);
} catch (error) {
  app.log.error(error);
  process.exitCode = 1;
}
