import type { Job, PgBoss } from 'pg-boss';
import type { Kysely } from 'kysely';
import type { BlobStore, LocalMediaFiles } from '../blobs/blob-store.js';
import type { CatalogDatabase } from '../catalog/database-types.js';
import { jobNames } from './job-contracts.js';
import { inJobSpan, type JobEnvelope } from './job-envelope.js';
import {
  createInspectVideoProcessor,
  type InspectVideoJob,
} from './processors/inspect-video.js';
import {
  createGeneratePreviewProcessor,
  type PreviewJob,
} from './processors/generate-preview.js';
import { createPurgeFragmentProcessor } from './processors/purge-fragment.js';
import { createDeleteVideoProcessor } from './processors/delete-video.js';
import { createDeleteAssetProcessor } from './processors/delete-asset.js';
import type { DeleteAssetJob } from './processors/asset-deletion.js';

export async function registerWorkerHandlers(input: {
  database: Kysely<CatalogDatabase>;
  boss: PgBoss;
  blobs: BlobStore & LocalMediaFiles;
}): Promise<void> {
  const inspect = createInspectVideoProcessor(input.database, input.blobs);
  const preview = createGeneratePreviewProcessor(input.database, input.blobs);
  const purge = createPurgeFragmentProcessor(input.database, input.boss);
  const deleteVideo = createDeleteVideoProcessor(input.database, input.blobs);
  const deleteAsset = createDeleteAssetProcessor(input.database, input.blobs);

  await input.boss.work<JobEnvelope<InspectVideoJob>>(
    jobNames.inspectVideo,
    { batchSize: 1 },
    async (jobs) => runBatch(jobNames.inspectVideo, jobs, inspect),
  );
  await input.boss.work<JobEnvelope<PreviewJob>>(
    jobNames.generateFragmentPreview,
    { batchSize: 2 },
    async (jobs) => runBatch(jobNames.generateFragmentPreview, jobs, preview),
  );
  await input.boss.work<JobEnvelope<{ fragmentId: string }>>(
    jobNames.purgeFragment,
    { batchSize: 4 },
    async (jobs) => runBatch(jobNames.purgeFragment, jobs, purge),
  );
  await input.boss.work<
    JobEnvelope<{ videoId: string; expectedRevision: number }>
  >(jobNames.deleteVideo, { batchSize: 1 }, async (jobs) =>
    runBatch(jobNames.deleteVideo, jobs, deleteVideo),
  );
  await input.boss.work<JobEnvelope<DeleteAssetJob>>(
    jobNames.deleteAsset,
    { batchSize: 2 },
    async (jobs) => runBatch(jobNames.deleteAsset, jobs, deleteAsset),
  );
}

async function runBatch<T>(
  name: string,
  jobs: Job<JobEnvelope<T>>[],
  operation: (payload: T) => Promise<void>,
): Promise<void> {
  await Promise.all(
    jobs.map((job) => inJobSpan(name, job, (payload) => operation(payload))),
  );
}
