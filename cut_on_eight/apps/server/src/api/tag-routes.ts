import {
  createTagRequestSchema,
  tagListSchema,
  tagSchema,
} from '@cut-on-eight/api-contracts';
import type { FastifyInstance } from 'fastify';
import type { ApiRuntime } from '../runtime.js';

export function registerCatalogTagRoutes(
  app: FastifyInstance,
  runtime: ApiRuntime,
): void {
  app.get('/api/tags', async () =>
    tagListSchema.parse(await runtime.fragments.listTags()),
  );
  app.post<{ Body: unknown }>('/api/tags', async (request, reply) => {
    const { name } = createTagRequestSchema.parse(request.body);
    return reply
      .code(201)
      .send(tagSchema.parse(await runtime.fragments.createTag(name)));
  });
}
