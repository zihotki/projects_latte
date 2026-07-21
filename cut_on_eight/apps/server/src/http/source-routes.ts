import type { FastifyInstance, FastifyReply } from 'fastify';
import type { AppServices, ManagedSource } from '../services.js';
import { apiError } from './api-error.js';
import { parseProjectId } from './route-params.js';

interface ByteRange {
  readonly end: number;
  readonly start: number;
}

function parseByteRange(header: string, size: number): ByteRange | null {
  const match = /^bytes=(\d*)-(\d*)$/u.exec(header.trim());

  if (match === null) {
    return null;
  }

  const startText = match[1] ?? '';
  const endText = match[2] ?? '';

  if (startText.length === 0 && endText.length === 0) {
    return null;
  }

  if (startText.length === 0) {
    const suffixLength = Number(endText);

    if (
      !Number.isSafeInteger(suffixLength) ||
      suffixLength <= 0 ||
      size === 0
    ) {
      return null;
    }

    return {
      start: Math.max(size - suffixLength, 0),
      end: size - 1,
    };
  }

  const start = Number(startText);

  if (!Number.isSafeInteger(start) || start < 0 || start >= size) {
    return null;
  }

  const requestedEnd = endText.length === 0 ? size - 1 : Number(endText);

  if (!Number.isSafeInteger(requestedEnd) || requestedEnd < start) {
    return null;
  }

  return { start, end: Math.min(requestedEnd, size - 1) };
}

async function sendInvalidRange(
  reply: FastifyReply,
  source: ManagedSource,
): Promise<FastifyReply> {
  await source.file.close().catch(() => undefined);
  return reply
    .code(416)
    .header('Accept-Ranges', 'bytes')
    .header('Content-Range', `bytes */${source.size}`)
    .send(
      apiError(
        'invalid_range',
        'The requested video byte range is not satisfiable.',
        false,
      ),
    );
}

export function registerSourceRoutes(
  app: FastifyInstance,
  services: AppServices,
): void {
  app.get(
    '/api/sources/:projectId/content',
    { exposeHeadRoute: false },
    async (request, reply) => {
      const projectId = parseProjectId(request.params, 'projectId');
      const source = await services.openSource(projectId);

      try {
        const rangeHeader = request.headers.range;
        reply.header('Accept-Ranges', 'bytes');

        if (rangeHeader === undefined) {
          return reply
            .code(200)
            .header('Content-Type', 'video/mp4')
            .header('Content-Length', source.size)
            .send(source.file.createReadStream({ autoClose: true }));
        }

        const range = parseByteRange(rangeHeader, source.size);

        if (range === null) {
          return sendInvalidRange(reply, source);
        }

        return reply
          .code(206)
          .header('Content-Type', 'video/mp4')
          .header(
            'Content-Range',
            `bytes ${range.start}-${range.end}/${source.size}`,
          )
          .header('Content-Length', range.end - range.start + 1)
          .send(
            source.file.createReadStream({
              autoClose: true,
              start: range.start,
              end: range.end,
            }),
          );
      } catch (error) {
        await source.file.close().catch(() => undefined);
        throw error;
      }
    },
  );
}
