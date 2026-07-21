import {
  capabilitiesSchema,
  jobRecordSchema,
  jobSnapshotSchema,
  type JobSnapshot,
} from '@cut-on-eight/contracts';
import type { FastifyInstance } from 'fastify';
import type { ServerResponse } from 'node:http';
import type { AppServices } from '../services.js';
import { parseProjectId } from './route-params.js';

function writeSnapshot(
  stream: NodeJS.WritableStream,
  snapshot: JobSnapshot,
): void {
  stream.write(
    `event: jobs\ndata: ${JSON.stringify(jobSnapshotSchema.parse(snapshot))}\n\n`,
  );
}

export function registerJobRoutes(
  app: FastifyInstance,
  services: AppServices,
): void {
  const activeResponses = new Set<ServerResponse>();

  app.addHook('preClose', async () => {
    for (const response of activeResponses) response.end();
    activeResponses.clear();
  });

  app.get('/api/jobs', async () =>
    jobSnapshotSchema.parse(await services.getJobs()),
  );

  app.get('/api/capabilities', async () =>
    capabilitiesSchema.parse(await services.getCapabilities()),
  );

  app.post('/api/jobs/:id/retry', async (request) => {
    const id = parseProjectId(request.params, 'id');
    return jobRecordSchema.parse(await services.retryJob(id));
  });

  app.get('/api/events', async (_request, reply) => {
    let ready = false;
    let pending: JobSnapshot | undefined;
    const connection: { keepalive?: NodeJS.Timeout } = {};
    let unsubscribe = (): void => undefined;
    let cleaned = false;
    const cleanup = (): void => {
      if (cleaned) return;
      cleaned = true;
      if (connection.keepalive !== undefined) {
        clearInterval(connection.keepalive);
      }
      unsubscribe();
      activeResponses.delete(reply.raw);
    };
    activeResponses.add(reply.raw);
    reply.raw.once('close', cleanup);
    reply.raw.once('error', cleanup);
    if (reply.raw.destroyed || reply.raw.writableEnded) {
      cleanup();
      return reply;
    }

    const subscribed = services.subscribeToJobs((snapshot) => {
      if (!ready) {
        pending = snapshot;
      } else if (!reply.raw.destroyed) {
        writeSnapshot(reply.raw, snapshot);
      }
    });
    unsubscribe = subscribed;
    if (cleaned) subscribed();
    let initial: JobSnapshot;
    try {
      initial = await services.getJobs();
    } catch (error) {
      cleanup();
      throw error;
    }
    if (reply.raw.destroyed) {
      cleanup();
      return reply;
    }
    reply.hijack();
    reply.raw.writeHead(200, {
      'cache-control': 'no-cache, no-transform',
      connection: 'keep-alive',
      'content-type': 'text/event-stream; charset=utf-8',
      'x-accel-buffering': 'no',
    });
    writeSnapshot(reply.raw, initial);
    if (pending !== undefined) writeSnapshot(reply.raw, pending);
    ready = true;
    connection.keepalive = setInterval(() => {
      if (!reply.raw.destroyed) reply.raw.write(': keepalive\n\n');
    }, 20_000);
    connection.keepalive.unref();
  });
}
