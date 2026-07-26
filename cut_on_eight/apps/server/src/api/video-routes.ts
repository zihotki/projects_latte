import {
  uploadAcceptedSchema,
  videoListSchema,
  videoSummarySchema,
  deleteVideoRequestSchema,
  workspaceSchema,
} from '@cut-on-eight/api-contracts';
import type { FastifyInstance } from 'fastify';
import { DomainConflict } from '../domain/models.js';
import type { ApiRuntime } from '../runtime.js';

export function registerVideoRoutes(
  app: FastifyInstance,
  runtime: ApiRuntime,
): void {
  app.post('/api/videos', async (request, reply) => {
    const part = await request.file();
    if (part === undefined || part.fieldname !== 'source') {
      throw new DomainConflict(
        'validation_failed',
        'One source file is required.',
      );
    }
    if (!part.filename.toLowerCase().endsWith('.mp4')) {
      throw new DomainConflict(
        'validation_failed',
        'Only MP4 files are supported.',
      );
    }
    const accepted = await runtime.videos.import({
      fileName: part.filename,
      mimeType: part.mimetype,
      bytes: part.file,
    });
    return reply.code(202).send(uploadAcceptedSchema.parse(accepted));
  });

  app.get('/api/videos', async () =>
    videoListSchema.parse(await runtime.videos.list()),
  );
  app.get<{ Params: { videoId: string } }>(
    '/api/videos/:videoId',
    async (request) =>
      videoSummarySchema.parse(
        await runtime.videos.get(request.params.videoId),
      ),
  );
  app.post<{ Params: { videoId: string } }>(
    '/api/videos/:videoId/open',
    async (request) =>
      workspaceSchema.parse(
        await runtime.workspace.open(request.params.videoId),
      ),
  );
  app.post<{ Params: { videoId: string } }>(
    '/api/videos/:videoId/activate',
    async (request) =>
      workspaceSchema.parse(
        await runtime.workspace.activate(request.params.videoId),
      ),
  );
  app.post<{ Params: { videoId: string } }>(
    '/api/videos/:videoId/close',
    async (request) =>
      workspaceSchema.parse(
        await runtime.workspace.close(request.params.videoId),
      ),
  );
  app.delete<{ Params: { videoId: string }; Body: unknown }>(
    '/api/videos/:videoId',
    async (request) => {
      const body = deleteVideoRequestSchema.parse(request.body);
      return workspaceSchema.parse(
        await runtime.videos.delete(
          request.params.videoId,
          body.expectedRevision,
        ),
      );
    },
  );
}
