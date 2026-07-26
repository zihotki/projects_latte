import {
  deleteFragmentRequestSchema,
  deletedFragmentSchema,
  editorSaveRequestSchema,
  editorVideoSchema,
  fragmentListSchema,
  fragmentPatchRequestSchema,
  fragmentSchema,
  restoreFragmentRequestSchema,
} from '@cut-on-eight/api-contracts';
import type { FastifyInstance } from 'fastify';
import type { ApiRuntime } from '../runtime.js';

export function registerCatalogFragmentRoutes(
  app: FastifyInstance,
  runtime: ApiRuntime,
): void {
  app.patch<{ Params: { videoId: string }; Body: unknown }>(
    '/api/videos/:videoId/editor',
    async (request) =>
      editorVideoSchema.parse(
        await runtime.fragments.saveEditor(
          request.params.videoId,
          editorSaveRequestSchema.parse(request.body),
        ),
      ),
  );
  app.get('/api/fragments', async () =>
    fragmentListSchema.parse(await runtime.fragments.list()),
  );
  app.patch<{ Params: { fragmentId: string }; Body: unknown }>(
    '/api/fragments/:fragmentId',
    async (request) =>
      fragmentSchema.parse(
        await runtime.fragments.patch(
          request.params.fragmentId,
          fragmentPatchRequestSchema.parse(request.body),
        ),
      ),
  );
  app.delete<{ Params: { fragmentId: string }; Body: unknown }>(
    '/api/fragments/:fragmentId',
    async (request) => {
      const body = deleteFragmentRequestSchema.parse(request.body);
      return deletedFragmentSchema.parse(
        await runtime.fragments.delete(
          request.params.fragmentId,
          body.expectedRevision,
        ),
      );
    },
  );
  app.post<{ Params: { fragmentId: string }; Body: unknown }>(
    '/api/fragments/:fragmentId/restore',
    async (request) => {
      const body = restoreFragmentRequestSchema.parse(request.body);
      return fragmentSchema.parse(
        await runtime.fragments.restore(
          request.params.fragmentId,
          body.undoToken,
        ),
      );
    },
  );
}
