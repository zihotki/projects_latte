import {
  createTagRequestSchema,
  deletedFragmentSchema,
  fragmentMutationSchema,
} from '@cut-on-eight/contracts';
import type { FastifyInstance } from 'fastify';
import type { AppServices } from '../services.js';
import { parseProjectId } from './route-params.js';

export function registerFragmentRoutes(
  app: FastifyInstance,
  services: AppServices,
): void {
  app.get('/api/fragments', () => services.getFragments());
  app.get('/api/tags', () => services.getTags());

  app.post('/api/tags', (request) =>
    services.createTag(createTagRequestSchema.parse(request.body).name),
  );

  app.put('/api/projects/:projectId/fragments/:fragmentId', (request) =>
    services.updateFragment(
      parseProjectId(request.params, 'projectId'),
      parseProjectId(request.params, 'fragmentId'),
      fragmentMutationSchema.parse(request.body),
    ),
  );

  app.delete('/api/projects/:projectId/fragments/:fragmentId', (request) =>
    services.deleteFragment(
      parseProjectId(request.params, 'projectId'),
      parseProjectId(request.params, 'fragmentId'),
    ),
  );

  app.post(
    '/api/projects/:projectId/fragments/:fragmentId/restore',
    (request) =>
      services.restoreFragment(
        parseProjectId(request.params, 'projectId'),
        parseProjectId(request.params, 'fragmentId'),
        deletedFragmentSchema.parse(request.body),
      ),
  );
}
