import { thumbnailManifestV1Schema } from '@cut-on-eight/contracts';
import type { FastifyInstance } from 'fastify';
import type { AppServices } from '../services.js';
import { ApiRouteError } from './api-error.js';
import { parseProjectId } from './route-params.js';

function parseFileName(params: unknown): string {
  if (
    typeof params !== 'object' ||
    params === null ||
    Array.isArray(params) ||
    !('fileName' in params) ||
    typeof params.fileName !== 'string'
  ) {
    throw invalidFileName();
  }

  const fileName = params.fileName;
  if (!/^sprite-\d{3}\.webp$/u.test(fileName)) throw invalidFileName();
  return fileName;
}

function invalidFileName(): ApiRouteError {
  return new ApiRouteError(
    404,
    'thumbnail_page_not_found',
    'The thumbnail sprite page was not found.',
    false,
  );
}

export function registerThumbnailRoutes(
  app: FastifyInstance,
  services: AppServices,
): void {
  app.get('/api/projects/:id/thumbnails/manifest', async (request, reply) => {
    const projectId = parseProjectId(request.params, 'id');
    const manifest = thumbnailManifestV1Schema.parse(
      await services.getThumbnailManifest(projectId),
    );
    return reply.header('Cache-Control', 'no-cache').send(manifest);
  });

  app.get(
    '/api/projects/:id/thumbnails/:fileName',
    { exposeHeadRoute: false },
    async (request, reply) => {
      const projectId = parseProjectId(request.params, 'id');
      const page = await services.openThumbnailPage(
        projectId,
        parseFileName(request.params),
      );

      try {
        return reply
          .code(200)
          .header('Content-Type', 'image/webp')
          .header('Content-Length', page.size)
          .header('Cache-Control', 'public, max-age=31536000, immutable')
          .send(page.file.createReadStream({ autoClose: true }));
      } catch (error) {
        await page.file.close().catch(() => undefined);
        throw error;
      }
    },
  );
}
