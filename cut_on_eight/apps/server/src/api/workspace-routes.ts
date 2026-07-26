import { workspaceSchema } from '@cut-on-eight/api-contracts';
import type { FastifyInstance } from 'fastify';
import type { ApiRuntime } from '../runtime.js';

export function registerWorkspaceCatalogRoutes(
  app: FastifyInstance,
  runtime: ApiRuntime,
): void {
  app.get('/api/workspace', async () =>
    workspaceSchema.parse(await runtime.workspace.snapshot()),
  );
}
