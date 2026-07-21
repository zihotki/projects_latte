import { healthResponseSchema } from '@cut-on-eight/contracts';
import Fastify, { type FastifyInstance } from 'fastify';

export function createApp(): FastifyInstance {
  const app = Fastify({ logger: true });

  app.get('/api/health', async () =>
    healthResponseSchema.parse({
      status: 'ok',
      service: 'cut-on-eight-server',
    }),
  );

  return app;
}
