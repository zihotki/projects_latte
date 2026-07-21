import { projectDocumentSchema } from '@cut-on-eight/contracts';
import type { FastifyInstance } from 'fastify';
import type { AppServices } from '../services.js';
import { parseProjectId } from './route-params.js';

export function registerProjectRoutes(
  app: FastifyInstance,
  services: AppServices,
): void {
  app.put('/api/projects/:id', (request) => {
    const id = parseProjectId(request.params, 'id');
    const project = projectDocumentSchema.parse(request.body);
    return services.saveProject(id, project);
  });

  app.post('/api/projects/:id/close', (request) => {
    const id = parseProjectId(request.params, 'id');
    const project = projectDocumentSchema.parse(request.body);
    return services.closeProject(id, project);
  });
}
