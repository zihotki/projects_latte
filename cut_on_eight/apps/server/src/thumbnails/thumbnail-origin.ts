import Fastify, { type FastifyInstance } from 'fastify';
import type { Kysely } from 'kysely';
import type { CatalogDatabase } from '../catalog/database-types.js';
import { installApiErrorHandling } from '../http/api-error.js';
import { ThumbnailBundleStore } from './thumbnail-bundle-store.js';
import {
  isVideoThumbnailManifest,
  type VideoThumbnailManifest,
} from './video-thumbnail-manifest.js';

export function createThumbnailOrigin(input: {
  database: Kysely<CatalogDatabase>;
  bundles: ThumbnailBundleStore;
}): FastifyInstance {
  const app = Fastify({ logger: true });
  installApiErrorHandling(app);
  app.get<{
    Params: { videoId: string };
  }>(
    '/thumbnail-cdn/v1/videos/:videoId/manifest.json',
    async (request, reply) => {
      const state = await findActiveState(
        input.database,
        request.params.videoId,
      );
      if (state === undefined) return reply.code(404).send();
      const etag = `"${state.storage_key}"`;
      if (request.headers['if-none-match'] === etag)
        return reply.code(304).send();
      return reply
        .header('cache-control', 'no-cache')
        .header('etag', etag)
        .type('application/json')
        .send(state.manifest);
    },
  );
  app.get<{
    Params: { videoId: string; fileName: string };
  }>('/thumbnail-cdn/v1/videos/:videoId/:fileName', async (request, reply) => {
    const state = await findActiveState(input.database, request.params.videoId);
    if (state === undefined) return reply.code(404).send();
    if (
      !state.manifest.pages.some(([name]) => name === request.params.fileName)
    ) {
      return reply.code(404).send();
    }
    const page = await input.bundles.readPage(
      state.storage_key,
      request.params.fileName,
    );
    if (page === null) return reply.code(404).send();
    return reply
      .header('cache-control', 'public, max-age=31536000, immutable')
      .type('image/webp')
      .send(page);
  });
  return app;
}

async function findActiveState(
  database: Kysely<CatalogDatabase>,
  videoId: string,
): Promise<
  | {
      readonly storage_key: string;
      readonly manifest: VideoThumbnailManifest;
    }
  | undefined
> {
  const state = await database
    .selectFrom('video_thumbnail_state')
    .select(['storage_key', 'manifest', 'status'])
    .where('video_id', '=', videoId)
    .executeTakeFirst();
  if (
    state?.status !== 'ready' ||
    state.storage_key === null ||
    state.storage_key === undefined
  ) {
    return undefined;
  }
  const manifest = assertManifest(state.manifest);
  return manifest === undefined
    ? undefined
    : { storage_key: state.storage_key, manifest };
}

function assertManifest(value: unknown): VideoThumbnailManifest | undefined {
  return isVideoThumbnailManifest(value) ? value : undefined;
}
