import {
  healthLiveSchema,
  problemDetailsSchema,
} from '@cut-on-eight/api-contracts';
import { sql, type Kysely } from 'kysely';
import type { FastifyInstance, FastifyReply } from 'fastify';
import type { CatalogDatabase } from '../catalog/database-types.js';
import type { ServerConfig } from '../config.js';
import { toReadyDto } from './public-mappers.js';

export interface HealthProbes {
  postgres(): Promise<void>;
  qdrant: ((signal: AbortSignal) => Promise<void>) | null;
  worker(): Promise<boolean>;
}

export const qdrantReadinessDeadlineMs = 500;

export function createHealthProbes(
  database: Kysely<CatalogDatabase>,
  config: Pick<ServerConfig, 'qdrantHttpUrl' | 'qdrantApiKey'>,
  qdrantProbe?: (signal: AbortSignal) => Promise<void>,
): HealthProbes {
  const qdrant =
    qdrantProbe ??
    (config.qdrantHttpUrl === null
      ? null
      : async (signal) => {
          const response = await fetch(
            new URL('/healthz', config.qdrantHttpUrl!).href,
            {
              signal,
              headers:
                config.qdrantApiKey === null
                  ? undefined
                  : { 'api-key': config.qdrantApiKey },
            },
          );
          if (!response.ok) {
            throw new Error(`Qdrant health returned ${response.status}`);
          }
        });

  return {
    async postgres() {
      await sql`select 1`.execute(database);
    },
    qdrant,
    async worker() {
      const result = await sql<{ ready: boolean }>`
        select exists (
          select 1
          from worker_heartbeats
          where last_seen_at > now() - interval '15 seconds'
        ) as ready
      `.execute(database);
      return result.rows[0]?.ready ?? false;
    },
  };
}

export function registerHealthRoutes(
  app: FastifyInstance,
  probes?: HealthProbes,
): void {
  app.get('/api/health/live', async () =>
    healthLiveSchema.parse({
      status: 'live',
      service: 'cut-on-eight-server',
    }),
  );

  app.get('/api/health/ready', async (request, reply) => {
    if (probes === undefined) {
      return unavailable(reply, request.url);
    }

    try {
      await probes.postgres();
    } catch {
      return unavailable(reply, request.url);
    }

    const [qdrant, worker] = await Promise.all([
      checkQdrant(probes.qdrant),
      probes.worker().catch(() => false),
    ]);

    return toReadyDto({
      postgres: 'ready',
      qdrant,
      worker: worker ? 'ready' : 'unavailable',
    });
  });
}

async function checkQdrant(
  probe: ((signal: AbortSignal) => Promise<void>) | null,
): Promise<'ready' | 'degraded' | 'not-configured'> {
  if (probe === null) {
    return 'not-configured';
  }
  const controller = new AbortController();
  let timer: NodeJS.Timeout | undefined;
  try {
    await Promise.race([
      probe(controller.signal),
      new Promise<never>((_resolve, reject) => {
        timer = setTimeout(() => {
          controller.abort();
          reject(new Error('Qdrant readiness deadline exceeded'));
        }, qdrantReadinessDeadlineMs);
      }),
    ]);
    return 'ready';
  } catch {
    return 'degraded';
  } finally {
    if (timer !== undefined) {
      clearTimeout(timer);
    }
  }
}

function unavailable(reply: FastifyReply, instance: string) {
  const body = problemDetailsSchema.parse({
    type: 'https://cut-on-eight.local/problems/dependency-unavailable',
    title: 'Required dependency unavailable',
    status: 503,
    detail: 'The catalog database is unavailable.',
    code: 'catalog_unavailable',
    instance,
  });
  return reply.code(503).type('application/problem+json').send(body);
}
