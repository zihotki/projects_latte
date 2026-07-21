import type { FastifyInstance } from 'fastify';
import type { AppServices } from '../services.js';
import { parseProjectId } from './route-params.js';

export function registerWorkspaceRoutes(
  app: FastifyInstance,
  services: AppServices,
): void {
  app.get('/api/workspace', () => services.getWorkspace());

  app.post('/api/imports/select', () => services.selectImport());

  app.post('/api/projects/:id/open', (request) => {
    const id = parseProjectId(request.params, 'id');
    return services.openProject(id);
  });

  app.post('/api/projects/:id/activate', (request) => {
    const id = parseProjectId(request.params, 'id');
    return services.activateProject(id);
  });
}
