import { processingSnapshotSchema } from '@cut-on-eight/api-contracts';
import type { FastifyInstance } from 'fastify';
import type { ApiRuntime } from '../runtime.js';
import { ProcessingService } from '../processing/processing-service.js';

export function registerProcessingRoutes(
  app: FastifyInstance,
  runtime: ApiRuntime,
): void {
  const processing = new ProcessingService(runtime.db);
  app.get('/api/processing', async () =>
    processingSnapshotSchema.parse(await processing.snapshot()),
  );
}
