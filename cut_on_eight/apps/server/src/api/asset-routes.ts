import type { FastifyInstance } from 'fastify';
import { blobKey } from '../blobs/blob-key.js';
import { CatalogNotFound } from '../domain/models.js';
import type { ApiRuntime } from '../runtime.js';

export function registerAssetRoutes(
  app: FastifyInstance,
  runtime: ApiRuntime,
): void {
  app.get<{ Params: { videoId: string } }>(
    '/api/videos/:videoId/source',
    async (request, reply) => {
      const video = await runtime.db
        .selectFrom('videos')
        .select('source_asset_id')
        .where('id', '=', request.params.videoId)
        .where('status', '!=', 'deleting')
        .executeTakeFirst();
      if (
        video?.source_asset_id === null ||
        video?.source_asset_id === undefined
      ) {
        throw new CatalogNotFound();
      }
      return reply.redirect(
        `/api/assets/${encodeURIComponent(video.source_asset_id)}`,
      );
    },
  );
  app.get<{ Params: { assetId: string } }>(
    '/api/assets/:assetId',
    async (request, reply) => {
      const row = await runtime.db
        .selectFrom('assets')
        .selectAll()
        .where('id', '=', request.params.assetId)
        .where('state', '=', 'ready')
        .where('kind', 'in', ['source', 'fragment_preview'])
        .executeTakeFirst();
      if (row === undefined) throw new CatalogNotFound();
      const visible =
        row.owner_kind === 'video'
          ? await runtime.db
              .selectFrom('videos')
              .select('id')
              .where('id', '=', row.owner_id)
              .where('source_asset_id', '=', row.id)
              .where('status', '!=', 'deleting')
              .executeTakeFirst()
          : await runtime.db
              .selectFrom('fragments')
              .innerJoin('videos', 'videos.id', 'fragments.video_id')
              .innerJoin(
                'fragment_previews',
                'fragment_previews.fragment_id',
                'fragments.id',
              )
              .select('fragments.id')
              .where('fragments.id', '=', row.owner_id)
              .where('fragments.deleted_at', 'is', null)
              .where('videos.status', '!=', 'deleting')
              .where('fragment_previews.asset_id', '=', row.id)
              .executeTakeFirst();
      if (visible === undefined) throw new CatalogNotFound();
      const size = Number(row.size_bytes);
      const parsed = parseRange(request.headers.range, size);
      if (parsed === 'invalid') {
        return reply
          .code(416)
          .header('content-range', `bytes */${size}`)
          .send();
      }
      const range = await runtime.blobs.openRange(
        blobKey(row.storage_key),
        parsed ?? undefined,
      );
      reply
        .header('accept-ranges', 'bytes')
        .header('content-type', row.mime_type)
        .header('content-length', range.endInclusive - range.start + 1);
      if (parsed !== null) {
        reply
          .code(206)
          .header(
            'content-range',
            `bytes ${range.start}-${range.endInclusive}/${range.size}`,
          );
      }
      if (row.kind === 'fragment_preview') {
        reply.header('cache-control', 'public, max-age=31536000, immutable');
      }
      return reply.send(range.stream);
    },
  );
}

function parseRange(
  value: string | undefined,
  size: number,
): null | 'invalid' | { start: number; endInclusive: number } {
  if (value === undefined) return null;
  if (value.includes(',')) return 'invalid';
  const match = /^bytes=(\d+)-(\d*)$/.exec(value);
  if (match === null) return 'invalid';
  const start = Number(match[1]);
  const endInclusive = match[2] === '' ? size - 1 : Number(match[2]);
  if (
    !Number.isSafeInteger(start) ||
    !Number.isSafeInteger(endInclusive) ||
    start < 0 ||
    endInclusive < start ||
    endInclusive >= size
  ) {
    return 'invalid';
  }
  return { start, endInclusive };
}
