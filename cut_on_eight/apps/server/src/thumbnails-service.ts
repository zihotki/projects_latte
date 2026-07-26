import {
  closeCatalogDatabase,
  createCatalogDatabase,
} from './catalog/database.js';
import { LocalBlobStore } from './blobs/local-blob-store.js';
import { getServerConfig } from './config.js';
import { runThumbnailGenerator } from './events/consumers/thumbnail-generator.js';
import {
  createJetStreamManager,
  createJetStreamRuntime,
} from './events/jetstream.js';
import { ensurePipelineTopology } from './events/topology.js';
import { FfmpegRunner } from './jobs/ffmpeg-runner.js';
import { shutdownTelemetry } from './observability/telemetry.js';
import { ThumbnailBundleStore } from './thumbnails/thumbnail-bundle-store.js';
import { VideoThumbnailGenerator } from './thumbnails/video-thumbnail-generator.js';
import { createThumbnailOrigin } from './thumbnails/thumbnail-origin.js';

const config = getServerConfig();
const database = createCatalogDatabase(config);
const runtime = await createJetStreamRuntime(config);
const topology = await createJetStreamManager(config);
const bundles = new ThumbnailBundleStore(config.thumbnailRoot);
const blobs = new LocalBlobStore(config.dataRoot);
const generator = new VideoThumbnailGenerator(new FfmpegRunner(), bundles);
const app = createThumbnailOrigin({ database, bundles });
let stopping = false;

async function shutdown(): Promise<void> {
  if (stopping) return;
  stopping = true;
  await app.close().catch(() => undefined);
  await topology.close().catch(() => undefined);
  await runtime.close().catch(() => undefined);
  await closeCatalogDatabase(database).catch(() => undefined);
  await shutdownTelemetry().catch(() => undefined);
}

process.once('SIGINT', () => void shutdown());
process.once('SIGTERM', () => void shutdown());

try {
  await ensurePipelineTopology(topology.manager);
  await app.listen({ host: config.host, port: config.thumbnailOriginPort });
  await runThumbnailGenerator({
    database,
    runtime,
    files: blobs,
    generator,
    bundles,
    stopping: () => stopping,
  });
} catch (error) {
  app.log.error(error);
  process.exitCode = 1;
} finally {
  await shutdown();
}
